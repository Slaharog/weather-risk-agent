from weather_risk.api.limits import RateLimiter


def test_per_client_limit_within_a_minute():
    lim = RateLimiter(per_minute=2, per_day=100)
    assert lim.allow("a", now=0) and lim.allow("a", now=1)
    assert not lim.allow("a", now=2)
    assert lim.allow("b", now=2)  # other clients are unaffected


def test_window_slides_after_60_seconds():
    lim = RateLimiter(per_minute=1, per_day=100)
    assert lim.allow("a", now=0)
    assert not lim.allow("a", now=59)
    assert lim.allow("a", now=61)


def test_global_daily_cap_applies_to_everyone():
    lim = RateLimiter(per_minute=100, per_day=2)
    assert lim.allow("a", now=0) and lim.allow("b", now=1)
    assert not lim.allow("c", now=2)
    assert lim.allow("c", now=86_401)  # next day
