#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
exec docker compose exec -T spark bash -c \
  'exec /opt/spark/bin/spark-sql --conf "spark.sql.catalog.semskip.jdbc.password=$SEMSKIP_DB_PASSWORD" "$@"' \
  spark-sql "$@"
