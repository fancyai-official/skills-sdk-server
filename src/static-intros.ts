// ---------------------------------------------------------------------------
// Static intro responses — bypass LLM for self-introduction messages.
//
// Each app can register a static intro config keyed by a substring that
// appears in the request `cwd`.  When the user message matches a known
// trigger phrase the server returns the fixed text directly (+ optional
// follow-up events) without ever calling `query()`.
//
// App-specific configurations live in ./static-intro-configs.ts.
// ---------------------------------------------------------------------------

import { INTRO_CONFIGS } from "./static-intro-configs";

// ── Types ──────────────────────────────────────────────────────────────────

export interface FileUploadFollowUp {
  type: "file_upload_request";
  uploads: Array<{
    prompt: string;
    header: string;
    accept?: string;
    description?: string;
  }>;
}

export interface AskQuestionFollowUp {
  type: "ask_user_question";
  questions: Array<{
    question: string;
    header: string;
    options: Array<{ label: string; value?: string; description?: string }>;
  }>;
}

export type FollowUpEvent = FileUploadFollowUp | AskQuestionFollowUp;

export interface StaticIntroEntry {
  triggerPhrases: string[];
  introText: { en: string; zh: string };
  followUpEvents: { en: FollowUpEvent[]; zh: FollowUpEvent[] };
  resumePromptTemplate: string;
}

export interface ResolvedStaticIntro {
  introText: string;
  followUpEvents: FollowUpEvent[];
  resumePromptTemplate: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const CJK_RE = /[\u4e00-\u9fff\u3400-\u4dbf]/;

function detectLanguage(message: string): "en" | "zh" {
  return CJK_RE.test(message) ? "zh" : "en";
}

const TRAILING_PUNCT_RE = /[\s.!?。！？，,;；:：~…]+$/;

function normalize(text: string): string {
  return text.trim().toLowerCase().replace(TRAILING_PUNCT_RE, "");
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Check whether `message` is a static-intro trigger for the app identified
 * by `cwd`.  Returns a resolved config (with the correct language variant
 * already selected) or `null` if this request should go through the LLM.
 */
export function getStaticIntroConfig(
  cwd: string | undefined,
  message: string,
): ResolvedStaticIntro | null {
  if (!cwd || !message) return null;

  const normalizedMsg = normalize(message);

  for (const [appKey, entry] of Object.entries(INTRO_CONFIGS)) {
    if (!cwd.includes(appKey)) continue;

    const matched = entry.triggerPhrases.some(
      (phrase) => normalizedMsg === normalize(phrase),
    );
    if (!matched) return null;

    const lang = detectLanguage(message);
    const followUp = entry.followUpEvents?.[lang];
    console.log(`[StaticIntro] Matched app=${appKey}, lang=${lang}, followUpEvents=${JSON.stringify(followUp?.length ?? "undefined")}`);
    return {
      introText: entry.introText[lang],
      followUpEvents: followUp ?? [],
      resumePromptTemplate: entry.resumePromptTemplate,
    };
  }

  return null;
}
