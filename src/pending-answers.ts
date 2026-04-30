/**
 * Manages the pending-answer state for AskUserQuestion / file_upload_request
 * interactions.  The stream handler registers a pending promise when Claude
 * asks the user a question; the `/answer` endpoint resolves it when the
 * frontend sends back the user's selection.
 */

/** 0 = wait indefinitely (no auto-continue); positive value = timeout in ms */
export const ANSWER_TIMEOUT_MS = Number(process.env.AGENT_SDK_ANSWER_TIMEOUT_MS ?? 0);

export interface PendingAnswer {
  resolve: (answers: Record<string, string>) => void;
  timer: ReturnType<typeof setTimeout> | null;
  keepAlive: ReturnType<typeof setInterval>;
}

export const pendingAnswers = new Map<string, PendingAnswer>();

/**
 * Block until the frontend submits an answer for `questionId`, or until
 * abort fires.  If timeoutMs > 0, also resolves with empty answers on timeout.
 * When timeoutMs is 0 (default), waits indefinitely — only user reply or
 * abort will unblock.
 *
 * @param onActivity  Called every 10 s to keep the stream's idle timer alive.
 */
export function waitForAnswer(opts: {
  questionId: string;
  abortController: AbortController;
  onActivity: () => void;
  timeoutMs?: number;
}): Promise<Record<string, string>> {
  const { questionId, abortController, onActivity, timeoutMs = ANSWER_TIMEOUT_MS } = opts;

  return new Promise<Record<string, string>>((resolve) => {
    const onAbort = () => {
      if (timer) clearTimeout(timer);
      clearInterval(keepAlive);
      pendingAnswers.delete(questionId);
      console.log(`[PendingAnswer] Abort fired during wait for ${questionId}, not resolving`);
    };
    if (abortController.signal.aborted) { onAbort(); return; }
    abortController.signal.addEventListener("abort", onAbort, { once: true });

    const timer = timeoutMs > 0
      ? setTimeout(() => {
          abortController.signal.removeEventListener("abort", onAbort);
          console.warn(`[PendingAnswer] Timeout for ${questionId}, resolving with empty answers`);
          pendingAnswers.delete(questionId);
          resolve({});
        }, timeoutMs)
      : null;

    const keepAlive = setInterval(() => { onActivity(); }, 10_000);

    pendingAnswers.set(questionId, {
      resolve: (ans) => {
        abortController.signal.removeEventListener("abort", onAbort);
        if (timer) clearTimeout(timer);
        clearInterval(keepAlive);
        pendingAnswers.delete(questionId);
        resolve(ans);
      },
      timer,
      keepAlive,
    });
  });
}

/**
 * Clean up all pending answers that belong to a specific stream session.
 */
export function cleanupStreamAnswers(questionIds: Set<string>): void {
  for (const qId of questionIds) {
    const pending = pendingAnswers.get(qId);
    if (pending) {
      if (pending.timer) clearTimeout(pending.timer);
      clearInterval(pending.keepAlive);
      pendingAnswers.delete(qId);
    }
  }
  questionIds.clear();
}

/**
 * Resolve a pending answer by ID.  If the exact ID is not found, falls back
 * to the most recent pending answer (there is usually only one at a time).
 *
 * @returns `true` if a matching pending answer was found and resolved.
 */
export function resolvePendingAnswer(
  answerId: string,
  answers: Record<string, string>,
): boolean {
  let pending = pendingAnswers.get(answerId);

  if (!pending && pendingAnswers.size > 0) {
    const entry = pendingAnswers.entries().next().value;
    const [fallbackId, fallbackPending] = entry as [string, PendingAnswer];
    console.log(`[Answer] Fallback: mapped ${answerId} → ${fallbackId}`);
    pending = fallbackPending;
  }

  if (!pending) return false;

  console.log(`[AskUserQuestion] Answer received for ${answerId}`, JSON.stringify(answers));
  pending.resolve(answers);
  return true;
}
