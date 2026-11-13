from weather_risk.hubs import Region, hubs_in_region, load_hubs


def test_exactly_16_hubs_with_unique_ids():
    hubs = load_hubs()
    assert len(hubs) == 16
    assert len({h.id for h in hubs}) == 16


def test_county_fips_is_five_digits():
    for hub in load_hubs():
        assert len(hub.county_fips) == 5 and hub.county_fips.isdigit(), hub.id


def test_region_is_derived_from_state():
    by_id = {h.id: h for h in load_hubs()}
    assert by_id["dallas"].region == Region.SOUTH
    assert by_id["denver"].region == Region.WEST
    assert by_id["newark"].region == Region.NORTHEAST
    assert by_id["chicago"].region == Region.MIDWEST


def test_midwest_hubs():
    ids = {h.id for h in hubs_in_region(Region.MIDWEST)}
    assert ids == {
        "chicago", "indianapolis", "columbus", "minneapolis", "kansas-city", "st-louis", "detroit"
    }
