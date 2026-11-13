---

description: "Task list for feature 003: Voice Input"
---

# Tasks: Voice Input

**Input**: Design documents from `/specs/003-voice-input/`

**Tests**: Constitution Principle IV scope for the chat page is smoke tests. Here that means a pytest markup smoke test plus a scripted browser check with a fake recognizer (research.md §4). The smoke test (T301) is written first and seen failing.

**Task IDs** start at T301 (matching FR-3xx).

## Phase 1: User Story 1 - Speak a question (P1) and User Story 2 - Fallback (P1)

Both stories live in the same function and file, so they are built together.

- [X] T301 [US1] Smoke test, failing first, in `tests/smoke/test_api_chat.py`: `GET /` contains `id="mic"` with `aria-pressed="false"`, `id="voice-status"` with `role="status"`, the unsupported note text "Voice input isn't supported in this browser", the privacy hint "Voice uses your browser's speech service", and `function initVoice(`. Also check that the voice code never calls `form.requestSubmit`, `form.submit` or `ask(` (no auto-send, FR-302 and SC-303).
- [X] T302 [US1] Markup and CSS in `src/weather_risk/api/static/index.html`:
  - a `<button id="mic" type="button" aria-pressed="false">Voice</button>` before Send, inside `.composer`;
  - a `role="status"` line `#voice-status`;
  - the hidden-by-default unsupported note and the privacy hint, in the existing `.count` row style;
  - a listening style (accent border plus the text label "Stop"; not color alone);
  - a `:focus-visible` ring.
- [X] T303 [US1][US2] `initVoice(Recognition)` in the same file. It covers:
  - feature detection: no class means hide `#mic` and show the note;
  - `lang = "en-US"`, `interimResults = true`, `continuous = false`;
  - the toggle on click;
  - `base` text captured at start, with live interim plus final text appended with a space and capped at 1,000 characters;
  - the `updateCount()` call;
  - the error map from research.md §3;
  - `end` resetting the button and announcing "Done…" if text was added;
  - the form submit handler stopping recognition first.
  - It is called once: `initVoice(window.SpeechRecognition || window.webkitSpeechRecognition)`.
- [ ] T304 [US1][US2] Browser check with the Chrome tool against a local server:
  - inject a `FakeRecognition` class and call `initVoice(FakeRecognition)`;
  - type "Hi", click Voice, fire an interim result then a final result, and check that the box shows "Hi <words>", the button says "Stop" then "Voice", the status announces each step, and no `/api/chat` request was made;
  - fire `not-allowed` and check the message;
  - call `initVoice(undefined)` on a fresh load and check that the button is hidden and the note is visible.
  - Record the results in the commit message.
- [ ] T305 Impeccable triage of the changed page: hook findings, plus contrast computed for the new text in both themes (at least 4.5:1). Fix or document.

## Phase 2: Polish

- [ ] T306 Full `pytest`, `ruff`, and `wra eval` (20/20 expected; the chat API is unchanged). Add a README "Voice input" section: how it works, supported browsers, and the privacy line. Add a `docs/decisions.md` entry.

## Dependencies

T301 comes before T302 and T303 (the test is red first). T303 comes before T304 and T305. T306 comes last.
