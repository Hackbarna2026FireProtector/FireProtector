"""What /assets puts on the wire, checked without a database.

The contract is strict about three things and the consumer rejects a response
that breaks them: asset_id must be unique, name must be at most 120 characters,
and value and vulnerability must sit inside their ranges.
"""

import pytest
from fastapi import HTTPException

from app.routers.assets import _clean_name, _feature, _positive_int
from app.vulnerability import vulnerability

ROW = {
    "wire_id": "asset-42",
    "asset_type": "shed",
    "name": "Cal Ratat",
    "value": 7,
    "source": "INSPIRE",
    "geometry": {"type": "Point", "coordinates": [1.4, 41.4]},
}


def row(**overrides):
    return {**ROW, **overrides}


# ------------------------------------------------------------------ names ---


def test_name_passes_through_unchanged() -> None:
    assert _clean_name("Hospital Comarcal") == "Hospital Comarcal"


def test_name_is_capped_at_the_contract_length() -> None:
    cleaned = _clean_name("x" * 400)

    assert len(cleaned) == 120
    assert cleaned.endswith("…")


def test_control_characters_are_stripped() -> None:
    assert _clean_name("Escola\x00 Sant\tJordi\n") == "Escola SantJordi"


@pytest.mark.parametrize("value", [None, "", "   ", "\x00"])
def test_empty_name_gets_a_placeholder(value) -> None:
    # The contract requires a name on every feature, so there is no null here.
    assert _clean_name(value) == "unnamed"


# ----------------------------------------------------------------- ranges ---


def test_feature_carries_the_rows_own_values() -> None:
    feature = _feature(row())

    assert feature.properties.asset_id == "asset-42"
    assert feature.properties.asset_type == "shed"
    assert feature.properties.value == 7
    assert feature.geometry == ROW["geometry"]


@pytest.mark.parametrize("stored, expected", [(0, 1.0), (-5, 1.0), (1000, 100.0), (50, 50.0)])
def test_value_is_pulled_into_the_contracts_range(stored, expected) -> None:
    assert _feature(row(value=stored)).properties.value == expected


@pytest.mark.parametrize("returned, expected", [(-1.0, 0.0), (2.0, 1.0), (0.25, 0.25)])
def test_vulnerability_is_clamped(monkeypatch, returned, expected) -> None:
    """A replacement model that returns nonsense must not break the response."""
    monkeypatch.setattr("app.routers.assets.vulnerability", lambda _: returned)

    assert _feature(row()).properties.vulnerability == expected


def test_the_stub_is_inside_the_contracts_range() -> None:
    assert 0.0 <= vulnerability(ROW) <= 1.0


# ------------------------------------------------------------- parameters ---


def test_missing_parameter_falls_back_to_the_default() -> None:
    assert _positive_int(None, "limit", 1000, minimum=1) == 1000
    assert _positive_int("", "limit", 1000, minimum=1) == 1000


def test_parameter_is_read_as_an_integer() -> None:
    assert _positive_int("250", "limit", 1000, minimum=1) == 250


@pytest.mark.parametrize(
    "raw, minimum, message",
    [
        ("abc", 1, "whole number"),
        ("1.5", 1, "whole number"),
        ("0", 1, "1 or more"),
        ("-5", 1, "1 or more"),
        ("-1", 0, "0 or more"),
    ],
)
def test_bad_parameters_raise_a_400(raw, minimum, message: str) -> None:
    with pytest.raises(HTTPException) as caught:
        _positive_int(raw, "limit", 1000, minimum=minimum)

    # 400, not FastAPI's usual 422: the contract knows only 400 and 500.
    assert caught.value.status_code == 400
    assert message in caught.value.detail
