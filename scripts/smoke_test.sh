#!/usr/bin/env bash
set -Eeuo pipefail

base_url="${BASE_URL:?Define BASE_URL, por ejemplo https://agro.example.com}"
base_url="${base_url%/}"
tenant_base_url="${TENANT_BASE_URL:-}"
tenant_base_url="${tenant_base_url%/}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

health="$(curl --fail --silent --show-error --dump-header "${tmp_dir}/headers" "${base_url}/health/")"
readiness="$(curl --fail --silent --show-error "${base_url}/readiness/")"

grep -q '"status": "ok"' <<< "${health}"
grep -q '"database": "ready"' <<< "${readiness}"
grep -qi '^content-security-policy:' "${tmp_dir}/headers"
grep -qi '^x-content-type-options: nosniff' "${tmp_dir}/headers"
grep -qi '^x-frame-options:' "${tmp_dir}/headers"

if [[ "${base_url}" == https://* ]]; then
  grep -qi '^strict-transport-security:' "${tmp_dir}/headers"
fi

if [[ -n "${tenant_base_url}" ]]; then
  curl --fail --silent --show-error "${tenant_base_url}/login/" > "${tmp_dir}/tenant-login"
  grep -q 'Entrar a la finca' "${tmp_dir}/tenant-login"

  field_status="$(
    curl --silent --show-error \
      --dump-header "${tmp_dir}/field-headers" \
      --output /dev/null \
      --write-out '%{http_code}' \
      "${tenant_base_url}/field/"
  )"
  [[ "${field_status}" == "302" ]]
  grep -qi '^location: /login/?next=/field/' "${tmp_dir}/field-headers"
fi

echo "KORE Agro responde correctamente en ${base_url}"
if [[ -n "${tenant_base_url}" ]]; then
  echo "Acceso de finca y PWA verificados en ${tenant_base_url}"
fi
