import { AsyncLocalStorage } from "node:async_hooks";

export const traceStore = new AsyncLocalStorage<string>();

const _origLog = console.log;
const _origWarn = console.warn;
const _origError = console.error;
const _prefix = () => {
  const ts = new Date().toISOString().replace("T", " ").slice(0, 23);
  const tid = traceStore.getStore();
  return tid ? `[${ts}] [${tid}]` : `[${ts}]`;
};
console.log = (...args: unknown[]) => _origLog(_prefix(), ...args);
console.warn = (...args: unknown[]) => _origWarn(_prefix(), ...args);
console.error = (...args: unknown[]) => _origError(_prefix(), ...args);
