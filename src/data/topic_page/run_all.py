"""Regenerate every topic_page output the scripts write.

Run with ``PYTHONPATH=. uv run python -m src.data.topic_page.run_all``. Each script also
runs on its own as ``python -m src.data.topic_page.<script>``.
"""

from src.data.topic_page import overview, total_excl_donor, total_oda_gni


def main() -> None:
    """Run each topic page script in turn."""
    total_oda_gni.main()
    total_excl_donor.main()
    overview.main()


if __name__ == "__main__":
    main()
