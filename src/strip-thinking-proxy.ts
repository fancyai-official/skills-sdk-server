/**
 * Local proxy that sanitizes outgoing Anthropic API requests before
 * forwarding them to the real upstream, and tracks token usage from
 * every API response.
 *
 * Sanitization includes:
 * - Stripping `thinking` content blocks from multi-turn message history
 *   (avoids "Invalid signature in thinking block" on third-party proxies).
 * - Removing unsupported `anthropic-beta` flags from request headers
 *   (avoids "invalid beta flag" on AWS Bedrock / non-first-party hosts).
 * - Deleting top-level body fields the upstream doesn't recognise
 *   (e.g. `thinking`, `context_management`, `output_config`).
 *
 * Usage tracking:
 * - For streaming responses: parses SSE events (`message_start` /
 *   `message_delta`) to extract per-call token counts.
 * - For non-streaming responses: extracts `usage` from the JSON body.
 * - Logs a `[ProxyUsage]` line for every API call that consumed tokens.
 * - Pushes usage data to registered session callbacks (for real-time
 *   forwarding to clients via SSE).
 */

const LOG_TAG = "[StripThinkingProxy]";
const USAGE_TAG = "[ProxyUsage]";

// ── Beta-flag filtering ────────────────────────────────────────────────

const STRIP_BETA_FLAGS_ENV = typeof process !== "undefined"
  ? process.env.STRIP_BETA_FLAGS
  : undefined;

const BETA_FLAGS_TO_STRIP: Set<string> = new Set(
  STRIP_BETA_FLAGS_ENV
    ? STRIP_BETA_FLAGS_ENV.split(",").map((s: string) => s.trim()).filter(Boolean)
    : [
        "interleaved-thinking-2025-05-14",
        "context-management-2025-06-27",
        "prompt-caching-scope-2026-01-05",
        "structured-outputs-2025-12-15",
      ],
);

function sanitizeBetaHeader(headers: Headers): void {
  const raw = headers.get("anthropic-beta");
  if (!raw) return;

  const original = raw.split(",").map((s) => s.trim()).filter(Boolean);
  const kept = original.filter((flag) => !BETA_FLAGS_TO_STRIP.has(flag));
  if (kept.length === original.length) return;

  const removed = original.filter((flag) => BETA_FLAGS_TO_STRIP.has(flag));
  console.log(`${LOG_TAG} Removed beta flags: ${removed.join(", ")}`);

  if (kept.length > 0) {
    headers.set("anthropic-beta", kept.join(","));
  } else {
    headers.delete("anthropic-beta");
  }
}

// ── Body sanitization ──────────────────────────────────────────────────

const UNSUPPORTED_BODY_FIELDS = ["thinking", "context_management", "output_config"];

interface SanitizeResult {
  json: string;
  modified: boolean;
}

function stripThinkingBlocks(messages: any[]): number {
  let stripped = 0;
  for (const msg of messages) {
    if (!msg || !Array.isArray(msg.content)) continue;

    const before = msg.content.length;
    const filtered = msg.content.filter((b: any) => b?.type !== "thinking");

    if (filtered.length === before) continue;
    stripped += before - filtered.length;

    msg.content = filtered.length > 0
      ? filtered
      : [{ type: "text", text: "(thinking omitted)" }];
  }
  return stripped;
}

function sanitizeRequestBody(rawText: string): SanitizeResult {
  try {
    const parsed = JSON.parse(rawText) as Record<string, unknown>;
    let modified = false;

    if (Array.isArray(parsed.messages)) {
      const count = stripThinkingBlocks(parsed.messages);
      if (count > 0) {
        console.log(`${LOG_TAG} Removed ${count} thinking block(s) from request`);
        modified = true;
      }
    }

    for (const field of UNSUPPORTED_BODY_FIELDS) {
      if (field in parsed) {
        delete parsed[field];
        console.log(`${LOG_TAG} Removed unsupported body field: ${field}`);
        modified = true;
      }
    }

    return { json: modified ? JSON.stringify(parsed) : rawText, modified };
  } catch {
    return { json: rawText, modified: false };
  }
}

// ── Usage callback registry ────────────────────────────────────────────

export interface UsageData {
  inputTokens: number;
  outputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;
  model?: string;
  path: string;
}

export type UsageCallback = (usage: UsageData) => void;

const usageCallbacks = new Map<string, UsageCallback>();

export function registerUsageCallback(sessionId: string, callback: UsageCallback): void {
  usageCallbacks.set(sessionId, callback);
  console.log(`${USAGE_TAG} Registered callback for session ${sessionId}`);
}

export function unregisterUsageCallback(sessionId: string): void {
  usageCallbacks.delete(sessionId);
  console.log(`${USAGE_TAG} Unregistered callback for session ${sessionId}`);
}

// ── Response-side usage tracking ───────────────────────────────────────

interface UsageAccumulator {
  inputTokens: number;
  outputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;
}

function emitUsage(
  usage: UsageAccumulator,
  path: string,
  sessionId?: string,
  model?: string,
): void {
  const total = usage.inputTokens + usage.outputTokens;
  if (total === 0) return;

  const parts = [
    `input=${usage.inputTokens}`,
    `output=${usage.outputTokens}`,
    `cache_read=${usage.cacheReadInputTokens}`,
    `cache_create=${usage.cacheCreationInputTokens}`,
  ];
  if (model) parts.push(`model=${model}`);
  parts.push(`path=${path}`);
  console.log(`${USAGE_TAG} ${parts.join(" ")}`);

  if (sessionId) {
    const cb = usageCallbacks.get(sessionId);
    if (cb) cb({ ...usage, model, path });
  }
}

