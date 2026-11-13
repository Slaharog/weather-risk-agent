# Contract: Webhook payload

One `POST` per alert to `ALERT_WEBHOOK_URL`, with `Content-Type: application/json`, a 5 s timeout and up to 3 attempts (waits of 1 s and 2 s). A non-2xx response or any exception is a failed attempt.

```json
{
  "text": "[DEMO] Dallas, TX heat score rose 7.5 points: 76.6 -> 84.1 (threshold 2.0). Data: FEMA NRI December 2025 release (retrieved 2026-11-13); Open-Meteo ERA5 2016-01-01 to 2025-12-31 (retrieved 2026-11-13).",
  "alert": {
    "id": 3, "hub_id": "dallas", "hub_name": "Dallas, TX", "metric": "heat",
    "old_value": 76.6, "new_value": 84.1, "change": 7.5, "threshold": 2.0,
    "detected_at": "2026-11-13T17:40:00Z", "is_demo": true,
    "data_retrieved": [ ... ]
  }
}
```

- `text` starts with `[DEMO] ` for demo alerts and has no prefix for real ones. It is built by code from the alert fields: every number comes from the alert row.
- Slack incoming webhooks show `text` and ignore `alert`. webhook.site shows the whole body.
