# Feature Specification: Voice Input

**Feature Branch**: `003-voice-input` (work happens on `main`; no branch hook is configured)

**Created**: 2026-11-13

**Status**: Approved (2026-11-13)

**Input**: User description: "Voice input for the chat page (bonus feature). A microphone button next to the message box lets the analyst speak a question; the browser's built-in speech recognition (Web Speech API) turns it into text, which appears in the input box for review and editing before the user sends it (never auto-sent). Graceful fallback: when the browser does not support speech recognition, or microphone permission is denied, the button is hidden or disabled with a clear text explanation, and typing still works. Clear listening state (visible and announced to screen readers), stop on second click, keyboard accessible, readable contrast in light and dark mode; the impeccable design hook findings are triaged. No audio is sent to our server; the server and agent are unchanged. Keep it small: front-end only, one static page."

## Clarifications

### Session 2026-11-13

- Q: In a browser without speech recognition, is the microphone hidden or disabled? → A: Hidden, with one short note under the message box saying voice input isn't supported in this browser and to type instead.
- Q: Do partial words appear while the analyst is still speaking? → A: Yes. Live partial text appears in the box and is replaced by the final text when speech ends.
- Q: What does dictation do to text already in the box? → A: Append, separated by a space; typed text is never replaced.

## User Scenarios & Testing *(mandatory)*

The user is the same **analyst** as in feature 001, using the chat page in a desktop browser.

### User Story 1 - Speak a question instead of typing it (Priority: P1)

The analyst presses the microphone button next to the message box and speaks a question. While they speak, the page clearly shows that it is listening. When they stop (or press the button again), the recognized words appear in the message box. The analyst reads them, fixes any misheard word by typing, and sends the question as usual.

**Why this priority**: this is the whole feature.

**Independent Test**: in a supporting browser, press the button, say "Which hubs in the Midwest are most exposed to winter disruption?", stop, and verify the text appears in the message box, is editable, and is sent only when the analyst presses Send.

**Acceptance Scenarios**:

1. **Given** a browser with speech recognition and microphone permission, **When** the analyst presses the microphone button and speaks, **Then** the page shows a visible "listening" state, and screen readers announce that listening started.
2. **Given** listening is active, **When** the analyst stops speaking or presses the button again, **Then** listening stops, the state is announced, and the recognized text is in the message box.
3. **Given** recognized text is in the message box, **When** the analyst does nothing, **Then** nothing is sent; the question is sent only through the normal Send action.
4. **Given** the message box already has typed text, **When** the analyst dictates, **Then** the dictated words are added after the existing text, not replacing it.

---

### User Story 2 - Clear fallback when voice is not available (Priority: P1)

If the browser cannot recognize speech (for example Firefox), the microphone is blocked, or recognition fails, the analyst sees a short plain-language explanation and can keep typing as before.

**Why this priority**: a broken or silent button is worse than no button; typing must never be affected.

**Independent Test**: open the page in a browser without speech recognition and verify the explanation is shown, no broken control is offered, and typing and sending still work. Deny microphone permission in a supporting browser and verify a clear message.

**Acceptance Scenarios**:

1. **Given** a browser without speech recognition, **When** the page loads, **Then** the microphone button is hidden and a short text says voice input is not supported in this browser and to type instead.
2. **Given** microphone permission is denied, **When** the analyst presses the button, **Then** a message says the microphone is blocked and how to allow it, and the message box keeps its contents.
3. **Given** recognition returns nothing (silence) or a network error, **When** listening ends, **Then** a short message says nothing was recognized, or that voice input is unavailable, and the button returns to its normal state.

### Edge Cases

- **Pressing Send while listening**: listening stops first; only text already in the box is sent.
- **Very long dictation**: the box keeps its 1,000-character limit; the existing counter shows the length.
- **A request is in progress** (the page is waiting for an answer): dictation still fills the box for the next question; nothing is sent automatically.
- **Language**: recognition uses US English, matching the hubs and the agent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-301**: The chat page MUST offer a microphone control next to the message box in browsers that support speech recognition.
- **FR-302**: Recognized speech MUST be placed in the message box, appended after any existing text with a space, and MUST NOT be sent automatically. Partial words MUST appear while the analyst speaks and be replaced by the final recognized text when speech ends.
- **FR-303**: The control MUST toggle: the first activation starts listening, and the second stops it. Listening also stops on its own when the speaker pauses.
- **FR-304**: The listening state MUST be visible by more than color alone (a text label change) and MUST be announced to assistive technology when it starts and stops.
- **FR-305**: The control MUST be operable by keyboard, have an accessible name, and expose its pressed state.
- **FR-306**: Where speech recognition is unsupported, the microphone control MUST be hidden, and one short note under the message box MUST say voice input isn't supported in this browser and to type instead. Typing and sending MUST work unchanged.
- **FR-307**: Permission denied, no speech, and recognition errors MUST each produce a short plain-language message, and MUST leave the message box contents intact.
- **FR-308**: Recognition language MUST be US English.
- **FR-309**: Text from recognition MUST be treated as plain text (never interpreted as markup) and MUST respect the 1,000-character limit.
- **FR-310**: The page MUST tell the user, in one short line near the control, that speech is processed by their browser's speech service, not by this application.
- **FR-311**: No server, API, or agent change. Chat behavior and evals are unchanged.
- **FR-312**: Contrast of all new text and controls MUST be readable in light and dark mode (at least 4.5:1 for text).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-301**: In a supporting browser, an analyst can dictate one of the four example questions and send it in under 15 seconds, with no typing other than corrections.
- **SC-302**: In an unsupported browser, 100% of chat functions still work, and the explanation is visible without any interaction.
- **SC-303**: Zero questions are ever sent without an explicit Send action.
- **SC-304**: All new text meets 4.5:1 contrast in both color schemes; the control is reachable and usable with the keyboard alone.
- **SC-305**: All existing tests pass and the eval set still scores 20/20.

## Assumptions

- **Where speech is processed.** In Chrome and Edge, the browser sends the audio to the browser vendor's cloud speech service for recognition. This application never receives audio, only the final text the user chooses to send. This is stated on the page (FR-310) and in the README.
- **Supported browsers.** Chrome, Edge and Safari support the browser speech API; Firefox does not. The fallback covers the rest.
- **Microphone access needs a secure page** (https or localhost); the deployed site is https.
- **Out of scope:** spoken answers (text-to-speech), continuous conversation mode, wake words, languages other than US English, mobile-specific layouts beyond what the page already does, and server-side speech recognition.
