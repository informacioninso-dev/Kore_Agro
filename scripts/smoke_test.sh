#!/usr/bin/env bash
set -Eeuo pipefail

base_url="${BASE_URL:?Define BASE_URL, por ejemplo https://agro.example.com}"
base_url="${base_url%/}"

health="$(curl --fail --silent --show-error "${base_url}/health/")"
readiness="$(curl --fail --silent --show-error "${base_url}/readiness/")"

grep -q '"status": "ok"' <<< "${health}"
grep -q '"database": "ready"' <<< "${readiness}"

echo "KORE Agro responde correctamente en ${base_url}"
