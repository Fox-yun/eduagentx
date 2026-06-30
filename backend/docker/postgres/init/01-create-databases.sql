SELECT 'CREATE DATABASE eduagentx_test'
WHERE NOT EXISTS (
    SELECT
    FROM pg_database
    WHERE datname = 'eduagentx_test'
)\gexec

SELECT 'CREATE DATABASE eduagentx_e2e'
WHERE NOT EXISTS (
    SELECT
    FROM pg_database
    WHERE datname = 'eduagentx_e2e'
)\gexec
