#!/usr/bin/env bash
set -euo pipefail

# Downloads the private, standardized `db-upgrader` (DbUp) binary published
# from austinkoske/utils/db-upgrader into ./.tools/db-upgrader. Every project
# database repo pulls the same binary instead of vendoring compiled DbUp
# binaries per-project.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${ROOT_DIR}/.tools/db-upgrader"
PACKAGE_NAME="${DB_UPGRADER_PACKAGE_NAME:-db-upgrader}"
PACKAGE_VERSION="${DB_UPGRADER_VERSION:-}"
PROJECT_ID="${DB_UPGRADER_PROJECT_ID:-82573706}" # austinkoske/utils/db-upgrader
API_V4_URL="${CI_API_V4_URL:-https://gitlab.com/api/v4}"
ARCHIVE_PATH="${TOOLS_DIR}/db-upgrader-linux-x64.tar.gz"
UPGRADER_PATH="${TOOLS_DIR}/DbUp"

if [ -z "${PACKAGE_VERSION}" ]; then
  echo "Set DB_UPGRADER_VERSION to a published db-upgrader package version, for example v0.1.0." >&2
  exit 1
fi

PACKAGE_URL="${API_V4_URL}/projects/${PROJECT_ID}/packages/generic/${PACKAGE_NAME}/${PACKAGE_VERSION}/db-upgrader-linux-x64.tar.gz"
GLAB_API_PATH="projects/${PROJECT_ID}/packages/generic/${PACKAGE_NAME}/${PACKAGE_VERSION}/db-upgrader-linux-x64.tar.gz"

auth_header() {
  if [ -n "${DEPLOY_TOKEN:-}" ]; then
    printf 'Deploy-Token: %s' "${DEPLOY_TOKEN}"
    return 0
  fi

  if [ -n "${CI_JOB_TOKEN:-}" ]; then
    printf 'JOB-TOKEN: %s' "${CI_JOB_TOKEN}"
    return 0
  fi

  if [ -n "${GITLAB_TOKEN:-}" ]; then
    printf 'PRIVATE-TOKEN: %s' "${GITLAB_TOKEN}"
    return 0
  fi

  if [ -n "${GLAB_TOKEN:-}" ]; then
    printf 'PRIVATE-TOKEN: %s' "${GLAB_TOKEN}"
    return 0
  fi

  return 1
}

if [ -x "${UPGRADER_PATH}" ]; then
  echo "${UPGRADER_PATH}"
  exit 0
fi

mkdir -p "${TOOLS_DIR}"
cleanup() {
  rm -f "${ARCHIVE_PATH}"
}
trap cleanup EXIT

HEADER_VALUE="$(auth_header || true)"
if [ -n "${HEADER_VALUE}" ]; then
  curl --fail --location \
    --header "${HEADER_VALUE}" \
    --output "${ARCHIVE_PATH}" \
    "${PACKAGE_URL}"
elif command -v glab >/dev/null 2>&1; then
  glab api -X GET "${GLAB_API_PATH}" > "${ARCHIVE_PATH}"
else
  echo "Unable to authenticate to the private db-upgrader package." >&2
  echo "Set CI_JOB_TOKEN, GITLAB_TOKEN, GLAB_TOKEN, or authenticate with glab." >&2
  exit 1
fi

tar -C "${TOOLS_DIR}" -xzf "${ARCHIVE_PATH}"
chmod +x "${UPGRADER_PATH}"

echo "${UPGRADER_PATH}"
