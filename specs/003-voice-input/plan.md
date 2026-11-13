# Implementation Plan: Voice Input

**Branch**: `003-voice-input` (work on `main`) | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-voice-input/spec.md`

## Summary

Add a microphone button to the chat page (`api/static/index.html`) using the browser's own speech recognition (`SpeechRecognition`, or `webkitSpeechRecognition` in Chrome, Edge and Safari).

- **Text:** live partial words appear in the message box. The final text is appended after any existing text and never sent automatically.
- **States:** the button's text label switches between "Voice" and "Stop", with `aria-pressed`, plus a polite live region that announces start, stop, and each error.
- **Fallback:** unsupported browsers get no button and a one-line note.
- **Privacy:** a one-line hint says speech is handled by the browser's speech service.
- **Scope:** no server, API, or agent change.

## Technical Context

**Language/Version**: HTML, CSS and plain JavaScript in the existing static page. No build step, no library.

**Primary Dependencies**: the browser speech API only (MDN, checked via Context7: `interimResults`, `isFinal`, `resultIndex`, and error codes `not-allowed`, `service-not-allowed`, `no-speech`, `audio-capture`, `network`, `aborted`).

**Storage**: none.

**Testing**:
- **pytest smoke:** the page contains the voice control markup, the note, the live region, and no auto-submit from the voice code.
- **Browser check (Chrome tool):** the voice logic is one function, `initVoice(Recognition)`, so the check can pass a **fake recognition class** and fire result and error events. That verifies append, live partial text, no auto-send, toggling and error messages deterministically, without a real microphone. Calling `initVoice(undefined)` verifies the unsupported fallback.
- **One real-microphone try** by the user in Chrome on the deployed https URL.

**Target Platform**: desktop Chrome, Edge and Safari (supported); Firefox gets the fallback.

**Project Type**: front-end change to an existing web page.

**Constraints**: the input keeps its 1,000-character limit, and values are set through `.value` (plain text, never markup). Speech recognition needs a secure page (https or localhost). New text must reach 4.5:1 contrast in both themes.

**Scale/Scope**: about 60 lines of JavaScript, about 15 lines of CSS, and 4 elements of markup.

## Constitution Check

| Principle | How this plan complies | Status |
|---|---|---|
| I. Deterministic scoring, LLM explains | Untouched; voice only fills the text box. | Pass |
| II. Structured contracts | Untouched; the same `/api/chat` request. | Pass |
| III. Grounded and honest | The page states where speech is processed (FR-310); the README says the same. | Pass |
| IV. Test-first and evals | The constitution asks for smoke tests only for the chat page. The plan adds a markup smoke test plus a scripted browser check with a fake recognizer. The eval is rerun at the end (20/20 expected). | Pass |
| V. Narrow scope | One file, no library, no new endpoint. | Pass |
| VI. Reproducible data | Untouched. | Pass |
| VII. Safe by default | Recognized text is treated like typed input: plain text, length-limited, and sent only by the user. No audio reaches the server. | Pass |

**Post-design re-check**: passes. No deviations.

## Project Structure

```text
specs/003-voice-input/
├── plan.md, research.md, quickstart.md
├── contracts/ui.md        # the control's states, labels, messages
└── tasks.md
src/weather_risk/api/static/index.html   # + mic button, note, live region, initVoice()
tests/smoke/test_api_chat.py              # + markup smoke test
```

## Build order

1. Markup and CSS: the button inside `.composer`, the note line, the live region, and the listening style.
2. `initVoice(Recognition)`: feature detection, toggling, interim and final text, append, error messages, and stopping on submit.
3. Smoke test, browser check with the fake recognizer, impeccable triage.
4. Full tests and eval; README voice section.
