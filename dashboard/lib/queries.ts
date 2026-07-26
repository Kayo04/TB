import pool from "./db";

// Every function here issues exactly one SELECT. bigint/bigserial columns
// (the *_id primary keys) come back from node-postgres as strings, not
// numbers, by default -- typed that way below to match reality rather than
// silently losing precision.

export type RunLogRow = {
  run_log_id: string;
  bar_ts: string;
  symbol: string;
  signal: number | null;
  decision: "no_transition" | "order_submitted" | "cycle_failed";
  order_status: string | null;
  reason: string | null;
  reconciliation_divergent: boolean | null;
  halted_after: boolean;
  cycle_duration_ms: number;
  created_at: string;
};

export async function getRecentRunLog(limit = 50): Promise<RunLogRow[]> {
  const { rows } = await pool.query<RunLogRow>(
    "SELECT * FROM run_log ORDER BY bar_ts DESC, run_log_id DESC LIMIT $1",
    [limit]
  );
  return rows;
}

export type FillRow = {
  fill_id: string;
  client_order_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
  filled_ts: string;
  created_at: string;
};

export async function getRecentFills(limit = 50): Promise<FillRow[]> {
  const { rows } = await pool.query<FillRow>(
    "SELECT * FROM fills ORDER BY filled_ts DESC, fill_id DESC LIMIT $1",
    [limit]
  );
  return rows;
}

// Unbounded on purpose: trade-pairing (lib/tradeStats.ts) needs every fill
// ever recorded to compute lifetime P&L/win-rate correctly, not just a
// recent page. Fee/fill-count history is small (one row per order
// execution), so this is cheap for as long as this stays a single-symbol
// paper bot -- revisit if that assumption ever changes.
export async function getAllFills(): Promise<FillRow[]> {
  const { rows } = await pool.query<FillRow>("SELECT * FROM fills ORDER BY filled_ts ASC, fill_id ASC");
  return rows;
}

export type LatestEquity = { totalEquity: number; recordedAt: string } | null;

export async function getLatestEquity(): Promise<LatestEquity> {
  const { rows } = await pool.query<{ total_equity: number; recorded_at: string }>(
    "SELECT total_equity, recorded_at FROM equity_snapshots ORDER BY recorded_at DESC LIMIT 1"
  );
  const row = rows[0];
  return row ? { totalEquity: row.total_equity, recordedAt: row.recorded_at } : null;
}

export type CycleActivity = {
  totalCycles: number;
  byDecision: Record<string, number>;
  monitoringSince: string | null;
  lastCycleAt: string | null;
  avgDurationMs24h: number | null;
};

// monitoringSince is the earliest run_log row, NOT true process uptime --
// heartbeat is a single upserted row with no history, so past restarts
// aren't visible from current tables. Labelled honestly wherever it's
// rendered (ActivityPanel) rather than called "uptime". Supersedes the old
// getCycleHealth() (folded avgDurationMs in here; failedLast24h dropped in
// favor of the lifetime cycle_failed breakdown below, which is more useful
// than the same count windowed two different ways).
export async function getCycleActivity(): Promise<CycleActivity> {
  const [{ rows: byDecisionRows }, { rows: rangeRows }, { rows: avgRows }] = await Promise.all([
    pool.query<{ decision: string; c: string }>("SELECT decision, COUNT(*) AS c FROM run_log GROUP BY decision"),
    pool.query<{ since: string | null; last: string | null }>(
      "SELECT MIN(created_at) AS since, MAX(created_at) AS last FROM run_log"
    ),
    pool.query<{ avg_ms: string | null }>(
      "SELECT AVG(cycle_duration_ms) AS avg_ms FROM run_log WHERE created_at > now() - interval '24 hours'"
    ),
  ]);

  const byDecision: Record<string, number> = {};
  let totalCycles = 0;
  for (const row of byDecisionRows) {
    const count = Number(row.c);
    byDecision[row.decision] = count;
    totalCycles += count;
  }

  return {
    totalCycles,
    byDecision,
    avgDurationMs24h: avgRows[0]?.avg_ms != null ? Number(avgRows[0].avg_ms) : null,
    monitoringSince: rangeRows[0]?.since ?? null,
    lastCycleAt: rangeRows[0]?.last ?? null,
  };
}

export type EquitySnapshotRow = {
  snapshot_id: string;
  total_equity: number;
  cash_flow: number;
  mark_to_market: number;
  recorded_at: string;
};

export async function getEquityCurve(limit = 500): Promise<EquitySnapshotRow[]> {
  const { rows } = await pool.query<EquitySnapshotRow>(
    `SELECT * FROM (
       SELECT * FROM equity_snapshots ORDER BY recorded_at DESC LIMIT $1
     ) recent
     ORDER BY recorded_at ASC`,
    [limit]
  );
  return rows;
}

export async function getStrategyName(): Promise<string | null> {
  const { rows } = await pool.query<{ strategy_name: string }>(
    "SELECT strategy_name FROM orders ORDER BY created_at DESC LIMIT 1"
  );
  return rows[0]?.strategy_name ?? null;
}

export type PositionRow = { symbol: string; position: number };

export async function getPositions(): Promise<PositionRow[]> {
  const { rows } = await pool.query<PositionRow>(
    `SELECT symbol, COALESCE(SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END), 0) AS position
     FROM fills
     GROUP BY symbol
     ORDER BY symbol`
  );
  return rows;
}

export type RiskEventRow = {
  event_id: string;
  event_type: "halt" | "clear";
  reason: string;
  triggered_by: string;
  created_at: string;
};

export async function getRiskEvents(limit = 50): Promise<RiskEventRow[]> {
  const { rows } = await pool.query<RiskEventRow>(
    "SELECT * FROM risk_events ORDER BY created_at DESC, event_id DESC LIMIT $1",
    [limit]
  );
  return rows;
}

export type HaltState = { halted: boolean; latestEvent: RiskEventRow | null };

export async function getHaltState(): Promise<HaltState> {
  const events = await getRiskEvents(1);
  const latestEvent = events[0] ?? null;
  return { halted: latestEvent?.event_type === "halt", latestEvent };
}

export type ReconciliationRow = {
  check_id: string;
  symbol: string;
  internal_position: number;
  external_position: number;
  difference: number;
  is_divergent: boolean;
  checked_at: string;
};

export async function getReconciliationChecks(limit = 50): Promise<ReconciliationRow[]> {
  const { rows } = await pool.query<ReconciliationRow>(
    "SELECT * FROM reconciliation_checks ORDER BY checked_at DESC, check_id DESC LIMIT $1",
    [limit]
  );
  return rows;
}

export type HeartbeatRow = {
  component: string;
  detail: string | null;
  lastSeenAt: string;
};

// Distinct from getCycleHealth() below: run_log only gains a row when a bar
// closes (up to once per timeframe -- once an hour for 1h bars). heartbeat
// is written by LiveRunner on a fixed ~60s cadence regardless of bar
// activity, so "last activity" here can catch a wedged process within
// roughly a minute instead of only after an hour-long silence.
export async function getHeartbeat(): Promise<HeartbeatRow | null> {
  const { rows } = await pool.query<{ component: string; detail: string | null; last_seen_at: string }>(
    "SELECT component, detail, last_seen_at FROM heartbeat ORDER BY last_seen_at DESC LIMIT 1"
  );
  const row = rows[0];
  if (!row) return null;
  return { component: row.component, detail: row.detail, lastSeenAt: row.last_seen_at };
}

