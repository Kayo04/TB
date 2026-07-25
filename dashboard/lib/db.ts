import { Pool } from "pg";

// Connects as dashboard_ro (see bot/persistence/migrations/0004_dashboard_readonly_role.sql).
// Every query in queries.ts is SELECT-only, but the real guarantee is the
// Postgres role itself -- it has no write grant, ever -- not this file's
// discipline. See tests/test_dashboard_role.py in the bot repo.
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,
});

export default pool;
