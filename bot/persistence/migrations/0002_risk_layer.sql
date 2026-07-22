-- Milestone 4: durable kill-switch state and equity history for the
-- mark-to-market drawdown check.
--
-- risk_events is append-only, same convention as orders/fills/
-- reconciliation_checks: current halt state is derived from the latest row
-- (event_type), never overwritten in place. This gives a full audit trail
-- of every halt and every human clearance for free.
--
-- Enforcement note (same as milestone 3): append-only is a review-enforced
-- convention here, not yet a DB grant. REVOKE UPDATE, DELETE ... FROM
-- app_role remains deferred tech debt until a non-superuser app role
-- exists.

CREATE TABLE risk_events (
    event_id     BIGSERIAL PRIMARY KEY,
    event_type   TEXT NOT NULL CHECK (event_type IN ('halt', 'clear')),
    reason       TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_risk_events_created_at ON risk_events (created_at DESC);

CREATE TABLE equity_snapshots (
    snapshot_id    BIGSERIAL PRIMARY KEY,
    total_equity   DOUBLE PRECISION NOT NULL,
    cash_flow      DOUBLE PRECISION NOT NULL,
    mark_to_market DOUBLE PRECISION NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_equity_snapshots_recorded_at ON equity_snapshots (recorded_at DESC);
