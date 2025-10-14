#!/usr/bin/env bash

set -euo pipefail

LOCAL_DIR=${1:-"cdn_files/sectors_view"}
GCS_PATH=${2:-"gs://data-apps-one-data/sources/sectors_view"}

if ! command -v gsutil >/dev/null 2>&1; then
    echo "Error: gsutil is not installed or not on PATH." >&2
    exit 1
fi

if [ ! -d "${LOCAL_DIR}" ]; then
    echo "Error: local directory '${LOCAL_DIR}' does not exist." >&2
    exit 1
fi

echo "Clearing existing data in '${GCS_PATH}'..."
gsutil -m rm -r "${GCS_PATH}/**" 2>/dev/null || true

echo "Uploading '${LOCAL_DIR}' → '${GCS_PATH}'"
gsutil -m rsync -r -d "${LOCAL_DIR}" "${GCS_PATH}"

echo "Upload complete."
