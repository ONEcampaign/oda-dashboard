#!/usr/bin/env bash
# Snapshot the four dashboard views as deployed in production, as a parity baseline.
#
# Writes validation_data/baseline/<view>/ for every view, the layout load_view reads:
#   financing_view, recipients_view, gender_view: data.parquet + options.json
#   sectors_view: the hive partitions of the live dataset version, flat (no version
#     directory), + options.json
# plus README.txt recording the date and the pipeline package versions.
#
# Needs an authenticated gsutil (gcloud auth login). Not for CI.
#
# Usage: scripts/snapshot_baseline.sh [output_dir]

set -euo pipefail

BUCKET="gs://data-apps-one-data"
APP_URL="${BUCKET}/oda-dashboard"
SECTORS_URL="${BUCKET}/sources/sectors_view"
SECTORS_OPTIONS_URL="${BUCKET}/sources/sectors_view_options.json"
OUT_DIR="${1:-validation_data/baseline}"

# The deployed pages that load each Observable view.
OBSERVABLE_VIEWS=(financing_view recipients_view gender_view)
PAGES=(index.html recipients.html gender.html)

if ! command -v gsutil >/dev/null 2>&1; then
    echo "Error: gsutil is not installed or not on PATH." >&2
    exit 1
fi

# The hashed file the deployed pages reference for a view, e.g. data.4004128e.parquet;
# empty if no page references one.
referenced_file() {
    local view="$1" stem="$2" ext="$3" pages_html="$4"
    local path
    path="$(grep -o "_file/data/scripts/${view}/${stem}\.[0-9a-f]*\.${ext}" <<<"${pages_html}" \
        | sort -u | head -n 1 || true)"
    echo "${path##*/}"
}

# Copy one hashed view file to a fixed name in the view's baseline directory.
snapshot_file() {
    local view="$1" stem="$2" ext="$3" target="$4" pages_html="$5"
    local name
    name="$(referenced_file "${view}" "${stem}" "${ext}" "${pages_html}")"
    # The newest file in the bucket need not be the live one, so there is no fallback.
    if [ -z "${name}" ]; then
        echo "Error: no deployed page references a ${view} ${stem}.*.${ext} file." >&2
        exit 1
    fi
    echo "${view}: ${name} -> ${target}"
    gsutil cp "${APP_URL}/_file/data/scripts/${view}/${name}" "${OUT_DIR}/${view}/${target}"
}

pages_html=""
for page in "${PAGES[@]}"; do
    pages_html+="$(gsutil cat "${APP_URL}/${page}")"$'\n'
done

for view in "${OBSERVABLE_VIEWS[@]}"; do
    rm -rf "${OUT_DIR:?}/${view}"
    mkdir -p "${OUT_DIR}/${view}"
    snapshot_file "${view}" data parquet data.parquet "${pages_html}"
    snapshot_file "${view}" options json options.json "${pages_html}"
done

rm -rf "${OUT_DIR:?}/sectors_view"
mkdir -p "${OUT_DIR}/sectors_view"
# cp, not cat: cp decompresses the gzip-encoded options.
gsutil cp "${SECTORS_OPTIONS_URL}" "${OUT_DIR}/sectors_view/options.json"
sectors_version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("dataset_version") or "")' \
    "${OUT_DIR}/sectors_view/options.json")"
if [ -n "${sectors_version}" ]; then
    echo "sectors_view: ${SECTORS_URL}/${sectors_version} -> ${OUT_DIR}/sectors_view"
    gsutil -m rsync -r "${SECTORS_URL}/${sectors_version}" "${OUT_DIR}/sectors_view"
else
    # Live options from before versioning: the partitions sit at the root.
    echo "sectors_view: ${SECTORS_URL} (unversioned) -> ${OUT_DIR}/sectors_view"
    gsutil -m rsync -r -x '^(?!donor_slug=).*' "${SECTORS_URL}" "${OUT_DIR}/sectors_view"
fi

{
    echo "Production snapshot of the dashboard views, taken $(date -u +'%Y-%m-%dT%H:%M:%SZ')."
    echo "Source: ${APP_URL} and ${BUCKET}/sources."
    echo
    echo "Local pipeline package versions at snapshot time (not necessarily those of the"
    echo "production build):"
    uv pip show oda-data oda-reader pydeflate | grep -E '^(Name|Version):'
} >"${OUT_DIR}/README.txt"

echo "Baseline written to ${OUT_DIR}."
