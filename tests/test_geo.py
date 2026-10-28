import pytest
from ted_harvester.geo import CoordinateError, NutsGazetteer, resolve_location, validate_lonlat


def test_single_nuts3_resolves_to_25832(gaz):
    loc = resolve_location(["DEA13", "DEU", "DEA13"], gaz)
    assert loc.status == "resolved" and loc.precision == "nuts3_representative_point" and loc.warning is None
    assert 340000 < loc.x < 420000 and 5600000 < loc.y < 5750000


@pytest.mark.parametrize("codes,reason", [
    ([], "no_place_of_performance"), (["DEU", "anyw"], "country_level_only"), (["DEA1", "DEU"], "nuts_below_level3"),
    (["DEA11", "DEA22"], "ambiguous_multiple_nuts3"), (["DEA77"], "nuts3_not_in_gazetteer")])
def test_unresolved_reasons(gaz, codes, reason):
    loc = resolve_location(codes, gaz)
    assert loc.status == "unresolved" and loc.reason == reason and loc.x is None


@pytest.mark.parametrize("code", ["DEB11", "DEA99"])
def test_invalid_gazetteer_coordinates_rejected(gaz, code):
    loc = resolve_location([code], gaz)
    assert loc.status == "unresolved" and loc.reason.startswith("invalid_coordinates") and loc.x is None


@pytest.mark.parametrize("lon,lat", [(200, 10), (10, 95), ("a", 1), (None, 1), (float("nan"), 1), (0, 0)])
def test_validate_lonlat_rejects(lon, lat):
    with pytest.raises(CoordinateError):
        validate_lonlat(lon, lat)


def test_outside_area_of_use_flagged(gaz):
    assert resolve_location(["FR104"], gaz).warning == "outside_epsg25832_area_of_use"


def test_missing_gazetteer_file(tmp_path):
    assert NutsGazetteer.from_csv(tmp_path / "nope.csv").rows == {}
