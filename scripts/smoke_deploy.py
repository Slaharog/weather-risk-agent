"""Smoke-check a running deployment: health, an LLM-free ranking, and one chat question.

Usage: python scripts/smoke_deploy.py https://<your-app>.up.railway.app
Prints a short summary and exits non-zero on the first failure.
"""

import sys

import httpx


def main(base: str) -> None:
    base = base.rstrip("/")
    with httpx.Client(timeout=90) as http:
        health = http.get(f"{base}/api/health")
        health.raise_for_status()
        print("health  ", health.status_code, health.json())

        ranks = http.get(f"{base}/api/rankings", params={"hazard": "winter", "region": "Midwest"})
        ranks.raise_for_status()
        rows = ranks.json()["rankings"]
        print("rankings", ranks.status_code, [(r["rank"], r["hub_id"], r["score"]) for r in rows[:3]])

        chat = http.post(f"{base}/api/chat",
                         json={"message": "Which hubs in the Midwest are most exposed to winter disruption?"})
        chat.raise_for_status()
        answer = chat.json()["answer"]
        print("chat    ", chat.status_code, answer["answer_type"], "|", answer["narrative"][:200])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
