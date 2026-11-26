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

`src/data/scripts/validate.py` checks the built views and compares them with `topic_page`. `scripts/snapshot_baseline.sh` downloads the views in production (for sectors, only the live dataset version) into `validation_data/baseline`, which `validate.py --baseline validation_data/baseline` compares against.

The sectors view is too large for Observable, so CI publishes it to GCS. `cdn_files/sectors_view/<version>/` goes to `sources/sectors_view/<version>/`, where `<version>` is a hash of the partitions and the directory is never overwritten. CI then uploads `sources/sectors_view_options.json`, which names the live version. Each deploy keeps the new and the previous version and deletes older ones. `scripts/upload_sectors_partition.sh` uploads a local build by hand and deletes nothing.

A day or more after the first versioned deploy, delete the unversioned partitions with `gsutil -m rm -r 'gs://data-apps-one-data/sources/sectors_view/donor_slug=*'`.

The `topic_page` outputs are not built in CI. Regenerate them with `PYTHONPATH=. uv run python -m src.data.topic_page.run_all`. The ODA article on data.one.org reads them from `main` through CMS data sources: `tests/data/test_topic_page_contract.py` lists the files, columns and key numbers it depends on, so a rename there needs the matching change in the CMS.
