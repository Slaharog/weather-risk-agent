# Contract: Command line (`wra`)

Installed as a script entry point by `uv`. Run as `uv run wra <command>`. Exit code 0 on success, 1 on user error, 2 on data or network failure.

| Command | What it does | LLM? |
|---|---|---|
| `wra rank [--hazard overall] [--region Midwest]` | Prints the ranking table (FR-029) | No |
| `wra breakdown <hub_id>` | Prints the overall score, hazard scores, and components | No |
| `wra stat <hub_id> <stat> [--year 2025]` | Prints one weather statistic with its counts and definition | No |
| `wra refresh [--source weather\|nri\|all]` | Fetches live data from Open-Meteo and FEMA NRI into `DATA_DIR`, atomically per source; prints what changed | No |
| `wra eval [--model NAME] [--case ID]` | Runs the eval set and prints the pass rate overall and per category, with failure reasons; writes `evals/results/<timestamp>.json` | Yes |
| `wra serve [--port 8000]` | Starts the API and chat page | Yes, for chat |

`rank`, `breakdown`, and `stat` call the same functions as the API endpoints and the agent tools, so all three paths show identical numbers.
