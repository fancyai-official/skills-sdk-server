/**
 * Image & media processing utilities — compression, resolution, multimodal
 * prompt building, and media artifact extraction from stream events.
 */

import sharp from "sharp";
import type { ImageAttachment } from "./types";

// ── Media Artifacts ────────────────────────────────────────────────────

export interface MediaArtifact {
  type: "image" | "video" | "document";
  url: string;
  name?: string;
}

/**
 * Scan a JSON-stringified message for generated media URLs.  Detects:
 *
 * 1. Script markers — `[IMAGE_URL]`, `[CAMPAIGN_IMAGE_URL]`, `[VIDEO_URL]`
 * 2. Markdown images — `![alt](url)`
 * 3. Document URLs — bare CDN URLs ending in `.md` / `.pdf` etc.
 */
export function extractMediaArtifacts(jsonStr: string): MediaArtifact[] {
  const artifacts: MediaArtifact[] = [];
  let m: RegExpExecArray | null;

  const imageMarkerRe = /\[(?:IMAGE_URL|CAMPAIGN_IMAGE_URL)\]\s+(?:([^\s"\\]+?)\s+)?(https?:\/\/[^\s"\\]+)/g;
  while ((m = imageMarkerRe.exec(jsonStr)) !== null) {
    let rawName: string | undefined = m[1];
    let url = m[2];
    if (rawName && /^https?:\/\//.test(rawName)) {
      url = rawName;
      rawName = undefined;
    }
    const name = rawName?.replace(/:$/, "") || undefined;
    artifacts.push({ type: "image", url, ...(name ? { name } : {}) });
  }

  const videoMarkerRe = /\[VIDEO_URL\]\s+(https?:\/\/[^\s"\\]+)/g;
  while ((m = videoMarkerRe.exec(jsonStr)) !== null) {
    artifacts.push({ type: "video", url: m[1] });
  }

  const mdImageRe = /!\[[^\]]*\]\((https?:\/\/[^\s)"\\]+)\)/g;
  while ((m = mdImageRe.exec(jsonStr)) !== null) {
    artifacts.push({ type: "image", url: m[1] });
  }

  const docRe = /(https?:\/\/[^\s"\\]+\.(?:md|pdf|docx?))\b/g;
  while ((m = docRe.exec(jsonStr)) !== null) {
    artifacts.push({ type: "document", url: m[1] });
  }

  return artifacts;
}

// ── Image Compression & Resolution ─────────────────────────────────────

const IMAGE_MAX_DIM = 1024;
const IMAGE_MAX_BYTES = 1_048_576; // 1 MB

export async function compressImage(
  input: Buffer,
): Promise<{ data: string; media_type: string }> {
  const meta = await sharp(input).metadata();
  const origW = meta.width ?? 0;
  const origH = meta.height ?? 0;

  let pipeline = sharp(input).rotate();
  if (origW > IMAGE_MAX_DIM || origH > IMAGE_MAX_DIM) {
    pipeline = pipeline.resize(IMAGE_MAX_DIM, IMAGE_MAX_DIM, { fit: "inside", withoutEnlargement: true });
  }

  let buf = await pipeline.jpeg({ quality: 100 }).toBuffer();

  let scale = 0.9;
  while (buf.byteLength > IMAGE_MAX_BYTES && scale >= 0.3) {
    const targetW = Math.max(1, Math.round(Math.min(origW, IMAGE_MAX_DIM) * scale));
    const targetH = Math.max(1, Math.round(Math.min(origH, IMAGE_MAX_DIM) * scale));
    buf = await sharp(input)
      .rotate()
      .resize(targetW, targetH, { fit: "inside", withoutEnlargement: true })
      .jpeg({ quality: 100 })
      .toBuffer();
    scale -= 0.1;
  }

  const finalMeta = await sharp(buf).metadata();
  console.log(
    `[ImageCompress] ${Math.round(input.byteLength / 1024)}KB → ${Math.round(buf.byteLength / 1024)}KB JPEG (${finalMeta.width}×${finalMeta.height})`,
  );
  return { data: buf.toString("base64"), media_type: "image/jpeg" };
}

export async function resolveImagesToBase64(images: ImageAttachment[]): Promise<ImageAttachment[]> {
  return Promise.all(
    images.map(async (img) => {
      if (img.data) {
        try {
          const raw = Buffer.from(img.data, "base64");
          const { data, media_type } = await compressImage(raw);
          return { data, media_type } as ImageAttachment;
        } catch (err) {
          console.warn(`[ImageCompress] Failed to compress base64 image: ${err instanceof Error ? err.message : err}, using raw`);
          return img;
        }
      }
      if (!img.url) return img;
      try {
        const resp = await fetch(img.url, { signal: AbortSignal.timeout(50_000) });
        if (!resp.ok) {
          console.warn(`[ImageResolve] HTTP ${resp.status} for ${img.url}, falling back to URL`);
          return img;
        }
        const buffer = Buffer.from(await resp.arrayBuffer());
        console.log(`[ImageResolve] Downloaded ${img.url} (${Math.round(buffer.byteLength / 1024)}KB), compressing...`);
        const { data, media_type } = await compressImage(buffer);
        return { data, media_type } as ImageAttachment;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[ImageResolve] Failed to fetch/compress ${img.url}: ${msg}, falling back to URL`);
        return img;
      }
    }),
  );
}

// ── Multimodal Prompt Building ─────────────────────────────────────────

export function buildMultimodalContentBlocks(
  text: string,
  images: ImageAttachment[],
): Array<Record<string, unknown>> {
  const blocks: Array<Record<string, unknown>> = [];
  for (const img of images) {
    if (img.data) {
      blocks.push({
        type: "image",
        source: { type: "base64", media_type: img.media_type || "image/jpeg", data: img.data },
      });
    } else if (img.url) {
      blocks.push({
        type: "image",
        source: { type: "url", url: img.url },
      });
    }
  }
  if (text) {
    blocks.push({ type: "text", text });
  }
  return blocks;
}

export async function* buildMultimodalPrompt(
  text: string,
  images: ImageAttachment[],
  sessionId?: string,
): AsyncGenerator<{ type: "user"; session_id: string; message: { role: "user"; content: unknown }; parent_tool_use_id: null }> {
  yield {
    type: "user" as const,
    session_id: sessionId || crypto.randomUUID(),
    message: {
      role: "user" as const,
      content: buildMultimodalContentBlocks(text, images),
    },
    parent_tool_use_id: null,
  };
}

// ── Prompt Image Extraction ────────────────────────────────────────────

export const IMAGE_URL_RE = /https?:\/\/[^\s"'<>]+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"'<>]*)?/gi;

export interface ProcessedPrompt {
  text: string;
  resolvedImages: ImageAttachment[];
}

/**
 * Extract image URLs from text, merge with body images, resolve all to base64,
 * and replace inline URLs with `[product_img_url:...]` metadata tags.
 */
export async function processPromptWithImages(
  text: string,
  bodyImages?: ImageAttachment[],
): Promise<ProcessedPrompt> {
  const promptImageUrls = (text.match(IMAGE_URL_RE) || []) as string[];
  const promptImages: ImageAttachment[] = promptImageUrls.map((url) => ({ url }));
  const allImages: ImageAttachment[] = [...(bodyImages || []), ...promptImages];

  if (promptImageUrls.length > 0) {
    console.log(`[ImageExtract] Found ${promptImageUrls.length} image URL(s) in prompt text:`, promptImageUrls);
  }

  const resolvedImages = allImages.length > 0 ? await resolveImagesToBase64(allImages) : [];

  let processedText = text;
  if (promptImageUrls.length > 0) {
    processedText = promptImageUrls
      .reduce((t, url) => t.replace(url, ""), processedText)
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const urlTags = promptImageUrls.map((url) => `[product_img_url:${url}]`).join("\n");
    processedText = processedText ? `${processedText}\n\n${urlTags}` : urlTags;
  }

  return { text: processedText, resolvedImages };
}

/**
 * Log a summary of resolved images being sent to Claude.
 */
export function logResolvedImages(images: ImageAttachment[], context: string): void {
  if (images.length === 0) return;
  const sizes = images.map((img) => {
    const kb = img.data ? Math.round((img.data.length * 3) / 4 / 1024) : 0;
    return `${kb}KB ${img.media_type || "unknown"}`;
  });
  console.log(`[QueryInput] Sending ${images.length} image(s) to Claude${context}: [${sizes.join(", ")}]`);
}
