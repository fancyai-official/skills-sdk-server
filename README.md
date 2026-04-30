# Claude Agent SDK Server

A small Bun/TypeScript server that wraps `@anthropic-ai/claude-agent-sdk` behind HTTP + Server-Sent Events. It includes one sanitized sample app, **Icon Designer**, to demonstrate project-scoped Claude skills, static intros, interactive questions, and optional image generation providers.

This directory is prepared as a public GitHub project. It intentionally contains no private deployment files, no real API keys, and only one sample app.

## Choose Your Path

Start with the lowest-cost path, then add paid services only when you need them.

| Path | What You Get | Requires | Cost |
|---|---|---|---|
| **Mock demo** | Run the server, use the sample app, and generate local placeholder images | Bun + an Anthropic-compatible API key | Model tokens only |
| **Claude chat** | Build your own UI or integration on top of `/agent-sdk/stream` and `/agent-sdk/answer` | Same as above, plus client code | Model tokens |
| **Real image generation** | Replace placeholder images with Tencent Cloud or DMXAPI generation and optional R2 publishing | Provider credentials and storage config | Model tokens + image API/storage costs |

If you are new to this project, follow [`QUICKSTART.md`](QUICKSTART.md) first, then try [`examples/client.html`](examples/client.html).

## Features

- `POST /agent-sdk/stream` streams Claude Agent SDK events over SSE.
- `POST /agent-sdk/answer` receives UI answers for `AskUserQuestion`.
- Local history endpoints read Claude conversation JSONL files.
- Static intro configuration can return an app intro without an upstream model call.
- `app-icon-designer` includes a local `mock` image provider that runs without cloud credentials.

## Project Structure

```text
.
├── src/                         # Bun server and SDK wrapper
├── .claude/
│   ├── CLAUDE.md                # Global interaction rules
│   └── apps/app-icon-designer/  # Single open-source sample app
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Quick Start

```bash
bun install
cp .env.example .env
# Edit .env and set ANTHROPIC_AUTH_TOKEN.
bun run dev
```

The server listens on `http://127.0.0.1:20001` by default.

For a guided 5-minute setup, see [`QUICKSTART.md`](QUICKSTART.md). For a browser-based client example, open [`examples/client.html`](examples/client.html) after starting the server.

## Minimal Request

```bash
curl -N http://127.0.0.1:20001/agent-sdk/stream \
  -H "Content-Type: application/json" \
  -d '{
    "userMessage": "Explain to me what you do",
    "options": {
      "cwd": "./.claude/apps/app-icon-designer",
      "allowedTools": ["Skill", "AskUserQuestion", "Bash"]
    }
  }'
```

If `AGENT_SDK_API_KEY` is set, add `Authorization: Bearer <token>` to requests.

## Sample App

`app-icon-designer` demonstrates a project-level `CLAUDE.md`, a skill-level `SKILL.md`, static intro configuration, interactive questions, and a three-step image generation script contract.

By default, the sample uses:

```bash
ICON_DESIGNER_PROVIDER=mock
```

The mock provider writes placeholder PNGs locally, so the example can run without paid image APIs. To connect real providers, set:

- `ICON_DESIGNER_PROVIDER=tencent` with Tencent Cloud variables, or
- `ICON_DESIGNER_PROVIDER=dmxapi` with `DMX_API_KEY`, or
- `ICON_DESIGNER_PROVIDER=auto` to try Tencent first and DMXAPI as fallback.

The sample references famous fashion designers only as historical and aesthetic inspiration. It is not affiliated with, endorsed by, or sponsored by any designer, fashion house, or trademark owner.

## Environment

See `.env.example` for the full list. Important variables:

- `ANTHROPIC_AUTH_TOKEN`: upstream API key.
- `ANTHROPIC_BASE_URL`: optional Anthropic-compatible base URL.
- `ANTHROPIC_MODEL`: default model.
- `AGENT_SDK_API_KEY`: optional bearer token protecting this proxy.
- `ICON_DESIGNER_PROVIDER`: `mock`, `tencent`, `dmxapi`, or `auto`.
- `UPLOAD_PROVIDER`: `local` or `r2` for generated assets.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Generated mock images are written under `.generated/` in local runs and `generated-output/` in Docker Compose. Conversation data is persisted under `claude-data/`.

## Development

```bash
bun run typecheck
bun run build
```

Python helpers for the sample app use `requirements.txt`.

## Security Notes

- Do not commit local environment files, secret files, conversation logs, or generated media.
- Prefer setting `AGENT_SDK_API_KEY` before exposing the server outside localhost.
- Provider credentials are optional and should be injected through environment variables.

## License

Apache-2.0. See `LICENSE`.
