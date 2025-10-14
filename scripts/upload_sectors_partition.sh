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

echo "Uploading '${LOCAL_DIR}' → '${GCS_PATH}'"
gsutil -m rsync -r -d "${LOCAL_DIR}" "${GCS_PATH}"

LEGACY_FILE="cdn_files/sectors_view.parquet"
if [ -f "${LEGACY_FILE}" ]; then
    echo "Uploading legacy single-file parquet '${LEGACY_FILE}'"
    gsutil cp "${LEGACY_FILE}" "${GCS_PATH}.parquet"
fi

echo "Upload complete."
