# Contract: CLI additions

`wra alerts <command>` (or `python -m weather_risk alerts <command>`). No token is needed: whoever can run the CLI already has the machine and its `.env`.

| Command | Does | Exit code |
|---|---|---|
| `wra alerts check` | Runs a real check (fetches live data into `DATA_DIR`), prints the summary and each alert | 0 ok; 2 if the check failed or any source failed to fetch |
| `wra alerts demo` | Runs the demo, prints the 2 demo alerts and their delivery status | 0 |
| `wra alerts list [--limit N]` | Prints the last check and the newest alerts (demo ones marked `[demo]`) | 0 |

Example output of `wra alerts demo`:

```text
Demo check #6: 16 hubs, 2 alerts (threshold 2.0)
[demo] Dallas      heat       76.6 -> 84.1  (+7.5)   delivered
[demo] Houston     hurricane  65.1 -> 60.1  (-5.0)   delivered
```

`wra refresh` keeps its output and exit codes. It does not record scores or raise alerts; the next check compares against the last recorded check, so a change brought in by a manual refresh is still caught.
