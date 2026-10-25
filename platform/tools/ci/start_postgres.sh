#!/usr/bin/env bash
# Start a throwaway PostgreSQL 16 for platform/db/test_schema.py as the CURRENT, non-root user (CI runners are not
# root, so the test's own ephemeral mode, which drops to `nobody` via runuser, does not apply).
#   platform/tools/ci/start_postgres.sh >> "$GITHUB_ENV"     # locally: set -a; eval "$(...)"; set +a
# Prints DEVPLAT_PG_HOST/PORT/USER for the test's "server" mode. The server listens only on a Unix socket in a
# private temporary directory, with trust authentication for local connections; superuser `devplat` (the tests
# need it to create isolated roles and, in one case, to backdate an append-only row). Data is discarded with the
# runner. Never use this for anything but tests.
set -euo pipefail
PG_BINDIR=${PG_BINDIR:-/usr/lib/postgresql/16/bin}
if [ "$(id -u)" = 0 ]; then echo "start_postgres.sh: run as a non-root user (initdb refuses root)" >&2; exit 2; fi
[ -x "$PG_BINDIR/initdb" ] || { echo "start_postgres.sh: PostgreSQL 16 server binaries not found in $PG_BINDIR" >&2; exit 2; }
command -v psql >/dev/null || { echo "start_postgres.sh: psql client not found" >&2; exit 2; }
"$PG_BINDIR/postgres" --version | grep -q ' 16\.' || { echo "start_postgres.sh: not PostgreSQL 16: $("$PG_BINDIR/postgres" --version)" >&2; exit 2; }
D=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/devplat-pg.XXXXXX"); chmod 700 "$D"
on_exit() { local rc=$?; [ "$rc" = 0 ] || { echo "start_postgres.sh failed ($rc); logs:" >&2; cat "$D"/*.log >&2 2>/dev/null; }; }
trap on_exit EXIT
PORT=55432
"$PG_BINDIR/initdb" -D "$D/data" -U devplat --auth=trust -E UTF8 --no-locale >"$D/initdb.log"
"$PG_BINDIR/pg_ctl" -D "$D/data" -l "$D/server.log" -w -o "-k $D -p $PORT -c listen_addresses=" start >/dev/null
psql -X -At -h "$D" -p "$PORT" -U devplat -d postgres -c 'select version()' | sed 's/^/# /' >&2
printf 'DEVPLAT_PG_HOST=%s\nDEVPLAT_PG_PORT=%s\nDEVPLAT_PG_USER=devplat\nPG_BINDIR=%s\n' "$D" "$PORT" "$PG_BINDIR"
