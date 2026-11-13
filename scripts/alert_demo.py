"""Trigger the alert demo (or a real check) on a deployed service, without pasting the token.

Usage: uv run python scripts/alert_demo.py https://<app>.up.railway.app [--check]

Reads ALERT_ADMIN_TOKEN from the environment or .env (the same value as the Railway variable)
and never prints it. Exit codes: 0 ok, 1 no token configured, 2 the service refused or failed.
"""

import argparse
import ssl
import sys

import httpx

from weather_risk.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url")
    parser.add_argument("--check", action="store_true", help="run a real check instead of the demo")
    args = parser.parse_args()

    token = get_settings().alert_admin_token
    if token is None:
        print("ALERT_ADMIN_TOKEN is not set in the environment or .env.", file=sys.stderr)
        return 1

    endpoint = "check" if args.check else "demo"
    url = f"{args.base_url.rstrip('/')}/api/alerts/{endpoint}"
    with httpx.Client(timeout=180, verify=ssl.create_default_context()) as http:  # a check takes ~1 min
        response = http.post(url, headers={"Authorization": f"Bearer {token.get_secret_value()}"})
    if response.status_code != 200:
        is_json = response.headers.get("content-type", "").startswith("application/json")
        detail = response.json().get("detail", "") if is_json else ""
        print(f"POST /api/alerts/{endpoint} -> HTTP {response.status_code}: {detail}", file=sys.stderr)
        return 2

    s = response.json()
    print(f"{'Demo check' if s['kind'] == 'demo' else 'Check'} #{s['check_id']}: {s['status']}, "
          f"{s['hubs_checked']} hubs, {s['alerts_raised']} alerts, {s['delivered']} delivered, "
          f"{s['delivery_failed']} delivery failed" + (", baseline recorded" if s["baseline"] else ""))
    for a in s["alerts"]:
        print(f"{'[demo] ' if a['is_demo'] else ''}{a['hub_name']:<16} {a['metric']:<14} "
              f"{a['old_value']:5.1f} -> {a['new_value']:5.1f}  ({a['change']:+.1f})   "
              f"{a['delivery_status']}")
    print(f"See {args.base_url.rstrip('/')}/alerts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
