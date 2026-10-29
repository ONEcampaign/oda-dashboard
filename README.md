# ODA Dashboard

An [interactive tool](https://data.one.org/tools/dashboards/oda) to explore Official Development Assistance (ODA) Data.

`src` contains the [Observable Framework](https://observablehq.com/framework/) project files.

`src/data` contains the data preparation scripts for the app.

## OECD data

The pipeline reads OECD data through oda-data 3, from four bulk files: `CRS.parquet`, `MultiSystem.zip`, `Table1_Data.zip` (DAC1) and `Table2a_Data.zip` (DAC2A). The OECD file server blocks scripted downloads, so CI takes them from the `oecd-bulk-data` GitHub release, where they are uploaded by hand.

To build locally, download the four files in a browser into one directory, then register them and convert them once:

```bash
PYTHONPATH=. uv run python src/data/scripts/register_bulk_files.py --dir <dir>
PYTHONPATH=. uv run python src/data/scripts/prewarm_cache.py
```

The cache lives in `src/data/cache/oda-reader`. Set `ODA_READER_CACHE_DIR` to use another directory.

`src/data/scripts/validate.py` checks the built views and compares them with `topic_page`. `scripts/snapshot_baseline.sh` downloads the views in production into `validation_data/baseline`, which `validate.py --baseline validation_data/baseline` compares against.

The `topic_page` outputs are not built in CI. Regenerate them with `PYTHONPATH=. uv run python -m src.data.topic_page.run_all`.
