#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
umask 077

# Create deployment-local credentials.
python3 - <<'PY'
import secrets
from pathlib import Path

try:
    with Path(".env").open("x") as env:
        env.write("SEMSKIP_S3_USER=semskip\n")
        env.write("SEMSKIP_S3_PASSWORD=" + secrets.token_urlsafe(24) + "\n")
        env.write("SEMSKIP_DB_PASSWORD=" + secrets.token_urlsafe(24) + "\n")
    Path(".env").chmod(0o600)
except FileExistsError:
    pass
PY

# Download runtime dependencies from Maven Central.
mkdir -p .data/jars
fetch_jar() {
    local url="https://repo.maven.apache.org/maven2/$1"
    local file=".data/jars/${1##*/}"
    if [[ ! -s "$file" ]]; then
        curl --fail --silent --show-error --location --retry 3 "$url" --output "$file.part"
        mv -- "$file.part" "$file"
    fi
    chmod 0644 "$file"
}
fetch_jar org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar
fetch_jar org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar
fetch_jar org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar

docker compose up -d --wait --wait-timeout 180
