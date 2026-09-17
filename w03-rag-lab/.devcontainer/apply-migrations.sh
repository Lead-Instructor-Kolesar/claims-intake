#!/usr/bin/env bash
# Applied at container start. Migrations are idempotent and ordered by file name.
#
# migrations/*.sql are the Day 1 schema and are applied on every container start.
# migrations/day5/*.sql add the document table and the chunk-to-document foreign
# key. They are applied only when STAGE=day5, because the foreign key requires
# ingestion to write document rows, which is Day 5 work. Applying them earlier
# would fail every chunk insert from Day 1 onward.
set -euo pipefail
cd "$(dirname "$0")/.."

DSN="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
STAGE="${STAGE:-day1}"

for f in migrations/*.sql; do
  echo "applying $f"
  psql "$DSN" -v ON_ERROR_STOP=1 -f "$f"
done

if [ "$STAGE" = "day5" ]; then
  for f in migrations/day5/*.sql; do
    echo "applying $f"
    psql "$DSN" -v ON_ERROR_STOP=1 -f "$f"
  done
fi
