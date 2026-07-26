import type { FillRow } from "./queries";

export type ClosedTrade = {
  symbol: string;
  entryTs: string;
  entryPrice: number;
  entryFee: number;
  exitTs: string;
  exitPrice: number;
  exitFee: number;
  qty: number;
  pnl: number;
  bucket: "win" | "loss" | "breakeven";
};

export type OpenPosition = {
  symbol: string;
  entryTs: string;
  entryPrice: number;
  qty: number;
};

export type PairingAnomaly = {
  symbol: string;
  fillId: string;
  reason: string;
};

export type TradeStats = {
  closedTrades: ClosedTrade[];
  openPositions: OpenPosition[];
  anomalies: PairingAnomaly[];
};

const QTY_EPSILON = 1e-9;

/**
 * Pairs fills into round-trip trades. Exact given the system's current
 * invariant: qty is fixed per symbol and the strategy is binary (flat/long,
 * see bot/strategy/ma_crossover.py + bot/risk/base.py's max_position_size),
 * so fills for a given symbol must strictly alternate buy, sell, buy,
 * sell, ... starting with buy. That invariant is NOT enforced by the
 * database schema -- it holds only because of today's strategy/risk-limit
 * shape. If sizing ever varies or a second concurrent position is
 * introduced, this function must stop trusting the pairing rather than
 * silently compute a wrong number: as soon as either check below fails for
 * a symbol, pairing for that symbol stops at that fill and everything from
 * that point on (including any "open position") is reported as an
 * anomaly instead of a number.
 */
export function pairTrades(fills: FillRow[]): TradeStats {
  const bySymbol = new Map<string, FillRow[]>();
  for (const fill of fills) {
    const list = bySymbol.get(fill.symbol);
    if (list) {
      list.push(fill);
    } else {
      bySymbol.set(fill.symbol, [fill]);
    }
  }

  const closedTrades: ClosedTrade[] = [];
  const openPositions: OpenPosition[] = [];
  const anomalies: PairingAnomaly[] = [];

  for (const [symbol, symbolFills] of bySymbol) {
    const ordered = [...symbolFills].sort((a, b) => {
      const byTs = new Date(a.filled_ts).getTime() - new Date(b.filled_ts).getTime();
      return byTs !== 0 ? byTs : a.fill_id.localeCompare(b.fill_id);
    });

    const referenceQty = ordered[0].qty;
    let expectedSide: "buy" | "sell" = "buy";
    let pendingEntry: FillRow | null = null;
    let broken = false;

    for (const fill of ordered) {
      if (Math.abs(fill.qty - referenceQty) > QTY_EPSILON) {
        anomalies.push({
          symbol,
          fillId: fill.fill_id,
          reason: `qty ${fill.qty} difere da qty de referência ${referenceQty} -- assunção de tamanho fixo violada`,
        });
        broken = true;
        break;
      }
      if (fill.side !== expectedSide) {
        anomalies.push({
          symbol,
          fillId: fill.fill_id,
          reason: `esperado fill '${expectedSide}' mas encontrado '${fill.side}' -- fills não alternam como esperado`,
        });
        broken = true;
        break;
      }

      if (fill.side === "buy") {
        pendingEntry = fill;
        expectedSide = "sell";
      } else {
        const entry = pendingEntry as FillRow; // guaranteed set: alternation above enforces buy precedes sell
        const pnl = (fill.price - entry.price) * entry.qty - entry.fee - fill.fee;
        closedTrades.push({
          symbol,
          entryTs: entry.filled_ts,
          entryPrice: entry.price,
          entryFee: entry.fee,
          exitTs: fill.filled_ts,
          exitPrice: fill.price,
          exitFee: fill.fee,
          qty: entry.qty,
          pnl,
          bucket: pnl > 0 ? "win" : pnl < 0 ? "loss" : "breakeven",
        });
        pendingEntry = null;
        expectedSide = "buy";
      }
    }

    // Past an anomaly, nothing about this symbol's position is trustworthy
    // from this pairing -- deliberately not reporting an "open position"
    // for it either.
    if (!broken && pendingEntry !== null) {
      openPositions.push({
        symbol,
        entryTs: pendingEntry.filled_ts,
        entryPrice: pendingEntry.price,
        qty: pendingEntry.qty,
      });
    }
  }

  if (anomalies.length > 0) {
    // Surfaced in the UI (see TradeAnomalyBanner) AND here, in the server
    // log -- fail loud, not silent, per project convention (CLAUDE.md).
    console.error("[trade-pairing anomaly]", JSON.stringify(anomalies));
  }

  return { closedTrades, openPositions, anomalies };
}

export type TradeSummary = {
  totalClosedTrades: number;
  wins: number;
  losses: number;
  breakeven: number;
  winRate: number | null; // wins / totalClosedTrades; null if no closed trades yet
  totalRealizedPnl: number;
  avgTrade: number | null;
  bestTrade: ClosedTrade | null;
  bestTradePnl: number | null;
  worstTrade: ClosedTrade | null;
  worstTradePnl: number | null;
};

export function summarizeTrades(closedTrades: ClosedTrade[]): TradeSummary {
  const wins = closedTrades.filter((t) => t.bucket === "win").length;
  const losses = closedTrades.filter((t) => t.bucket === "loss").length;
  const breakeven = closedTrades.filter((t) => t.bucket === "breakeven").length;
  const totalRealizedPnl = closedTrades.reduce((sum, t) => sum + t.pnl, 0);

  let bestTrade: ClosedTrade | null = null;
  let worstTrade: ClosedTrade | null = null;
  for (const t of closedTrades) {
    if (bestTrade === null || t.pnl > bestTrade.pnl) bestTrade = t;
    if (worstTrade === null || t.pnl < worstTrade.pnl) worstTrade = t;
  }

  return {
    totalClosedTrades: closedTrades.length,
    wins,
    losses,
    breakeven,
    winRate: closedTrades.length > 0 ? wins / closedTrades.length : null,
    totalRealizedPnl,
    avgTrade: closedTrades.length > 0 ? totalRealizedPnl / closedTrades.length : null,
    bestTrade,
    bestTradePnl: bestTrade?.pnl ?? null,
    worstTrade,
    worstTradePnl: worstTrade?.pnl ?? null,
  };
}
