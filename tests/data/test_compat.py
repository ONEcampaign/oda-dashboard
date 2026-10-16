"""Tests for the oda-reader area-code patch."""

import json

from oda_reader.schemas import dac1_translation, dac2_translation

from src.data._compat import _corrections_last


def test_corrected_codes_win_the_inversion(tmp_path):
    corrections = tmp_path / "corrections.json"
    corrections.write_text(json.dumps({"918": "4EU001"}))
    original = lambda: {918: "4EU001", 4: "FRA", 20918: "4EU001"}  # noqa: E731

    mapping = _corrections_last(original, corrections)()
    inverted = {area: code for code, area in mapping.items()}

    assert inverted["4EU001"] == 918
    assert mapping[4] == "FRA"


def test_patched_oda_reader_maps_eu_institutions_to_918():
    for module in (dac1_translation, dac2_translation):
        inverted = {area: code for code, area in module.area_code_mapping().items()}
        assert inverted["4EU001"] == 918
