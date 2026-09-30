#!/usr/bin/env bash
set -Eeuo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.production.yml}"
env_file="${ENV_FILE:-.env.production}"
export KORE_ENV_FILE="${env_file}"
backup_dir="${BACKUP_DIR:-backups}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="${backup_dir}/kore_agro_${timestamp}.dump"
compose=(docker compose --env-file "${env_file}" -f "${compose_file}")

mkdir -p "${backup_dir}"

"${compose[@]}" exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --no-owner --no-acl --dbname="$POSTGRES_DB" --username="$POSTGRES_USER"' \
  > "${output}"

if [[ ! -s "${output}" ]]; then
  echo "Backup vacio: ${output}" >&2
  exit 1
fi

(
  cd "${backup_dir}"
  sha256sum "$(basename "${output}")" > "$(basename "${output}").sha256"
)

if [[ "${retention_days}" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  find "${backup_dir}" -type f \( -name 'kore_agro_*.dump' -o -name 'kore_agro_*.dump.sha256' \) \
    -mtime "+${retention_days}" -delete
fi

echo "Backup creado: ${output}"
