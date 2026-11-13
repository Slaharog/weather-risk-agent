"""Eval runner: `wra eval` (or `python -m weather_risk eval`).

Runs every case in evals/cases.yaml through the real agent (in-process, no HTTP) and checks
the results deterministically. An optional LLM judge (--judge) scores explanation quality,
reported separately and never counted in the pass rate (constitution Principle IV).
"""

import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from weather_risk.agent.llm import LlmClient, LlmTurn
from weather_risk.agent.loop import Conversation, run_turn
from weather_risk.agent.schemas import ChatResponse
from weather_risk.agent.tools import ToolRegistry
from weather_risk.hubs import load_hubs
from weather_risk.scoring.engine import Engine

EVALS_DIR = Path(__file__).resolve().parent
CASES_FILE = EVALS_DIR / "cases.yaml"
RESULTS_DIR = EVALS_DIR / "results"

NUMBER = re.compile(r"(?<![A-Za-z0-9.])[-−]?\d+(?:,\d{3})*(?:\.\d+)?")


class CountingLlm:
    """Wraps the real client to count model calls and tokens per case."""

    def __init__(self, inner: LlmClient):
        self.inner = inner
        self.calls = self.input_tokens = self.output_tokens = 0

    def respond(self, instructions, input_items, tools, answer_schema) -> LlmTurn:
        turn = self.inner.respond(instructions, input_items, tools, answer_schema)
        self.calls += 1
        self.input_tokens += turn.input_tokens
        self.output_tokens += turn.output_tokens
        return turn


@dataclass
class CaseResult:
    id: str
    category: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    seconds: float = 0.0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    answer_type: str | None = None
    narrative: str | None = None
    tool_calls: list = field(default_factory=list)
    judge: dict | None = None


# ---------- helpers ----------

def numbers_in(text: str) -> list[float]:
    return [float(m.replace(",", "").replace("−", "-")) for m in NUMBER.findall(text)]


def numbers_in_json(value) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, str):
        return numbers_in(value)
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in_json(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in_json(v)]
    return []


def grounded(number: float, allowed: list[float]) -> bool:
    """Within display rounding (1 decimal) of a tool-result number, or the same magnitude
    written without its sign (e.g. '18 °C below' for -18)."""
    return any(abs(number - a) <= 0.051 or abs(abs(number) - abs(a)) <= 0.051 for a in allowed)


def _args_match(expected: dict, actual: dict) -> bool:
    for key, want in expected.items():
        got = actual.get(key)
        if isinstance(want, list):
            if not isinstance(got, list) or set(map(str, want)) != set(map(str, got)):
                return False
        elif str(got) != str(want):
            return False
    return True


# ---------- checks ----------

def check_case(case: dict, resp: ChatResponse, convo_items: list[dict], user_text: str,
               fresh_tools: ToolRegistry, hub_names: dict[str, str]) -> list[str]:
    exp, failures = case.get("expect", {}), []
    if resp.error or resp.answer is None:
        return [f"no answer: {resp.error}"]
    a = resp.answer

    if "answer_type" in exp and a.answer_type != exp["answer_type"]:
        failures.append(f"answer_type {a.answer_type} != {exp['answer_type']}")
    if "answer_type_in" in exp and a.answer_type not in exp["answer_type_in"]:
        failures.append(f"answer_type {a.answer_type} not in {exp['answer_type_in']}")

    for want in exp.get("tools_called", []):
        if not any(c.tool == want["tool"] and _args_match(want.get("args", {}), c.arguments)
                   for c in resp.tool_calls):
            failures.append(f"missing tool call {want['tool']}({want.get('args', {})}); "
                            f"got {[(c.tool, c.arguments) for c in resp.tool_calls]}")

    if "hubs_in_tables" in exp:
        text = " ".join(json.dumps(t.model_dump(), ensure_ascii=False) for t in resp.tables)
        found = {hid for hid, name in hub_names.items() if name in text}
        if found != set(exp["hubs_in_tables"]):
            failures.append(f"hubs in tables {sorted(found)} != {sorted(exp['hubs_in_tables'])}")

    narrative = (a.narrative + " " + (a.clarifying_question or "")).lower()
    if any_of := exp.get("narrative_must_contain_any"):
        if not any(s.lower() in narrative for s in any_of):
            failures.append(f"narrative contains none of {any_of}")
    for s in exp.get("narrative_must_not_contain", []):
        if s.lower() in narrative:
            failures.append(f"narrative contains forbidden '{s}'")

    # Automatic check 1: every table equals a fresh deterministic tool call (numbers_match_engine).
    ok_calls = [c for c in resp.tool_calls]
    fresh_tables = []
    for c in ok_calls:
        out = fresh_tools.execute(c.tool, json.dumps(c.arguments))
        if out.ok and out.table is not None:
            fresh_tables.append(out.table.model_dump())
    if [t.model_dump() for t in resp.tables] != fresh_tables:
        failures.append("numbers_match_engine: tables differ from a fresh engine call")

    # Automatic check 2: narrative numbers are grounded in tool results or the user's question.
    allowed = numbers_in(user_text)
    for item in convo_items:
        if item.get("type") == "function_call_output":
            allowed += numbers_in_json(json.loads(item["output"]))
    ungrounded = [n for n in numbers_in(a.narrative) if not grounded(n, allowed)]
    if ungrounded:
        failures.append(f"narrative_numbers_grounded: {ungrounded} not in tool results")
    return failures


JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["score", "reason"],
    "properties": {"score": {"type": "string", "enum": ["1", "2", "3", "4", "5"]},
                   "reason": {"type": "string"}},
}
JUDGE_PROMPT = ("You grade answers from a weather-risk assistant for logistics analysts. Score 1-5 "
                "how clearly the narrative explains the reasoning behind the result to a business "
                "analyst (5 = clear drivers, plain language, appropriate caveats). Judge clarity "
                "only, not correctness.")


# ---------- runner ----------

def run(model: str | None = None, case_id: str | None = None, judge: bool = False) -> dict:
    from weather_risk.agent.llm import OpenAILlm

    real = OpenAILlm()
    if model:
        real.model = model
    engine = Engine.from_settings()
    hub_names = {h.id: h.name for h in load_hubs()}
    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]

    results = []
    for case in cases:
        llm, convo = CountingLlm(real), Conversation.new()
        start = time.perf_counter()
        resp = None
        for text in case["turns"]:
            resp = run_turn(convo, text, llm, ToolRegistry(engine))
        seconds = time.perf_counter() - start
        failures = check_case(case, resp, convo.items, " ".join(case["turns"]),
                              ToolRegistry(engine), hub_names)
        result = CaseResult(
            id=case["id"], category=case["category"], passed=not failures, failures=failures,
            seconds=round(seconds, 2), model_calls=llm.calls, input_tokens=llm.input_tokens,
            output_tokens=llm.output_tokens,
            answer_type=resp.answer.answer_type if resp.answer else None,
            narrative=resp.answer.narrative if resp.answer else resp.error,
            tool_calls=[(c.tool, c.arguments) for c in resp.tool_calls])
        if judge and resp.answer:
            result.judge = real.complete_json(
                JUDGE_PROMPT, f"Question: {case['turns'][-1]}\nNarrative: {resp.answer.narrative}",
                "judge", JUDGE_SCHEMA)
        results.append(result)
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.id:<40} {seconds:5.1f}s"
              + ("" if result.passed else "\n      - " + "\n      - ".join(failures)))

    summary = summarize(results, real.model)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps({"summary": summary, "cases": [r.__dict__ for r in results]},
                              indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print_summary(summary)
    print(f"\nResults written to {out}")
    return summary


def summarize(results: list[CaseResult], model: str) -> dict:
    by_cat: dict[str, list[CaseResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    times = sorted(r.seconds for r in results)
    judged = [int(r.judge["score"]) for r in results if r.judge]
    return {
        "model": model,
        "cases": len(results),
        "passed": sum(r.passed for r in results),
        "pass_rate": round(100 * sum(r.passed for r in results) / max(1, len(results)), 1),
        "by_category": {c: f"{sum(r.passed for r in rs)}/{len(rs)}" for c, rs in by_cat.items()},
        "numbers_match_engine_failures": sum(
            any(f.startswith("numbers_match_engine") for f in r.failures) for r in results),
        "narrative_numbers_grounded_failures": sum(
            any(f.startswith("narrative_numbers_grounded") for f in r.failures) for r in results),
        "latency_p50_s": round(statistics.median(times), 1) if times else None,
        "latency_p95_s": round(times[min(len(times) - 1, int(0.95 * len(times)))], 1) if times else None,
        "model_calls": sum(r.model_calls for r in results),
        "input_tokens": sum(r.input_tokens for r in results),
        "output_tokens": sum(r.output_tokens for r in results),
        "judge_mean_clarity_1to5": round(statistics.mean(judged), 2) if judged else None,
    }


def print_summary(s: dict) -> None:
    print(f"\n{s['passed']}/{s['cases']} passed ({s['pass_rate']}%) with {s['model']}")
    for cat, score in s["by_category"].items():
        print(f"  {cat:<14} {score}")
    print(f"numbers_match_engine failures: {s['numbers_match_engine_failures']}, "
          f"narrative_numbers_grounded failures: {s['narrative_numbers_grounded_failures']}")
    print(f"latency p50 {s['latency_p50_s']}s, p95 {s['latency_p95_s']}s; "
          f"{s['model_calls']} model calls, {s['input_tokens']} in / {s['output_tokens']} out tokens")
    if s["judge_mean_clarity_1to5"] is not None:
        print(f"LLM judge (separate, not in pass rate): mean clarity {s['judge_mean_clarity_1to5']}/5")
