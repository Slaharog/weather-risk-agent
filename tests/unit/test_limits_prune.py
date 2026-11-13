from weather_risk.api.limits import RateLimiter


def test_per_client_history_is_dropped_when_the_day_rolls_over():
    limiter = RateLimiter(per_minute=5, per_day=100)
    for i in range(50):
        limiter.allow(f"203.0.113.{i}", now=1_000.0)
    limiter.allow("198.51.100.1", now=1_000.0 + 86_400)
    assert len(limiter._recent) == 1
