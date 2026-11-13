from fastapi.testclient import TestClient

from weather_risk.api.app import app

client = TestClient(app)


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert {s["name"] for s in body["data_sources"]} >= {"FEMA National Risk Index"}


def test_hubs_lists_all_16():
    assert len(client.get("/api/hubs").json()) == 16


def test_rankings_midwest_winter():
    body = client.get("/api/rankings", params={"hazard": "winter", "region": "Midwest"}).json()
    assert len(body["rankings"]) == 7
    assert body["rankings"][0]["rank"] == 1


def test_rankings_reject_unknown_values():
    assert client.get("/api/rankings", params={"hazard": "earthquake"}).status_code == 422
    assert client.get("/api/rankings", params={"region": "Mars"}).status_code == 422


def test_breakdown_matches_rankings_and_404s_for_unknown_hub():
    b = client.get("/api/hubs/dallas/breakdown").json()
    overall = client.get("/api/rankings").json()["rankings"]
    dallas = next(r for r in overall if r["hub_id"] == "dallas")
    assert b["overall_score"] == dallas["score"]
    assert b["overall_rank"] == dallas["rank"]
    assert len(b["hazards"]) == 5
    assert client.get("/api/hubs/boston/breakdown").status_code == 404