/**
 * Wrap an upstream SSE stream to extract token usage from
 * `message_start` and `message_delta` events while passing
 * all data through untouched.
 */
function createUsageTrackingStream(
  upstreamBody: ReadableStream<Uint8Array>,
  path: string,
  sessionId?: string,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const usage: UsageAccumulator = {
    inputTokens: 0,
    outputTokens: 0,
    cacheCreationInputTokens: 0,
    cacheReadInputTokens: 0,
  };
  let model: string | undefined;
  let buffer = "";

  return upstreamBody.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        controller.enqueue(chunk);

        buffer += decoder.decode(chunk, { stream: true });

        let boundary: number;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const event = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);

          const dataLines = event
            .split("\n")
            .filter((line: string) => line.startsWith("data: "))
            .map((line: string) => line.slice(6));
          if (dataLines.length === 0) continue;

          const dataStr = dataLines.join("");
          if (dataStr === "[DONE]") continue;

          try {
            const data = JSON.parse(dataStr);

            if (data.type === "message_start" && data.message?.usage) {
              const u = data.message.usage;
              usage.inputTokens += u.input_tokens ?? 0;
              usage.cacheCreationInputTokens += u.cache_creation_input_tokens ?? 0;
              usage.cacheReadInputTokens += u.cache_read_input_tokens ?? 0;
              if (data.message.model) model = data.message.model;
            } else if (data.type === "message_delta" && data.usage) {
              usage.outputTokens += data.usage.output_tokens ?? 0;
            }
          } catch {
            // not valid JSON, skip
          }
        }
      },

      flush() {
        emitUsage(usage, path, sessionId, model);
      },
    }),
  );
}

/**
 * Extract usage from a non-streaming JSON response body.
 */
function extractUsageFromJson(body: string, path: string, sessionId?: string): void {
  try {
    const parsed = JSON.parse(body);
    const u = parsed.usage;
    if (!u) return;
    emitUsage(
      {
        inputTokens: u.input_tokens ?? 0,
        outputTokens: u.output_tokens ?? 0,
        cacheCreationInputTokens: u.cache_creation_input_tokens ?? 0,
        cacheReadInputTokens: u.cache_read_input_tokens ?? 0,
      },
      path,
      sessionId,
      parsed.model,
    );
  } catch {
    // not valid JSON
  }
}

// ── Proxy server ───────────────────────────────────────────────────────

/**
 * Start a lightweight HTTP proxy on `127.0.0.1:<port>`.
 *
 * - POST requests to paths containing `/messages` are sanitized
 *   (headers + body) before forwarding.
 * - Responses from `/messages` endpoints are observed for token usage.
 * - All other requests are forwarded as-is.
 *
 * @returns The local base URL, or `undefined` if the proxy failed to start.
 */
export function startStripThinkingProxy(
  upstreamBaseUrl: string,
  port: number = 20099,
): string | undefined {
  try {
    const server = Bun.serve({
      port,
      hostname: "127.0.0.1",
      idleTimeout: 255,

      async fetch(req) {
        const url = new URL(req.url);
        const targetUrl = `${upstreamBaseUrl}${url.pathname}${url.search}`;

        const headers = new Headers(req.headers);
        const sessionId = headers.get("x-claude-code-session-id") ?? undefined;
        headers.delete("host");
        headers.delete("content-length");
        sanitizeBetaHeader(headers);

        let forwardBody: string | null = null;
        const isMessagesEndpoint = req.method === "POST" && url.pathname.includes("/messages");

        if (isMessagesEndpoint) {
          const { json } = sanitizeRequestBody(await req.text());
          forwardBody = json;
        } else if (req.body) {
          forwardBody = await req.text();
        }

        try {
          const upstream = await fetch(targetUrl, {
            method: req.method,
            headers,
            body: forwardBody,
          });

          const responseHeaders = new Headers(upstream.headers);
          responseHeaders.delete("content-encoding");
          responseHeaders.delete("content-length");
          responseHeaders.delete("transfer-encoding");

          if (isMessagesEndpoint && upstream.ok) {
            const contentType = upstream.headers.get("content-type") ?? "";
            const isStreaming = contentType.includes("text/event-stream");

            if (isStreaming && upstream.body) {
              return new Response(
                createUsageTrackingStream(upstream.body, url.pathname, sessionId),
                {
                  status: upstream.status,
                  statusText: upstream.statusText,
                  headers: responseHeaders,
                },
              );
            }

            // Non-streaming: read body, extract usage, return as-is
            const body = await upstream.text();
            extractUsageFromJson(body, url.pathname, sessionId);
            return new Response(body, {
              status: upstream.status,
              statusText: upstream.statusText,
              headers: responseHeaders,
            });
          }

          return new Response(upstream.body, {
            status: upstream.status,
            statusText: upstream.statusText,
            headers: responseHeaders,
          });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          console.error(`${LOG_TAG} Upstream fetch failed: ${message}`);
          return new Response(
            JSON.stringify({ error: { type: "proxy_error", message } }),
            { status: 502, headers: { "Content-Type": "application/json" } },
          );
        }
      },
    });

    const localUrl = `http://127.0.0.1:${server.port}`;
    console.log(`${LOG_TAG} Listening on ${localUrl} → upstream ${upstreamBaseUrl}`);
    return localUrl;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`${LOG_TAG} Failed to start on port ${port}: ${message}`);
    console.error(`${LOG_TAG} Falling back to direct upstream connection (thinking blocks will NOT be stripped)`);
    return undefined;
  }
}
