#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: CONFIRM_RESTORE=RESTORE_KORE_AGRO $0 backups/archivo.dump" >&2
  exit 2
fi

if [[ "${CONFIRM_RESTORE:-}" != "RESTORE_KORE_AGRO" ]]; then
  echo "Restauracion cancelada: define CONFIRM_RESTORE=RESTORE_KORE_AGRO." >&2
  exit 2
fi

backup_file="$1"
compose_file="${COMPOSE_FILE:-docker-compose.production.yml}"
env_file="${ENV_FILE:-.env.production}"
export KORE_ENV_FILE="${env_file}"
compose=(docker compose --env-file "${env_file}" -f "${compose_file}")

if [[ ! -f "${backup_file}" ]]; then
  echo "No existe el backup: ${backup_file}" >&2
  exit 2
fi

if [[ -f "${backup_file}.sha256" ]]; then
  (
    cd "$(dirname "${backup_file}")"
    sha256sum -c "$(basename "${backup_file}").sha256"
  )
fi

restart_apps() {
  "${compose[@]}" up -d web worker >/dev/null
}

"${compose[@]}" stop web worker
trap restart_apps EXIT

"${compose[@]}" exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error --dbname="$POSTGRES_DB" --username="$POSTGRES_USER"' \
  < "${backup_file}"

"${compose[@]}" run --rm migrate
trap - EXIT
restart_apps

echo "Restauracion completada desde: ${backup_file}"
