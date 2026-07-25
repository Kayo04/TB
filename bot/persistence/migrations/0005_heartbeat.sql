-- Durable liveness signal, distinct from run_log. run_log only gains a new
-- row when a bar closes -- up to once per timeframe (once an hour for 1h
-- bars) -- so a wedged process could go unnoticed for a long time. heartbeat
-- is written on a short, fixed ~60s cadence by LiveRunner regardless of bar
-- activity, so the dashboard can tell "healthily waiting for the next bar"
-- apart from "silently stuck" within roughly a minute, not an hour. One row
-- per component, upserted in place -- only "how long ago was this last
-- written" matters, not history.
CREATE TABLE heartbeat (
    component      TEXT PRIMARY KEY,
    detail         TEXT,
    last_seen_at   TIMESTAMPTZ NOT NULL
);
