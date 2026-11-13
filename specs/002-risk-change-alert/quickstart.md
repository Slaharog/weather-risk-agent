# Quickstart: Risk-Change Alert

## Configuration (env or `.env`)

| Variable | Default | Railway value |
|---|---|---|
| `ALERT_INTERVAL_HOURS` | `0` (scheduler off) | `24` |
| `ALERT_THRESHOLD` | `2.0` | `2.0` |
| `ALERT_WEBHOOK_URL` | unset (alerts only recorded and logged) | your webhook.site URL |
| `ALERT_ADMIN_TOKEN` | unset (trigger endpoints disabled) | a long random string |

The database is `DATA_DIR/alerts.sqlite` (locally `data/live/alerts.sqlite`, git-ignored).

## Validate locally

```bash
uv run python -m pytest                                  # all tests, including the new detection tests
uv run python -m weather_risk alerts demo                # 2 demo alerts: Dallas heat +7.5, Houston hurricane -5.0
uv run python -m weather_risk alerts list                # both listed with [demo]
uv run python -m weather_risk alerts check               # first real check: baseline, 0 alerts (fetches live data, about 1 min)
uv run python -m weather_risk alerts check               # second: 0 alerts unless the providers revised data
uv run python -m weather_risk eval                       # still 20/20
```

Expected:
- The demo does not change `wra rank` output.
- After the demo, a real check still reports `baseline` (first) or 0 alerts, never alerts caused by the demo.

## Validate on Railway

```bash
python scripts/smoke_deploy.py https://weather-risk-agent-production.up.railway.app
# then, with the token from Railway variables (do not commit it):
POST /api/alerts/demo   with header Authorization: Bearer $ALERT_ADMIN_TOKEN   -> 200, 2 alerts
GET  /api/alerts                                                               -> the 2 demo alerts, webhook_configured true
GET  /alerts (in a browser)                                                     -> the same 2 alerts with a "demo" badge
# webhook.site shows 2 POSTs whose text starts with [DEMO]
POST /api/alerts/demo   without the header                                     -> 403
```

Restart check (SC-203): redeploy, then `GET /api/alerts` still lists the same alerts.
