# Research: Voice Input

## 1. Browser speech API, not a server speech service

- **Decision:** use `window.SpeechRecognition || window.webkitSpeechRecognition` with `lang="en-US"`, `interimResults=true` and `continuous=false`, so it stops on a pause.
- **Rationale:** zero server code, zero cost, and the spec asks for it. The user reviews the text before sending, so recognition errors are cheap.
- **Honest privacy note:** Chrome and Edge send the audio to the vendor's cloud recognizer. This app never receives audio. The page says so in one line (FR-310).
- **Alternatives:** OpenAI transcription via a new upload endpoint, rejected because it adds an audio endpoint, cost and attack surface for a bonus feature. A local model such as Whisper in WebAssembly is too heavy for one static page.

## 2. Live partial text and append

- **Decision:** when listening starts, remember the box's current text as the `base`. On each `result` event, set the box to `base + space + (final words) + (partial words)`. When listening ends, keep the final text only.
- **Rationale:** the user sees words appear (clarified in spec Q2), and typed text is never lost (Q3).

## 3. States and messages

- **Decision:** one `<button type="button" aria-pressed>` whose text changes between "Voice" and "Stop", plus a `role="status"` line for announcements and errors. The error map:

| Error | Message |
|---|---|
| `not-allowed`, `service-not-allowed` | "Microphone blocked. Allow it in the browser's site settings, or type instead." |
| `no-speech` | "Didn't catch that. Try again, or type your question." |
| `audio-capture` | "No microphone found. Type your question instead." |
| `network` | "Voice input is unavailable right now (network). Type your question instead." |
| `aborted` | no message (the user stopped it) |
| other | "Voice input stopped unexpectedly. Type your question instead." |

- **Alternatives:** an icon-only button (needs an aria-label, and its state is less obvious), rejected in favor of a visible text label (FR-304).

## 4. Testability without a microphone

- **Decision:** the voice code is a single `initVoice(Recognition)` function called once with the real class. A browser check can call it with a fake class that fires `start`, `result`, `error` and `end` events. This verifies the behavior deterministically, which Principle IV's "smoke tests for the chat page" allows.
