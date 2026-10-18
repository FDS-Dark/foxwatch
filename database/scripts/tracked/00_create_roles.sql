-- Creates the application read/write role. Runs once as dbup_user (SUPERUSER).
-- $ReadWriteUser$ and $ReadWritePassword$ are substituted from appsettings Variables.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$ReadWriteUser$') THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '$ReadWriteUser$', '$ReadWritePassword$');
    END IF;
END
$$;

GRANT CONNECT ON DATABASE "$database$" TO "$ReadWriteUser$";
