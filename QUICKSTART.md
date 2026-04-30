# Quickstart

This guide gets the open-source demo running in about 5 minutes.

## 1. Install Runtime

Install Bun:

```bash
npm install -g bun
```

Check it works:

```bash
bun --version
```

## 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```bash
ANTHROPIC_AUTH_TOKEN=replace-with-your-api-key
ICON_DESIGNER_PROVIDER=mock
```

`mock` is the recommended first run. It creates local placeholder images and does not require image-generation provider credentials.

## 3. Start Server

```bash
bun install
bun run dev
```

The server should start on:

```text
http://127.0.0.1:20001
```

## 4. Try the Browser Demo

Open this file in your browser:

```text
examples/client.html
```

Click **Send Intro Request**. The page will:

1. call `POST /agent-sdk/stream`,
2. display streaming events,
3. render `ask_user_question` buttons,
4. send answers back to `POST /agent-sdk/answer`.

## 5. Try a Direct Request

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

If you set `AGENT_SDK_API_KEY`, include:

```bash
-H "Authorization: Bearer your-token"
```

## What To Try Next

- Keep `ICON_DESIGNER_PROVIDER=mock` while building your UI.
- Switch to `ICON_DESIGNER_PROVIDER=dmxapi` or `tencent` only after you have provider credentials.
- Set `UPLOAD_PROVIDER=r2` only if you want generated files published to Cloudflare R2.

## Troubleshooting

- `Missing ANTHROPIC_AUTH_TOKEN`: set it in `.env`, or pass `apiKey` in the request body.
- `Unauthorized`: remove `AGENT_SDK_API_KEY` for local testing, or send the matching bearer token.
- Browser shows CORS or connection errors: make sure the server is running on `http://127.0.0.1:20001`.
- No real image output: this is expected with `ICON_DESIGNER_PROVIDER=mock`; it returns local placeholder images.
