import "./logger";
import { traceStore } from "./logger";
import { query, type Options } from "@anthropic-ai/claude-agent-sdk";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import {
  DEFAULT_SETTING_SOURCES, json, normalizeMcpServers,
  normalizeSettingSources, parseBooleanParam, parseNumberParam, sanitizeBaseURL,
} from "./server-helpers";
import { listAllConversations, listProjects, readConversationHistory } from "./history";
import { type RequestBody } from "./types";
import { getStaticIntroConfig } from "./static-intros";
import {
  startStripThinkingProxy,
  registerUsageCallback, unregisterUsageCallback,
  type UsageData,
} from "./strip-thinking-proxy";
import { ensureIsolatedWorkspace } from "./workspace";
import {
  extractMediaArtifacts, buildMultimodalPrompt,
  processPromptWithImages, logResolvedImages,
  type MediaArtifact,
} from "./image-processing";
import { waitForAnswer, cleanupStreamAnswers, resolvePendingAnswer } from "./pending-answers";

process.env.DEBUG_SDK_HTTP ??= "0";

// ── Configuration ──────────────────────────────────────────────────────

const PORT = Number(process.env.AGENT_SDK_PORT || 20001);
const AGENT_SDK_API_KEY = process.env.AGENT_SDK_API_KEY || "";
const AUTH_TOKEN = process.env.ANTHROPIC_AUTH_TOKEN;
const BASE_URL = sanitizeBaseURL(process.env.ANTHROPIC_BASE_URL);

const STRIP_THINKING = process.env.STRIP_THINKING_BLOCKS === "1";
let THINKING_PROXY_URL: string | undefined;
if (STRIP_THINKING) {
  if (BASE_URL) {
    const proxyPort = Number(process.env.STRIP_THINKING_PROXY_PORT || 20099);
    THINKING_PROXY_URL = startStripThinkingProxy(BASE_URL, proxyPort);
  } else {
    console.warn("[StripThinkingProxy] STRIP_THINKING_BLOCKS=1 but ANTHROPIC_BASE_URL is not set — proxy will not start.");
  }
}

const DEFAULT_MODEL =
  process.env.ANTHROPIC_MODEL || process.env.ANTHROPIC_DEFAULT_SONNET_MODEL || "claude-3-5-sonnet-20241022";
const DEFAULT_SYSTEM_PROMPT = (process.env.ANTHROPIC_SYSTEM_PROMPT || "").trim() || undefined;
const HOME_DIR = process.env.HOME || process.env.USERPROFILE || "";
const CLAUDE_DATA_DIR =
  process.env.CLAUDE_DATA_DIR || process.env.AGENT_SDK_CLAUDE_DATA_DIR || (HOME_DIR ? `${HOME_DIR}/.claude` : ".claude");

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

// ── HTTP Helpers ────────────────────────────────────────────────────────

function corsResponse(body: string | null, status: number): Response {
  return new Response(body, { status, headers: CORS_HEADERS });
}

function corsJson(data: unknown, status = 200): Response {
  return json(data, { status, headers: CORS_HEADERS });
}

function checkAuth(req: Request): Response | null {
  if (!AGENT_SDK_API_KEY) return null;
  const auth = req.headers.get("authorization") || "";
  return auth === `Bearer ${AGENT_SDK_API_KEY}` ? null : corsResponse("Unauthorized", 401);
}

/**
 * Strip AskUserQuestion tool_use blocks from an assistant message JSON.
 * Returns null if the entire message should be suppressed.
 */
function filterAskUserQuestion(jsonStr: string): string | null {
  if (!jsonStr.includes("AskUserQuestion")) return jsonStr;
  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed.type !== "assistant") return jsonStr;
    const content = parsed.message?.content ?? parsed.content;
    if (!Array.isArray(content)) return jsonStr;

    const filtered = content.filter(
      (b: any) => !(b.type === "tool_use" && b.name === "AskUserQuestion"),
    );
    if (filtered.length === 0) {
      console.log("[Send] Blocked assistant message containing only AskUserQuestion tool_use");
      return null;
    }
    if (filtered.length !== content.length) {
      if (parsed.message?.content) parsed.message.content = filtered;
      else if (parsed.content) parsed.content = filtered;
      console.log("[Send] Stripped AskUserQuestion tool_use from assistant message");
      return JSON.stringify(parsed);
    }
    return jsonStr;
  } catch {
    return jsonStr;
  }
}

