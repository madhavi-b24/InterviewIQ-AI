#!/bin/sh
# Runs once, on first container init (per the postgres image's docker-entrypoint-initdb.d
# convention). Creates the test database alongside the dev one so `pytest` and the app
# never share state, without requiring a second Postgres service.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE ${POSTGRES_DB}_test;
EOSQL
