-- Milestone 3: replaces milestone 2's collapsed orders table (which carried
-- filled_price/fee/filled_ts directly) with a proper split of intent
-- (orders) from execution (fills), plus reconciliation_checks.
--
-- No real trading history exists yet in this database -- only milestone-2
-- test rows -- so this is a destructive reshape, not a backward-compatible
-- ALTER. That's deliberate: see PROGRESS.md.
--
-- Append-only by convention, not yet by DB grant: REVOKE UPDATE, DELETE
-- ... FROM app_role is the real enforcement, deferred as tech debt until a
-- non-superuser app role exists (everything currently runs as the
-- `postgres` superuser in the local paper container).

DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    client_order_id TEXT PRIMARY KEY,
    strategy_name   TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty             DOUBLE PRECISION NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'filled', 'rejected')),
    effective_ts    TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fills (
    fill_id         BIGSERIAL PRIMARY KEY,
    client_order_id TEXT NOT NULL REFERENCES orders(client_order_id),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty             DOUBLE PRECISION NOT NULL,
    price           DOUBLE PRECISION NOT NULL,
    fee             DOUBLE PRECISION NOT NULL,
    filled_ts       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reconciliation_checks (
    check_id           BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    internal_position    DOUBLE PRECISION NOT NULL,
    external_position    DOUBLE PRECISION NOT NULL,
    difference            DOUBLE PRECISION NOT NULL,
    is_divergent           BOOLEAN NOT NULL,
    checked_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