function readDebugLogs(): void {
  try {
    const homedir = process.env.HOME || process.env.USERPROFILE || "/root";
    const debugDir = join(homedir, ".claude", "debug");
    if (!existsSync(debugDir)) {
      console.log("[SDK Debug Log] ~/.claude/debug/ directory not found");
      return;
    }
    const files = readdirSync(debugDir)
      .map((f: string) => ({ name: f, path: join(debugDir, f), mtime: statSync(join(debugDir, f)).mtimeMs }))
      .sort((a: { mtime: number }, b: { mtime: number }) => b.mtime - a.mtime);
    for (const f of files.slice(0, 3)) {
      const content = readFileSync(f.path, "utf-8");
      const lines = content.split("\n");
      const headerLines = lines.filter(
        (l: string) => /request-id|authorization|anthropic-|x-api-key|content-type|user-agent|POST |GET |HTTP\//i.test(l),
      );
      if (headerLines.length > 0) {
        console.log(`[SDK Debug Log] ${f.name} (HTTP header lines):\n${headerLines.join("\n")}`);
      } else {
        console.log(`[SDK Debug Log] ${f.name}: ${lines.length} lines, first 30:\n${lines.slice(0, 30).join("\n")}`);
      }
    }
  } catch (err) {
    console.warn("[SDK Debug Log] Failed to read debug logs:", err);
  }
}

// ── Read-Only Route Handlers ────────────────────────────────────────────

async function handleProjectsRoute(): Promise<Response> {
  const projects = await listProjects({ claudeDataDir: CLAUDE_DATA_DIR });
  if (!projects) return corsJson({ error: "Claude data dir not found", claudeDataDir: CLAUDE_DATA_DIR }, 404);
  return corsJson({ claudeDataDir: CLAUDE_DATA_DIR, projects });
}

async function handleConversationsRoute(url: URL): Promise<Response> {
  const limit = parseNumberParam(url.searchParams.get("limit")) ?? 100;
  const items = await listAllConversations({ claudeDataDir: CLAUDE_DATA_DIR, limit });
  if (!items) return corsJson({ error: "Claude data dir not found", claudeDataDir: CLAUDE_DATA_DIR }, 404);
  return corsJson({ claudeDataDir: CLAUDE_DATA_DIR, conversations: items });
}

async function handleHistoryRoute(url: URL): Promise<Response> {
  const conversationId = url.searchParams.get("conversationId") || "";
  const offset = parseNumberParam(url.searchParams.get("offset")) ?? 0;
  const limit = parseNumberParam(url.searchParams.get("limit")) ?? 200;
  const includeThinking = parseBooleanParam(url.searchParams.get("includeThinking")) ?? false;

  const result = await readConversationHistory({ claudeDataDir: CLAUDE_DATA_DIR, conversationId, offset, limit, includeThinking });
  if (!result) {
    return corsJson({ error: "Conversation not found", claudeDataDir: CLAUDE_DATA_DIR, conversationId }, 404);
  }
  return corsJson({ claudeDataDir: CLAUDE_DATA_DIR, ...result });
}

// ── Answer Handler ──────────────────────────────────────────────────────

async function handleAnswerRequest(req: Request): Promise<Response> {
  let body: { questionId?: string; toolUseId?: string; answers?: Record<string, string> };
  try {
    body = await req.json();
  } catch {
    return corsJson({ error: "Invalid JSON" }, 400);
  }
  const answerId = body.questionId || body.toolUseId;
  if (!answerId || typeof body.answers !== "object") {
    return corsJson({ error: "Missing questionId/toolUseId or answers" }, 400);
  }
  if (!resolvePendingAnswer(answerId, body.answers!)) {
    return corsJson({ error: "Question not found or expired" }, 404);
  }
  return corsJson({ ok: true });
}

