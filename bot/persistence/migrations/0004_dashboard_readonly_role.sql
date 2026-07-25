-- Read-only dashboard: dashboard_ro never receives write grants at any
-- point, so there's no REVOKE needed the way there would be for a role
-- that started with broader privileges (see migration 0001's still-deferred
-- note about the bot's own superuser role). ALTER DEFAULT PRIVILEGES means
-- any table a future migration adds is automatically covered without a
-- follow-up grant.
--
-- No password set here -- a LOGIN role with no password cannot authenticate,
-- so this migration commits no secret. Password is set once, deploy-time,
-- via ALTER ROLE (see README.md / DEPLOY.md), never in a committed file.

CREATE ROLE dashboard_ro WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE trading_bot TO dashboard_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dashboard_ro;
