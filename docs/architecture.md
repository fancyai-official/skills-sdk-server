# Architecture

The server exposes a small HTTP API around `@anthropic-ai/claude-agent-sdk`.

```text
Client -> POST /agent-sdk/stream -> Bun server -> Claude Agent SDK
                     |                    |
                     |                    +-> project cwd / .claude skills
                     +-> POST /agent-sdk/answer for interactive tool answers
```

Main modules:

- `src/server.ts`: routes, SSE stream lifecycle, SDK invocation.
- `src/pending-answers.ts`: waits for UI answers to `AskUserQuestion` calls.
- `src/static-intros.ts`: serves configured app intros without an upstream model call.
- `src/history.ts`: reads local Claude conversation files for history APIs.
- `src/image-processing.ts`: optional image URL extraction and compression.
