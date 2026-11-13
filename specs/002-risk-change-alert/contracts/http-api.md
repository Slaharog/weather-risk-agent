# Contract: Alert HTTP API

Additions to the 001 API (`specs/001-core-risk-agent/contracts/http-api.md`). No existing route changes.

## GET /api/alerts

Public. No LLM. Query: `limit` (1 to 50, default 50).

Response `200`:

```json
{
  "threshold": 2.0,
  "interval_hours": 24,
  "webhook_configured": true,
  "last_check": {
    "id": 7, "kind": "scheduled", "started_at": "2026-11-13T18:00:00Z", "finished_at": "2026-11-13T18:01:02Z",
    "status": "ok", "baseline": false, "hubs_checked": 16, "alerts_raised": 0,
    "fetch_failures": [], "data_retrieved": [{"name": "FEMA National Risk Index", "period": "December 2025 release", "retrieved_at": "2026-11-13"}]
  },
  "alerts": [
    {
      "id": 3, "check_id": 6, "hub_id": "dallas", "hub_name": "Dallas", "metric": "heat",
      "old_value": 76.6, "new_value": 84.1, "change": 7.5,
      "detected_at": "2026-11-13T17:40:00Z", "is_demo": true,
      "delivery_status": "delivered", "delivery_error": null,
      "data_retrieved": [ ... ]
    }
  ]
}
```

- `alerts`: newest first (by id). `last_check`: the newest check of any kind, or `null` if none.
- `webhook_configured` is a boolean only. The URL is never returned (SC-206).

## GET /alerts (page)

Not part of `/api`: it serves `static/alerts.html`, a read-only page that fetches `GET /api/alerts` on load and with a "Reload" button. It renders every value with `textContent`, marks demo alerts with a text badge "demo" (not color alone), and shows the delivery status as text. It has no trigger controls. The chat page header links to it.

## POST /api/alerts/check

Runs a real check now (the same code as the scheduler, with `kind="manual"`). It takes about 1 minute, because it fetches live data.

- Header `Authorization: Bearer <ALERT_ADMIN_TOKEN>` is required.
- `403` if no token is configured on the server, or the token is missing or wrong (constant-time compare). The body does not say which.
- `409` if a check is already running.
- `429` when over the trigger rate limit (2 per minute, 50 per day).

Response `200` (`CheckSummary`):

```json
{ "check_id": 8, "kind": "manual", "status": "ok", "baseline": false, "hubs_checked": 16,
  "alerts_raised": 0, "fetch_failures": [], "delivered": 0, "delivery_failed": 0, "alerts": [] }
```

`alerts` contains the same objects as in `GET /api/alerts`.

## POST /api/alerts/demo

The same auth, 409 and 429 rules. No external data fetch. It returns a `CheckSummary` with `kind="demo"` and, at the default threshold, exactly 2 alerts (Dallas heat +7.5, Houston hurricane −5.0), all `is_demo: true`.
