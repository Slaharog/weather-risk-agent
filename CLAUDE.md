# Weather Risk Intelligence Agent (Moveo take-home)

Home assignment for the Moveo FDE role. Source: `ASSIGNMENT (2)_261112_193602.pdf`. Deadline: 24 hours from receipt (received 2026-11-12).

The user must defend every line in a follow-up interview, run the agent live, and possibly change it live. Prefer code the user can explain over clever code.

## Workflow: spec-driven development (Spec Kit)

All feature work uses Spec Kit (`speckit-*` skills, specs in `specs/`, constitution in `.specify/memory/constitution.md`).

Order: constitution, then `speckit-specify`, `speckit-clarify`, `speckit-plan`, `speckit-tasks`, `speckit-analyze`, `speckit-implement`.

- Keep each spec small, one feature per spec.
- The user approves each spec before planning, and approves the plan and tasks before implementation.
- Use `grill-me` / `grilling` to stress-test a spec or plan before approval.
- Use superpowers `test-driven-development` during implementation and `verification-before-completion` before claiming anything works.
- Commit after each completed task. Clean history is part of the deliverable.

## Assignment non-negotiables

- Deterministic scoring or ranking logic in plain code, not LLM output.
- Chat interface that talks to the agent through an API.
- JSON schema enforced between the LLM and the code.
- Small eval set plus a command to run it.
- Assumptions, uncertainty, and scope stated clearly in the README and in answers.
- Short design doc: architecture, repository structure, data storage choice.
- Bonus: alert when a hub's risk score changes. Voice is a bonus.

## Communication style

Write to the user in normal, full sentences in this project, even if caveman or another terse mode is active. The session transcript is submitted to Moveo and must read well.

## Decisions so far

- LLM provider: OpenAI (the user has a key). Use Structured Outputs (strict `json_schema`) and function calling. Keep the provider behind one module so it can be swapped. Pick the exact model from current OpenAI docs during planning.
- Extras in scope: risk-change alert (scheduled), voice input (browser Web Speech API). Keep both small; core requirements come first.
- Docs: use the Context7 MCP (`.mcp.json`) to check current library and API docs before relying on memory.
- Deployment: Railway. One long-lived FastAPI process (API + chat page + in-process scheduler), SQLite on a volume. Local first; deploy last.

## The session log is a deliverable

The full AI session (plan and conversation) must be submitted. Write plans, decisions, and trade-offs into files in the repo (`specs/`, `docs/decisions.md`) so the reasoning is readable without the raw transcript.

## Tools in this project

Project agents (`.claude/agents/`): `code-reviewer`, `prompt-engineer`, `ai-generated-code-auditor`, `reality-checker`, `fullstack-cto-advisor`, `git-workflow-master`, `predictive-qa-specialist`.

Project plugins: `llm-application-dev` (llm-evaluation, prompt patterns), `python-development` (fastapi-pro, python-pro, uv, testing), `tdd-workflows`, `comprehensive-review`, `c4-architecture`, `api-testing-observability`, `backend-api-security`, `ponytail`, `code-simplifier`, plus global superpowers, impeccable (chat UI), vercel (deploy), typesafe, context-mode.

Turned off here to save tokens: startup, startup-business-analyst, ui-ux-pro-max, taste-skill, hallmark, claude-mem, ui-design.
