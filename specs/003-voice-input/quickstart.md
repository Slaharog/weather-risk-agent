# Quickstart: Voice Input

1. `uv run python -m pytest`: all tests pass, including the voice markup smoke test.
2. Run `uv run python -m weather_risk serve` and open http://localhost:8000 in Chrome.
3. **Scripted check:** in the console, or with the Chrome tool, call `initVoice(FakeRecognition)` and fire events. Check append, live partial text, no auto-send, the toggle, and the error messages ([contracts/ui.md](contracts/ui.md)).
4. **Fallback check:** call `initVoice(undefined)`. The button is hidden, the note is shown, and typing still works.
5. **Real microphone:** on the deployed https URL in Chrome, press Voice, say "Which hubs in the Midwest are most exposed to winter disruption?", review the text, then press Send.
6. `uv run python -m weather_risk eval`: 20/20.
