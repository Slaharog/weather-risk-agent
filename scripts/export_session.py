"""Export the Claude Code session transcript(s) for submission (deliverable: the full AI session).

Writes:
    docs/session/raw/*.jsonl   the original transcripts (main session + review subagents), redacted
    docs/session/session.md    a readable version: user messages, assistant text, tool calls

Redaction: OpenAI-style API keys and e-mail addresses (except the public noreply/example ones).
Run again at the end of the session to capture everything: `python scripts/export_session.py`.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "session"
PROJECT_DIR = Path.home() / ".claude" / "projects" / "C--Users-yt141-OneDrive-Desktop-interview-for-moveo"

KEY = re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
KEEP_EMAILS = {"noreply@anthropic.com", "ceo@example.com", "you@example.com"}
MAX_TOOL_INPUT = 400


def redact(text: str) -> str:
    text = KEY.sub("[REDACTED-API-KEY]", text)
    return EMAIL.sub(lambda m: m.group(0) if m.group(0) in KEEP_EMAILS or "noreply.github" in m.group(0)
                     else "[REDACTED-EMAIL]", text)


def transcripts() -> list[Path]:
    main = sorted(PROJECT_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    subs = sorted(PROJECT_DIR.glob("*/subagents/*.jsonl"))
    return main + subs


def blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def to_markdown(path: Path) -> list[str]:
    lines = [f"\n---\n\n# Transcript: `{path.name}`\n"]
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        role = entry.get("type")
        msg = entry.get("message") or {}
        if role not in ("user", "assistant") or not msg:
            continue
        for b in blocks(msg.get("content")):
            kind = b.get("type")
            if kind == "text" and b.get("text", "").strip():
                text = b["text"].strip()
                if role == "user" and text.startswith("<system-reminder>"):
                    continue  # harness context, not something the user typed
                lines.append(f"\n**{'User' if role == 'user' else 'Assistant'}:**\n\n{text}\n")
            elif kind == "tool_use":
                args = json.dumps(b.get("input", {}), ensure_ascii=False)
                if len(args) > MAX_TOOL_INPUT:
                    args = args[:MAX_TOOL_INPUT] + " …"
                lines.append(f"\n> 🔧 `{b.get('name')}` {args}\n")
    return lines


def main() -> int:
    files = transcripts()
    if not files:
        print(f"No transcripts found in {PROJECT_DIR}", file=sys.stderr)
        return 1
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    md = ["# AI session log\n",
          "The complete Claude Code session that planned and built this project (spec-driven "
          "development with Spec Kit), followed by the two review subagents. Tool calls are shown "
          "with truncated inputs; tool outputs are omitted here and kept in `raw/`. "
          "API keys and personal e-mail addresses are redacted.\n"]
    for f in files:
        text = redact(f.read_text(encoding="utf-8"))
        (OUT / "raw" / f.name).write_text(text, encoding="utf-8")
        md += to_markdown(OUT / "raw" / f.name)
    (OUT / "session.md").write_text(redact("".join(md)), encoding="utf-8")
    print(f"Exported {len(files)} transcript(s) to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