// ── Stream Handler ──────────────────────────────────────────────────────

async function handleStreamRequest(req: Request): Promise<Response> {
  const requestStartAt = Date.now();

  // ── Parse request body ────────────────────────────────────────
  let body: RequestBody = {};
  try {
    const raw = await req.text();
    body = raw ? JSON.parse(raw) : {};
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return corsResponse(`Bad Request: ${message}`, 400);
  }

  const {
    prompt: bodyPrompt, userMessage, images: bodyImages, systemPrompt,
    model, baseURL, apiKey: bodyApiKey, conversationId, userId,
    options: bodyOptions = {},
  } = body;

  // ── Resolve effective config ──────────────────────────────────
  const effectiveAuthToken = bodyApiKey || AUTH_TOKEN;
  const effectiveBaseURL = sanitizeBaseURL(baseURL || BASE_URL);
  const sdkBaseURL =
    THINKING_PROXY_URL && (!baseURL || sanitizeBaseURL(baseURL) === BASE_URL)
      ? THINKING_PROXY_URL
      : effectiveBaseURL;
  const effectiveModel = model || bodyOptions.model || DEFAULT_MODEL;
  const rawAllowedTools =
    Array.isArray(bodyOptions.allowedTools) && bodyOptions.allowedTools.length > 0
      ? bodyOptions.allowedTools
      : ["Skill"];
  // AskUserQuestion 必须走 canUseTool 回调，不能被 allowedTools 直接放行
  const allowedTools = rawAllowedTools.filter((t: string) => t !== "AskUserQuestion");
  const settingSources = normalizeSettingSources(bodyOptions.settingSources) ?? DEFAULT_SETTING_SOURCES;
  const rawCwd = typeof bodyOptions.cwd === "string" ? bodyOptions.cwd : undefined;
  const cwd = rawCwd && userId ? ensureIsolatedWorkspace(rawCwd, userId) : rawCwd;
  const includePartialMessages = bodyOptions.includePartialMessages !== false;
  const extraArgs =
    bodyOptions.extraArgs && typeof bodyOptions.extraArgs === "object" && !Array.isArray(bodyOptions.extraArgs)
      ? bodyOptions.extraArgs : undefined;
  const mcpServers = normalizeMcpServers(bodyOptions.mcpServers);
  const hasImages = Array.isArray(bodyImages) && bodyImages.length > 0;
  const systemPromptOption = bodyOptions.systemPrompt ?? systemPrompt ?? DEFAULT_SYSTEM_PROMPT;
  const textPrompt = typeof bodyPrompt === "string" ? bodyPrompt : userMessage!;
  const maxTurns = bodyOptions.maxTurns ?? 100;
  const maxThinkingTokens = bodyOptions.maxThinkingTokens ?? 16384;
  const staticIntro = getStaticIntroConfig(cwd, textPrompt);
  const isResumedConversation = !!(conversationId || bodyOptions.resume);

  // ── Validate ──────────────────────────────────────────────────
  if (rawCwd && !userId) {
    console.warn("[UserWorkspace] Request has cwd but no userId — sessions from different users will share project context!");
  }
  console.log("Request received", {
    hasUserMessage: Boolean(userMessage), hasPrompt: typeof bodyPrompt === "string",
    hasImages, imageCount: hasImages ? bodyImages!.length : 0,
    hasApiKey: Boolean(bodyApiKey || AUTH_TOKEN), baseURL: effectiveBaseURL,
    model: effectiveModel, userId: userId || undefined, cwd: cwd || undefined,
    resume: bodyOptions.resume || conversationId || undefined,
    maxTurns: bodyOptions.maxTurns, maxThinkingTokens: bodyOptions.maxThinkingTokens,
  });

  if (!userMessage && typeof bodyPrompt !== "string") {
    return corsResponse("Missing userMessage (or provide a raw prompt)", 400);
  }
  if (!effectiveAuthToken) {
    return corsResponse("Missing ANTHROPIC_AUTH_TOKEN (either in env or request apiKey)", 400);
  }

  // ── Build SSE stream ──────────────────────────────────────────
  const encoder = new TextEncoder();
  const abortController = new AbortController();
  const idleTimeoutMs = Number(process.env.AGENT_SDK_IDLE_TIMEOUT_MS || 180_000);
  const heartbeatIntervalMs = Number(process.env.AGENT_SDK_HEARTBEAT_INTERVAL_MS || 15_000);

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      let lastEventAt = Date.now();
      let registeredSessionId: string | undefined;
      let userWaitMs = 0;
      const streamQuestionIds = new Set<string>();
      const refreshActivity = () => { lastEventAt = Date.now(); };

      // ── SSE helpers ─────────────────────────────────────────
      const send = (obj: unknown) => {
        if (closed) return;
        try {
          const raw = JSON.stringify(obj);
          const filtered = filterAskUserQuestion(raw);
          if (filtered === null) return;
          controller.enqueue(encoder.encode(`data: ${filtered}\n\n`));
        } catch {
          closed = true;
        }
      };
      const close = () => {
        if (closed) return;
        closed = true;
        try { controller.close(); } catch { /* stream may be locked by pipeThrough */ }
      };

      // ── Timers ──────────────────────────────────────────────
      const idleTimer = setInterval(() => {
        const idleFor = Date.now() - lastEventAt;
        if (idleFor >= idleTimeoutMs) {
          console.warn("Idle timeout waiting for upstream response", { idleTimeoutMs, idleFor });
          send({ type: "error", message: "Stream timed out waiting for upstream response." });
          abortController.abort();
          clearInterval(idleTimer);
          close();
        }
      }, 1_000);

      const heartbeatTimer = setInterval(() => {
        if (closed) return;
        try { controller.enqueue(encoder.encode(`: heartbeat ${Date.now()}\n\n`)); } catch { /* ignore */ }
      }, heartbeatIntervalMs);

      const cleanup = () => {
        clearInterval(idleTimer);
        clearInterval(heartbeatTimer);
        cleanupStreamAnswers(streamQuestionIds);
        if (registeredSessionId) unregisterUsageCallback(registeredSessionId);
        req.signal.removeEventListener("abort", onAbort);
      };
      const onAbort = () => { abortController.abort(); cleanup(); close(); };
      req.signal.addEventListener("abort", onAbort, { once: true });

      // ── Query options ───────────────────────────────────────
      const FILE_UPLOAD_RE = /^\[FILE_UPLOAD(?::([^\]]*))?\]\s*/;

      const queryOptions: Options = {
        abortController,
        ...(sdkBaseURL ? { baseURL: sdkBaseURL } : {}),
        executable: "node",
        includePartialMessages,
        permissionMode: "default",
        allowedTools,
        settingSources,
        maxTurns,
        maxThinkingTokens,

        canUseTool: async (toolName: string, input: any) => {
          if (toolName !== "AskUserQuestion") {
            return { behavior: "allow" as const, updatedInput: input };
          }
          if (abortController.signal.aborted) {
            return { behavior: "deny" as const, message: "Stream already aborted" };
          }

          const isFileUpload = input.questions?.some(
            (q: any) => typeof q.header === "string" && FILE_UPLOAD_RE.test(q.header),
          );
          const questionId = crypto.randomUUID();
          streamQuestionIds.add(questionId);
          refreshActivity();

          if (isFileUpload) {
            const uploads = (input.questions as any[]).map((q: any) => {
              const match = FILE_UPLOAD_RE.exec(q.header || "");
              return {
                prompt: q.question,
                header: (q.header || "").replace(FILE_UPLOAD_RE, "").trim(),
                accept: match?.[1] || undefined,
                description: q.options?.[0]?.description || undefined,
              };
            });
            console.log(`[FileUpload] Emitting file_upload_request ${questionId}`, JSON.stringify(uploads));
            send({ type: "file_upload_request", toolUseId: questionId, questionId, uploads });
          } else {
            console.log(`[AskUserQuestion] Registered pending ${questionId}, relying on SDK-emitted event`);
          }

          const waitStart = Date.now();
          const answers = await waitForAnswer({ questionId, abortController, onActivity: refreshActivity });
          userWaitMs += Date.now() - waitStart;
          refreshActivity();
          console.log(`[${isFileUpload ? "FileUpload" : "AskUserQuestion"}] Got answers for ${questionId}`, JSON.stringify(answers));
          return { behavior: "allow" as const, updatedInput: { ...input, answers } };
        },

        stderr: (data: string) => {
          const reqIdMatch = data.match(/request-id[:\s]+(req_[a-zA-Z0-9_-]+)/i);
          if (reqIdMatch) console.log(`[Anthropic request-id] request-id: ${reqIdMatch[1]}`);
          if (process.env.DEBUG_SDK_HTTP === "1") {
            if (/^(Request|Response|Headers|POST |GET |PUT |DELETE |PATCH |HTTP\/|content-type|authorization|anthropic-|x-api-|user-agent)/im.test(data) || /headers/i.test(data)) {
              console.log(`[Anthropic HTTP debug]\n${data}`);
            }
          }
          console.error("[Claude stderr]", data);
        },

        env: {
          ...process.env,
          PATH: process.env.PATH || "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
          ANTHROPIC_AUTH_TOKEN: effectiveAuthToken,
          ...(process.env.DEBUG_SDK_HTTP === "1" ? { ANTHROPIC_LOG: "debug", DEBUG_CLAUDE_AGENT_SDK: "1" } : {}),
          ...(sdkBaseURL ? { ANTHROPIC_BASE_URL: sdkBaseURL } : {}),
          ANTHROPIC_MODEL: effectiveModel,
          ANTHROPIC_DEFAULT_HAIKU_MODEL: effectiveModel,
          ANTHROPIC_DEFAULT_OPUS_MODEL: effectiveModel,
          ANTHROPIC_DEFAULT_SONNET_MODEL: effectiveModel,
        },

        ...(cwd ? { cwd } : {}),
        ...(extraArgs ? { extraArgs } : {}),
        persistSession: true,
        ...(conversationId ? { resume: conversationId } : {}),
        ...(bodyOptions.resume ? { resume: bodyOptions.resume } : {}),
        ...(bodyOptions.resumeSessionAt ? { resumeSessionAt: bodyOptions.resumeSessionAt } : {}),
        ...(bodyOptions.forkSession !== undefined ? { forkSession: bodyOptions.forkSession } : {}),
        ...(bodyOptions.tools ? { tools: bodyOptions.tools } : {}),
        ...(systemPromptOption !== undefined ? { systemPrompt: systemPromptOption } : {}),
        ...(mcpServers ? { mcpServers } : {}),
      };

      // ── Log options (redact sensitive fields) ───────────────
      const { env, ...restOpts } = queryOptions;
      console.log("Query options:", {
        ...restOpts,
        env: env ? {
          ANTHROPIC_BASE_URL: env.ANTHROPIC_BASE_URL,
          ANTHROPIC_AUTH_TOKEN: env.ANTHROPIC_AUTH_TOKEN ? "[redacted]" : undefined,
          ANTHROPIC_MODEL: env.ANTHROPIC_MODEL,
          ANTHROPIC_DEFAULT_HAIKU_MODEL: env.ANTHROPIC_DEFAULT_HAIKU_MODEL,
          ANTHROPIC_DEFAULT_OPUS_MODEL: env.ANTHROPIC_DEFAULT_OPUS_MODEL,
          ANTHROPIC_DEFAULT_SONNET_MODEL: env.ANTHROPIC_DEFAULT_SONNET_MODEL,
        } : undefined,
      });
      console.log("Query prompt:", hasImages ? `[multimodal: ${bodyImages!.length} image(s)] ${textPrompt}` : textPrompt);

      // ── Run stream session ──────────────────────────────────
      runStreamSession().finally(() => {
        cleanup();
        if (process.env.DEBUG_SDK_HTTP === "1") readDebugLogs();

        const totalMs = Date.now() - requestStartAt;
        const netMs = totalMs - userWaitMs;
        const totalSec = (totalMs / 1000).toFixed(1);
        const netSec = (netMs / 1000).toFixed(1);
        const waitSec = (userWaitMs / 1000).toFixed(1);
        console.log(
          `[RequestDuration] user=${userId || "unknown"} model=${effectiveModel} ` +
          `total=${totalMs}ms (${totalSec}s) net=${netMs}ms (${netSec}s) user_wait=${userWaitMs}ms (${waitSec}s)`,
        );

        send({
          type: "request_duration",
          totalMs,
          netMs,
          userWaitMs,
          userId: userId || undefined,
          model: effectiveModel,
        });

        console.log("Stream ended");
        close();
      });

      async function runStreamSession() {
        // ── 1. Process images in prompt ────────────────────────
        const { text: finalPrompt, resolvedImages } = await processPromptWithImages(
          textPrompt, hasImages ? bodyImages : undefined,
        );
        const prompt: string | AsyncGenerator = resolvedImages.length > 0
          ? buildMultimodalPrompt(finalPrompt, resolvedImages)
          : textPrompt;

        // ── 2. Static intro bypass ─────────────────────────────
        let effectivePrompt: string | AsyncGenerator = prompt;

        if (staticIntro && !isResumedConversation) {
          console.log("[StaticIntro] Matched — sending fixed intro text, skipping LLM for intro");
          send({
            type: "assistant",
            message: { role: "assistant", content: [{ type: "text", text: staticIntro.introText }] },
          });

          if (staticIntro.followUpEvents.length === 0) {
            console.log("[StaticIntro] No follow-up events, closing stream");
            send({ type: "result", result: staticIntro.introText });
            return;
          }

          const allAnswers: string[] = [];
          for (const event of staticIntro.followUpEvents) {
            if (abortController.signal.aborted) break;

            const questionId = crypto.randomUUID();
            streamQuestionIds.add(questionId);
            refreshActivity();

            if (event.type === "file_upload_request") {
              console.log(`[StaticIntro] Emitting file_upload_request ${questionId}`);
              send({ type: "file_upload_request", questionId, uploads: event.uploads });
            } else {
              console.log(`[StaticIntro] Emitting ask_user_question ${questionId}`);
              send({ type: "ask_user_question", toolUseId: questionId, questionId, questions: event.questions });
            }

            const waitStart = Date.now();
            const answers = await waitForAnswer({ questionId, abortController, onActivity: refreshActivity });
            userWaitMs += Date.now() - waitStart;
            refreshActivity();
            console.log(`[StaticIntro] Got answers for ${questionId}`, JSON.stringify(answers));
            allAnswers.push(...Object.values(answers).filter(Boolean));
          }

          if (abortController.signal.aborted) return;

          const resumeText = staticIntro.resumePromptTemplate.replace("{answers}", allAnswers.join(", "));
          const { text: finalResumeText, resolvedImages: answerResolvedImages } =
            await processPromptWithImages(resumeText);
          const allResolvedImages = [...resolvedImages, ...answerResolvedImages];

          effectivePrompt = allResolvedImages.length > 0
            ? buildMultimodalPrompt(finalResumeText, allResolvedImages)
            : resumeText;

          logResolvedImages(allResolvedImages, " (resume)");
          console.log("[StaticIntro] Proceeding to LLM with prompt:", finalResumeText);
        }

        logResolvedImages(resolvedImages, "");

        // ── 3. Query with retry ────────────────────────────────
        const MAX_RETRIES = 3;
        const RETRY_BASE_MS = 3000;

        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
          let seen = 0;
          let hasAssistantText = false;

          try {
            if (attempt > 1) {
              const delay = RETRY_BASE_MS * Math.pow(2, attempt - 2);
              console.log(`[Retry] Attempt ${attempt}/${MAX_RETRIES} after ${delay}ms backoff...`);
              await new Promise((r) => setTimeout(r, delay));
              if (abortController.signal.aborted) break;
            }

            console.log(`Calling query()... (attempt ${attempt}/${MAX_RETRIES})`);
            const queryStream = query({ prompt: effectivePrompt as any, options: queryOptions });
            console.log("query() returned, starting to iterate stream...");

            const eventTypeCounts: Record<string, number> = {};
            const collectedArtifacts: MediaArtifact[] = [];
            const artifactUrlSet = new Set<string>();

            for await (const msg of queryStream) {
              const msgJson = JSON.stringify(msg);
              let msgType: string;
              try { msgType = JSON.parse(msgJson)?.type ?? "unknown"; }
              catch { msgType = (msg as { type?: string }).type ?? "unknown"; }

              eventTypeCounts[msgType] = (eventTypeCounts[msgType] ?? 0) + 1;
              console.log("Stream event received", msgType, msgJson.length > 500 ? msgJson.slice(0, 500) + "..." : msgJson);
              if (seen === 0) console.log("First stream event received");
              seen += 1;
              refreshActivity();

              if (msgType === "assistant" || msgType === "result") hasAssistantText = true;

              // Register usage callback on session init
              if (msgType === "system" && !registeredSessionId) {
                const sid = (msg as any).session_id;
                if (sid && THINKING_PROXY_URL) {
                  registeredSessionId = sid;
                  registerUsageCallback(sid, (usageData: UsageData) => {
                    refreshActivity();
                    send({
                      type: "token_stats",
                      inputTokens: usageData.inputTokens,
                      outputTokens: usageData.outputTokens,
                      cacheReadInputTokens: usageData.cacheReadInputTokens,
                      cacheCreationInputTokens: usageData.cacheCreationInputTokens,
                      model: usageData.model,
                    });
                  });
                }
              }

              // Collect media artifacts from content messages
              if (msgType === "user" || msgType === "assistant" || msgType === "result") {
                const newArtifacts = extractMediaArtifacts(msgJson);
                for (const artifact of newArtifacts) {
                  if (!artifactUrlSet.has(artifact.url)) {
                    artifactUrlSet.add(artifact.url);
                    collectedArtifacts.push(artifact);
                  }
                }
                if (newArtifacts.length > 0) {
                  console.log(`[Artifacts] Extracted ${newArtifacts.length} URL(s) from ${msgType} message (total unique: ${collectedArtifacts.length})`);
                }
              }

              // Block SDK-emitted interactive events (handled via canUseTool)
              if (msgType === "ask_user_question" || msgType === "file_upload_request") {
                console.log(`[StreamFilter] Blocked SDK-emitted ${msgType} from queryStream`);
                continue;
              }

              // Filter AskUserQuestion tool_use from assistant content blocks
              let outMsg: unknown = msg;
              if (msgType === "assistant") {
                const message = (msg as any).message;
                if (message?.content && Array.isArray(message.content)) {
                  const filtered = message.content.filter(
                    (block: any) => !(block.type === "tool_use" && block.name === "AskUserQuestion"),
                  );
                  if (filtered.length === 0) continue;
                  if (filtered.length !== message.content.length) {
                    outMsg = { ...msg, message: { ...message, content: filtered } };
                  }
                }
              }

              // Log session-level usage from result event
              if (msgType === "result") {
                const r = msg as any;
                const u = r.usage;
                const cost = r.total_cost_usd;
                if (u && (u.input_tokens || u.output_tokens)) {
                  const parts = [
                    `input=${u.input_tokens ?? 0}`,
                    `output=${u.output_tokens ?? 0}`,
                    `cache_read=${u.cache_read_input_tokens ?? 0}`,
                    `cache_create=${u.cache_creation_input_tokens ?? 0}`,
                  ];
                  if (cost != null) parts.push(`cost=$${cost}`);
                  if (r.num_turns != null) parts.push(`turns=${r.num_turns}`);
                  if (r.duration_api_ms != null) parts.push(`api_ms=${r.duration_api_ms}`);
                  if (effectiveModel) parts.push(`model=${effectiveModel}`);
                  if (userId) parts.push(`user=${userId}`);
                  console.log(`[Usage] ${parts.join(" ")}`);
                }
                const mu = r.modelUsage;
                if (mu && typeof mu === "object") {
                  for (const [model, info] of Object.entries(mu)) {
                    const m = info as any;
                    console.log(
                      `[Usage:model] ${model} in=${m.inputTokens ?? 0} out=${m.outputTokens ?? 0}` +
                      ` cache_read=${m.cacheReadInputTokens ?? 0} cache_create=${m.cacheCreationInputTokens ?? 0}` +
                      (m.costUSD != null ? ` cost=$${m.costUSD}` : ""),
                    );
                  }
                }
              }

              // Attach collected artifacts to the final result event
              if (msgType === "result" && collectedArtifacts.length > 0) {
                console.log(`[Artifacts] Attaching ${collectedArtifacts.length} artifact(s) to result event`);
                send({ ...(outMsg as object), artifacts: collectedArtifacts });
              } else {
                send(outMsg);
              }
            }

            console.log("Stream stats:", { totalEvents: seen, hasAssistantText, eventTypeCounts });
            if (!hasAssistantText) console.warn("⚠️ Stream ended with NO assistant text message.");
            break; // success — exit retry loop

          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            const stack = err instanceof Error ? err.stack : undefined;
            const isRetryable =
              /overload|saturate|饱和|rate.?limit|503|502|500|ECONNRESET|ETIMEDOUT|socket hang up/i.test(message);
            const canRetry =
              isRetryable && !hasAssistantText && attempt < MAX_RETRIES && !abortController.signal.aborted;

            if (canRetry) {
              console.warn(`[Retry] Transient error on attempt ${attempt}/${MAX_RETRIES}, will retry: ${message}`);
              continue;
            }

            console.error("Stream error:", stack || message);
            send({ type: "error", message, ...(stack ? { stack } : {}) });
            break;
          }
        }
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

