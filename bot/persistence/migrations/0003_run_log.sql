-- Milestone 5: append-only history of every orchestration cycle attempt,
-- success or failure. Same convention as every other table here. This is
-- also the intended data source for the future dashboard (not built here).

CREATE TABLE run_log (
    run_log_id                BIGSERIAL PRIMARY KEY,
    bar_ts                    TIMESTAMPTZ NOT NULL,
    symbol                    TEXT NOT NULL,
    signal                    INTEGER,
    decision                  TEXT NOT NULL CHECK (decision IN ('no_transition', 'order_submitted', 'cycle_failed')),
    order_status               TEXT,
    reason                     TEXT,
    reconciliation_divergent   BOOLEAN,
    halted_after                BOOLEAN NOT NULL,
    cycle_duration_ms             INTEGER NOT NULL,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_log_created_at ON run_log (created_at DESC);
CREATE INDEX idx_run_log_bar_ts ON run_log (bar_ts DESC);
