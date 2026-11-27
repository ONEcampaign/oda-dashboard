#!/usr/bin/env bash
# Upload a local sectors build by hand, as deploy.yml does. The version directory its options
# name goes up first, then the options. Nothing is deleted. Old versions are pruned only by
# deploy.yml. Do not run this while a deploy is in progress (gh run list -w deploy.yml
# -s in_progress): its prune step can delete a version mid-upload, and its options upload
# replaces yours.
#
# Usage: scripts/upload_sectors_partition.sh [local_dir] [gcs_path]
#   local_dir: the built dataset, default cdn_files/sectors_view
#   gcs_path:  where versions live, default gs://data-apps-one-data/sources/sectors_view
# The options file sits beside each, at <dir>/../sectors_view_options.json.

set -euo pipefail

LOCAL_DIR=${1:-"cdn_files/sectors_view"}
GCS_PATH=${2:-"gs://data-apps-one-data/sources/sectors_view"}
LOCAL_OPTIONS="$(dirname "${LOCAL_DIR}")/sectors_view_options.json"
GCS_OPTIONS="$(dirname "${GCS_PATH}")/sectors_view_options.json"

if ! command -v gsutil >/dev/null 2>&1; then
    echo "Error: gsutil is not installed or not on PATH." >&2
    exit 1
fi

if [ ! -f "${LOCAL_OPTIONS}" ]; then
    echo "Error: options file '${LOCAL_OPTIONS}' does not exist." >&2
    exit 1
fi

VERSION="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["dataset_version"])' "${LOCAL_OPTIONS}")"
if [ ! -d "${LOCAL_DIR}/${VERSION}" ]; then
    echo "Error: '${LOCAL_OPTIONS}' names version ${VERSION}, but '${LOCAL_DIR}/${VERSION}' does not exist." >&2
    exit 1
fi

echo "Uploading '${LOCAL_DIR}/${VERSION}' → '${GCS_PATH}/${VERSION}'"
# -c compares checksums, so an already uploaded version is not sent again.
gsutil -m -h "Cache-Control:public, max-age=31536000, immutable" \
    rsync -r -c "${LOCAL_DIR}/${VERSION}" "${GCS_PATH}/${VERSION}"

# After the data, so every pair the options list already resolves.
echo "Uploading '${LOCAL_OPTIONS}' → '${GCS_OPTIONS}'"
gsutil -h "Cache-Control:no-cache" cp -Z "${LOCAL_OPTIONS}" "${GCS_OPTIONS}"

echo "Upload complete."