// ── Main Router ────────────────────────────────────────────────────────

async function handleRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);

  if (req.method === "OPTIONS") return corsResponse(null, 204);

  const authError = checkAuth(req);
  if (authError) return authError;

  switch (url.pathname) {
    case "/agent-sdk/stream":
      return req.method === "POST" ? handleStreamRequest(req) : corsResponse("Method not allowed", 405);
    case "/agent-sdk/answer":
      return req.method === "POST" ? handleAnswerRequest(req) : corsResponse("Method not allowed", 405);
    case "/agent-sdk/projects":
      return req.method === "GET" ? handleProjectsRoute() : corsResponse("Method not allowed", 405);
    case "/agent-sdk/conversations":
      return req.method === "GET" ? handleConversationsRoute(url) : corsResponse("Method not allowed", 405);
    case "/agent-sdk/history":
      return req.method === "GET" ? handleHistoryRoute(url) : corsResponse("Method not allowed", 405);
    default:
      return corsResponse("Not found", 404);
  }
}

// ── Server ─────────────────────────────────────────────────────────────

const server = Bun.serve({
  port: PORT,
  hostname: "0.0.0.0",
  idleTimeout: Math.min(Number(process.env.AGENT_SDK_HTTP_IDLE_TIMEOUT || 255), 255),
  fetch(req: Request) {
    const traceId = crypto.randomUUID().slice(0, 8);
    return traceStore.run(traceId, () =>
      handleRequest(req).catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        console.error("Server error:", message);
        return corsResponse("Internal error", 500);
      }),
    );
  },
});

console.log(`Agent SDK server listening on http://localhost:${server.port}/agent-sdk/stream`);

