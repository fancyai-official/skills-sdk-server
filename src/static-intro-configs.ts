// ---------------------------------------------------------------------------
// Loads per-app static intro configurations from the YAML file next to this
// module.  The YAML is read once at startup and parsed into the typed config
// map consumed by static-intros.ts.
// ---------------------------------------------------------------------------

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";
import type { StaticIntroEntry } from "./static-intros";

const __dirname = dirname(fileURLToPath(import.meta.url));
const YAML_PATH = resolve(__dirname, "static-intro-configs.yaml");

function loadConfigs(): Record<string, StaticIntroEntry> {
  try {
    const raw = readFileSync(YAML_PATH, "utf-8");
    const parsed = yaml.load(raw) as Record<string, StaticIntroEntry> | null;
    if (!parsed || typeof parsed !== "object") {
      console.warn("[StaticIntro] YAML config is empty or invalid, no static intros registered");
      return {};
    }
    console.log(`[StaticIntro] Loaded ${Object.keys(parsed).length} app config(s) from ${YAML_PATH}`);
    for (const [appKey, entry] of Object.entries(parsed)) {
      const enFollow = (entry as any).followUpEvents?.en?.length ?? 0;
      const zhFollow = (entry as any).followUpEvents?.zh?.length ?? 0;
      console.log(`[StaticIntro]   ${appKey}: triggers=${(entry as any).triggerPhrases?.length ?? 0}, followUp(en=${enFollow}, zh=${zhFollow})`);
    }
    return parsed;
  } catch (err) {
    console.error("[StaticIntro] Failed to load YAML config:", err);
    return {};
  }
}

export const INTRO_CONFIGS: Record<string, StaticIntroEntry> = loadConfigs();
