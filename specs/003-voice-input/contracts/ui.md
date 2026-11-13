# Contract: Voice control on the chat page

| State | Button | Status line (announced) |
|---|---|---|
| Unsupported browser | hidden | note under the box: "Voice input isn't supported in this browser. Type your question instead." (static text, not announced) |
| Idle | "Voice", `aria-pressed="false"` | empty |
| Listening | "Stop", `aria-pressed="true"`, listening style plus the text label | "Listening… speak your question." |
| Ended with text | "Voice" | "Done. Check the text, then press Send." |
| Error | "Voice" | the message from research.md §3 |

- **Text:** the box receives `base + " " + recognized words`, with live partial words while speaking. Nothing is ever submitted by the voice code.
- **Send while listening:** recognition is stopped, and only the text in the box is sent.
- **Hint:** one muted line near the box says "Voice uses your browser's speech service; this app receives only the text you send."
- **Keyboard:** the button is a native `<button>`, so Tab, Enter and Space work, with a visible focus ring.
