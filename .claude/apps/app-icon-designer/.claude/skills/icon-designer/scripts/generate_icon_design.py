#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Icon Designer — Asset Generator
Generates on-model garment imagery designed through a legendary fashion icon's lens.
Supports 3 shot types: front, side, back. Supports parallel generation of multiple shots.

Usage (single shot):
    python generate_icon_design.py --designer "Coco Chanel" --shot front \
        --piece_name "Bouclé Evening Jacket" --category "Outerwear" \
        --silhouette "boxy, chain-weighted hem" --materials "Linton bouclé tweed" \
        --palette "Midnight navy, ivory piping" --construction "chain hem, pearl buttons" \
        --signatures "camellia, contrast piping" --styling "over silk slip dress" \
        --gender "Womenswear" --output projects/icon-design/outputs/jacket_front.png

Usage (parallel multi-shot):
    python generate_icon_design.py --designer "Coco Chanel" --shots side back \
        --piece_name "Bouclé Evening Jacket" --category "Outerwear" \
        --silhouette "boxy, chain-weighted hem" --materials "Linton bouclé tweed" \
        --palette "Midnight navy, ivory piping" --construction "chain hem, pearl buttons" \
        --signatures "camellia, contrast piping" --styling "over silk slip dress" \
        --gender "Womenswear" \
        --reference projects/icon-design/outputs/jacket_front.png \
        --face_lock projects/icon-design/outputs/jacket_front.png \
        --outputs projects/icon-design/outputs/jacket_side.png \
                  projects/icon-design/outputs/jacket_back.png
"""

import argparse
import sys
import os
import json
import urllib.request
from typing import Optional

# Add current scripts directory to path for image_generator_factory and its deps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from image_generator_factory import (
    batch_step1_submit_tasks,
    batch_step2_poll_tasks,
)

# ---------------------------------------------------------------------------
# Designer aesthetic directives — injected into every prompt
# ---------------------------------------------------------------------------

DESIGNER_DIRECTIVES = {
    "coco chanel": """DESIGNER DNA — COCO CHANEL:
This garment embodies Chanel's philosophy: liberation through simplicity, practical elegance, androgynous ease.
- AESTHETIC: Clean, relaxed, effortlessly refined. No excess, no discomfort, no ostentation.
- PALETTE: Black, white, navy, beige, cream. Gold hardware. Touches of red only when deliberate.
- MATERIALS: Bouclé tweed, jersey knit, silk charmeuse, lambskin. Chain trim. Pearl accents.
- SIGNATURES TO INCLUDE (if present in brief): Camellia flowers, interlocking CC, contrast piping, grosgrain ribbon, pearl buttons, quilted accents, two-tone color blocking, chain-weighted hems.
- SILHOUETTE LANGUAGE: Relaxed, boxy but feminine. Nothing constricting. The body moves freely. Knee-length or midi.
- STYLING FEEL: The woman has been wearing this forever. Costume jewelry over real. Layered chains. Effortless Parisian luxury.
- NEVER: Loud prints, excessive skin exposure, uncomfortable-looking construction, trend-chasing novelty.""",

    "alexander mcqueen": """DESIGNER DNA — ALEXANDER McQUEEN:
This garment embodies McQueen's philosophy: romantic brutalism — savage beauty in impeccable tailoring.
- AESTHETIC: Dramatic tension between fragility and strength. Gothic romance meets Savile Row precision. If it doesn't make you gasp, it's not done.
- PALETTE: Black (always), blood red, bone white, iridescent silver, dusty rose, decayed gold. Colors of cathedrals and butterfly wings.
- MATERIALS: Skull-lace, feathers (hand-placed), distressed leather, laser-cut fabric, duchesse satin, horsehair. Haute embroidery.
- SIGNATURES TO INCLUDE (if present in brief): Skull motifs, harness straps, exaggerated shoulders, nature references (birds, butterflies, shells, antlers), exposed spine/skeletal construction, memento mori symbolism.
- SILHOUETTE LANGUAGE: Extreme. Razor shoulders, impossibly cinched waists, dramatic volume shifts. Corseted torsos, billowing skirts.
- STYLING FEEL: Arming a warrior queen. Every piece has aggression AND vulnerability. Platform boots with lace. Skull-print linings.
- NEVER: Safe, expected, merely "pretty." Mediocrity is the only sin.""",

    "giorgio armani": """DESIGNER DNA — GIORGIO ARMANI:
This garment embodies Armani's philosophy: the power of restraint — soft structure, quiet authority.
- AESTHETIC: Understated, deconstructed, fluid. Remove the armor, keep the power. If you can see the design, it failed.
- PALETTE: Greige (grey-beige), navy, taupe, sand, midnight blue, charcoal, pewter. One accent per look, never more. The palette of Milan twilight.
- MATERIALS: Unlined wool crepe, cashmere jersey, fluid silk, matte velvet, washed linen. Fabrics that drape, never fight the body.
- SIGNATURES TO INCLUDE (if present in brief): The unstructured blazer, one-button closure, collarless jacket, fluid palazzo trousers, the "no makeup" look in fashion. Crystal-encrusted evening as contrast.
- SILHOUETTE LANGUAGE: Soft, relaxed, flowing. Deconstructed shoulders, unlined blazers, wide trousers. Nothing sharp — everything moves.
- STYLING FEEL: One beautiful piece, worn simply. Blazer over t-shirt. Fluid trouser with silk camisole. Looks like they woke up this elegant.
- NEVER: Visible logos, theatrical drama, anything that TRIES to be noticed. Effort is failure.""",

    "valentino garavani": """DESIGNER DNA — VALENTINO GARAVANI:
This garment embodies Valentino's philosophy: couture drama — romance at opera-level grandeur.
- AESTHETIC: Grand, romantic, unapologetically glamorous. Each piece makes the wearer the most beautiful person in the room.
- PALETTE: ROSSO VALENTINO red (#D0021B) — THE red. Also ivory, black, blush pink, midnight navy. When in doubt, make it red.
- MATERIALS: Silk gazar, silk faille, Chantilly lace, point d'esprit tulle, duchess satin, organza. Italian mills. Hand-embroidery from the Roman atelier.
- SIGNATURES TO INCLUDE (if present in brief): Rockstud hardware, the V logo, cascading ruffles, opera-length capes, bow details, lace overlays, the red gown that stops the room.
- SILHOUETTE LANGUAGE: Grand theatre. Floor-sweeping gowns, dramatic capes, fitted bodices with exploding skirts. Or: the Valentino sheath — razor-clean and devastating.
- STYLING FEEL: Maximum romance with couture precision. A red gown needs nothing else. Simplicity with one grand gesture.
- NEVER: Synthetic fabrics, underdressing a moment that matters, cutting corners on handwork, anything that doesn't make the wearer feel extraordinary.""",

    "christian dior": """DESIGNER DNA — CHRISTIAN DIOR:
This garment embodies Dior's philosophy: the New Look — architecture of femininity, women as flowers.
- AESTHETIC: Structured femininity, sculptural elegance, the beauty of form. The outside is a flower; the inside is an engineering project.
- PALETTE: Pale pink, dove grey, navy, cream, black, soft blue. Gentle, feminine, the palette of a French garden in spring.
- MATERIALS: Silk taffeta (for volume and rustling), duchess satin, wool crepe, tulle, organza. Cannage quilting. Heavy fabrics that hold sculptural shapes.
- SIGNATURES TO INCLUDE (if present in brief): Bar jacket silhouette, cannage quilting, toile de Jouy, the bee motif, lily of the valley, full circle skirt, nipped waist, structured fascinator pairing.
- SILHOUETTE LANGUAGE: THE New Look: cinched waist, rounded shoulders, full skirt, elongated line. Every silhouette starts from the waist. A-line, H-line, architectural letters.
- STYLING FEEL: Head to toe composition — hat, gloves, bag, shoes all part of one thought. Feminine, never casual. Structured but never stiff.
- NEVER: Flat or shapeless garments, ignoring the waist, sportswear aesthetics, industrial materials. She should look like she stepped out of a painting.""",

    "yves saint laurent": """DESIGNER DNA — YVES SAINT LAURENT:
This garment embodies YSL's philosophy: the borrowed wardrobe — power dressing as art.
- AESTHETIC: Take what's in men's closets and make it feminine POWER. Art on the body. Androgynous provocation.
- PALETTE: Black (Le Smoking), navy, jewel tones (emerald, sapphire, amethyst), bold primaries (Mondrian), gold, hot pink. Color used like paint.
- MATERIALS: Wool gabardine (tailoring), silk mousseline, velvet, jersey, satin for evening. African and Moroccan textiles. Jet and gold embroidery.
- SIGNATURES TO INCLUDE (if present in brief): Le Smoking tuxedo, safari jacket, the Mondrian dress, the sheer blouse, the pantsuit, art-inspired prints (Van Gogh, Matisse, Picasso), Moroccan/North African influence, the heart logo sketch.
- SILHOUETTE LANGUAGE: Menswear structure adapted for women. Sharp tuxedo jacket with feminine proportions. Belted safari jacket. Also: flowing caftan, draped evening gown. Masters both tailored precision and bohemian flow.
- STYLING FEEL: Androgynous power meets sensual femininity. Tuxedo with nothing underneath. Safari jacket over bare legs. Sheer blouse with masculine trouser. The tension IS the point.
- NEVER: Make a woman look smaller, timid, passive. Design without cultural reference. Play it safe when art can be worn.""",
}

# ---------------------------------------------------------------------------
# Shot directives
# ---------------------------------------------------------------------------

SHOT_DIRECTIVES = {
    "front": """FRONT VIEW — FULL BODY:
Model facing camera directly. Complete outfit visible from head to shoes.
All front-facing details clearly visible: closure, buttons, pockets, collar, drape of fabric, hardware.
Clean, confident pose — weight slightly shifted, editorial bearing.
This is the HERO shot — the garment's first impression.""",

    "side": """SIDE VIEW — PROFILE:
Model turned 90° to show the garment's profile silhouette.
Volume, structure, and drape visible from the side — how the garment falls, extends, and moves.
Shoulder construction, sleeve hang, hem line, and any architectural details visible from this angle.
Head turned slightly toward camera to confirm model identity.
The garment MUST be IDENTICAL to the front reference — same color, material, construction, every detail.""",

    "back": """BACK VIEW — FULL BODY:
Model turned 180° away from camera. Complete back visible.
Back construction clearly shown: seam lines, vent, yoke, zipper, back closure, rear pockets, any back details.
Fabric drape and silhouette from behind — how the garment falls on the body from this angle.
Head turned 15° to confirm model identity.
The garment MUST be IDENTICAL to the front reference — same color, material, construction, every detail.""",
}

# ---------------------------------------------------------------------------
# Shared quality directives
# ---------------------------------------------------------------------------

PRODUCT_FIDELITY = """PRODUCT FIDELITY — ABSOLUTE REQUIREMENT:
The garment in the output MUST match the reference image exactly.
- MATERIAL & TEXTURE: Exact match — same weave, sheen, weight, surface quality
- COLOR: Exact hue and tone — no color drift
- SILHOUETTE: Exact proportions — sleeve length, hem, shoulder, waist all unchanged
- CONSTRUCTION: Every button, zipper, stitch, pocket, collar, cuff reproduced. Nothing added or removed.
- FIT & DRAPE: Consistent with garment construction
You are photographing THIS EXACT garment — not designing a similar one."""

PHOTO_REALISM = """PHOTOGRAPHIC REALISM — REAL PHOTOGRAPH, NOT AI RENDER:
- Clean digital capture — NO film grain, NO color grading, NO vintage filters
- Sharp focus across the full garment
- Natural depth of field (85mm lens equivalent)
- Natural skin texture, accurate skin tones
- Correct hand anatomy, natural body proportions
- Fabric obeys gravity: wrinkles at joints, natural drape
- Studio backdrop: seamless paper or minimal architectural space
AVOID: waxy skin, melted fingers, floating fabric, impossible anatomy, HDR processing"""

MODEL_QUALITY = """MODEL QUALITY — PROFESSIONAL FASHION MODEL:
- Editorial bone structure — defined cheekbones, clean jawline, symmetrical features
- Expression: subtle editorial — quiet confidence, NOT a stock-photo smile
- Hands: relaxed, elegant, natural fingers
- Hair: styled and camera-ready, moves naturally
- Proportions: fashion-model body — tall, lean, elongated limbs
- Bearing: effortless confidence — relaxed shoulders, elongated neck"""

FACE_LOCK = """FACE LOCK — SAME MODEL:
This model MUST be the same person as in the reference image — same face, hair, skin tone, bone structure, expression quality. Different angle, same person."""

AVOID_LIST = """EXPLICITLY AVOID:
- Film grain, vintage filters, HDR processing, color grading
- Waxy/plastic skin, melted fingers, floating fabric, impossible anatomy
- AI artifacts: smooth gradients replacing real surfaces, unnaturally perfect symmetry
- Generic/stock imagery feel — every output should feel intentional and curated
- Text, logos, watermarks, or typography in the image"""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(args):
    designer_key = args.designer.strip().lower()
    designer_block = DESIGNER_DIRECTIVES.get(designer_key, "")
    if not designer_block:
        for key in DESIGNER_DIRECTIVES:
            if key in designer_key or designer_key in key:
                designer_block = DESIGNER_DIRECTIVES[key]
                break

    if not designer_block:
        print(f"Warning: Unknown designer '{args.designer}'. Using generic fashion direction.")
        designer_block = f"Design in the aesthetic philosophy of {args.designer}."

    shot_block = SHOT_DIRECTIVES.get(args.shot, SHOT_DIRECTIVES["front"])

    has_reference = args.reference and len(args.reference) > 0
    fidelity_block = PRODUCT_FIDELITY if has_reference else ""
    face_block = FACE_LOCK if args.face_lock else ""

    parts = [
        f"Professional fashion lookbook photograph — designed by {args.designer}.",
        "",
        shot_block,
        "",
        f"Piece: {args.piece_name}" if args.piece_name else "",
        f"Category: {args.category}" if args.category else "",
        f"Silhouette: {args.silhouette}" if args.silhouette else "",
        f"Material: {args.materials}" if args.materials else "",
        f"Colorway: {args.palette}" if args.palette else "",
        f"Construction: {args.construction}" if args.construction else "",
        f"Signature elements: {args.signatures}" if args.signatures else "",
        f"Styling: {args.styling}" if args.styling else "",
        f"Gender: {args.gender}" if args.gender else "",
        "",
        designer_block,
        "",
        fidelity_block,
        face_block,
        MODEL_QUALITY,
        "",
        PHOTO_REALISM,
        "",
        AVOID_LIST,
    ]
    return "\n".join(p for p in parts if p is not None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _collect_refs(args):
    """
    Collect reference image paths/URLs from args.

    Accepts both local file paths and HTTP(S) URLs — both are supported
    by the underlying gen_file_id(image_path_or_url=...) API.
    Deduplicates entries and caps at 3 (API limit).
    """
    refs = []
    seen = set()

    def _add(ref):
        if ref in seen or len(refs) >= 3:
            return
        if _is_url(ref):
            refs.append(ref)
            seen.add(ref)
        elif os.path.exists(ref):
            refs.append(ref)
            seen.add(ref)
        else:
            print(f"  Warning: reference image not found: {ref}")

    if args.reference:
        for ref in args.reference:
            _add(ref)

    if args.face_lock:
        _add(args.face_lock)

    return refs


def _download_url_to_file(url: str, path: str) -> bool:
    """Download an image from a URL to a local file path."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        urllib.request.urlretrieve(url, path)
        return True
    except Exception as e:
        print(f"  Error downloading {url} to {path}: {e}")
        return False


# ---------------------------------------------------------------------------
# State file helpers  (for 3-step split mode)
# ---------------------------------------------------------------------------

def _load_state(state_file: str) -> dict:
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state_file: str, state: dict):
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"[STATE] Saved: {state_file}")


# ---------------------------------------------------------------------------
# Three-step split mode
# ---------------------------------------------------------------------------

def run_step1(args):
    """
    Step 1: Build prompts, submit tasks in parallel, save task_ids to state file.
    Each subsequent step only needs --state_file.
    """
    shots = args.shots if args.shots else [args.shot]
    outputs = args.outputs if args.shots else ([args.output] if args.output else [None])
    # Pad outputs list if shorter than shots
    while len(outputs) < len(shots):
        outputs.append(None)

    refs = _collect_refs(args)
    ratio = args.ratio or "3:4"
    resolution = args.resolution or "2K"

    provider = args.provider or os.environ.get("ICON_DESIGNER_PROVIDER", "mock")

    tasks = []
    for shot in shots:
        shot_args = argparse.Namespace(**vars(args))
        shot_args.shot = shot
        prompt = _build_prompt(shot_args)
        label = f"{args.designer} / {shot}"
        if args.piece_name:
            label += f" / {args.piece_name}"
        tasks.append({
            "task_name": label,
            "img_urls": refs if refs else None,
            "prompt": prompt,
            "ratio": ratio,
            "resolution": resolution,
            "provider": provider,
        })

    print(f"[STEP 1] Submitting {len(tasks)} task(s) in parallel (provider={provider})...")
    submitted = batch_step1_submit_tasks(tasks)

    state_tasks = []
    for item, output_path in zip(submitted, outputs):
        state_tasks.append({
            "task_name": item["task_name"],
            "task_id":   item.get("task_id"),
            "file_url":  None,
            "output":    output_path,
            "status":    item["status"],   # "ok" | "failed"
        })

    state = {"tasks": state_tasks}
    _save_state(args.state_file, state)

    ok = sum(1 for t in state_tasks if t["status"] == "ok")
    print(f"[STEP 1 DONE] {ok}/{len(state_tasks)} submitted. Run step2 next.")


def run_step2(args):
    """
    Step 2: Load state file, poll task_ids in parallel, update file_urls.
    Re-run this step if any tasks are still PENDING.
    """
    state = _load_state(args.state_file)
    tasks = state["tasks"]

    poll_infos = [
        {"task_name": t["task_name"], "task_id": t["task_id"]}
        for t in tasks
        if t.get("task_id") and t.get("status") not in ("ready", "saved", "failed")
    ]

    if not poll_infos:
        print("[STEP 2] No tasks to poll (all already ready/failed/saved).")
        return

    print(f"[STEP 2] Polling {len(poll_infos)} task(s)...")
    polled = batch_step2_poll_tasks(poll_infos)

    polled_map = {r["task_name"]: r for r in polled}
    for t in tasks:
        name = t["task_name"]
        if name in polled_map:
            r = polled_map[name]
            if r["status"] == "ready":
                t["file_url"] = r["file_url"]
                t["status"] = "ready"
            elif r["status"] == "pending":
                t["status"] = "pending"
            elif r["status"] == "failed":
                t["status"] = "failed"

    _save_state(args.state_file, state)

    ready   = sum(1 for t in tasks if t["status"] == "ready")
    pending = sum(1 for t in tasks if t["status"] == "pending")
    failed  = sum(1 for t in tasks if t["status"] == "failed")
    print(f"[STEP 2 DONE] ready={ready} pending={pending} failed={failed}")
    if pending:
        print("  Some tasks still PENDING — run step2 again.")
    elif ready:
        print("  All tasks ready — run step3 next.")


def _upload_to_r2(file_path: str) -> Optional[str]:
    """Publish a local file through the configured uploader and return its URL, or None on failure."""
    try:
        from uploader_factory import get_uploader
        uploader = get_uploader()
        published_url = uploader.upload_local_file(file_path, prefix="generate")
        return published_url
    except Exception as e:
        print(f"  [WARN] upload failed: {e}")
        return None


def run_step3(args):
    """
    Step 3: Load state file, download each file_url to its output path,
    then upload to R2 for a permanent CDN URL.
    """
    state = _load_state(args.state_file)
    tasks = state["tasks"]

    ready_tasks = [t for t in tasks if t.get("status") == "ready" and t.get("file_url")]
    if not ready_tasks:
        print("[STEP 3] No ready tasks to download.")
        return

    print(f"[STEP 3] Downloading {len(ready_tasks)} image(s)...")
    for t in ready_tasks:
        file_url    = t["file_url"]
        output_path = t.get("output")
        if output_path:
            if _download_url_to_file(file_url, output_path):
                print(f"  Saved: {output_path}")
                t["status"] = "saved"
                r2_url = _upload_to_r2(output_path)
                t["image_url"] = r2_url if r2_url else file_url
            else:
                print(f"  Failed to save: {t['task_name']} — URL: {file_url}")
                t["status"] = "failed"
        else:
            print(f"  Image URL: {file_url}")
            t["status"] = "saved"
            t["image_url"] = file_url

    _save_state(args.state_file, state)
    saved = sum(1 for t in tasks if t["status"] == "saved")
    print(f"[STEP 3 DONE] {saved}/{len(tasks)} image(s) saved.")

    # 输出可解析的图片 URL 标记，供 AI 展示给用户
    for t in tasks:
        if t.get("status") == "saved" and t.get("image_url"):
            print(f"[IMAGE_URL] {t['task_name']}: {t['image_url']}")
    url_map = {t["task_name"]: t["image_url"] for t in tasks
               if t.get("status") == "saved" and t.get("image_url")}
    if url_map:
        print(f"[STEP3_IMAGE_URLS] {json.dumps(url_map, ensure_ascii=False)}")


# ---------------------------------------------------------------------------
# All-in-one mode (step1 + step2 loop + step3 in one call)
# ---------------------------------------------------------------------------

def _run_batch(tasks: list, outputs: list) -> list:
    """
    Execute the full 3-step pipeline in one call (for --mode all).

    Args:
        tasks:   List of task dicts (task_name, img_urls, prompt, ratio, resolution)
        outputs: List of local output paths (or None) aligned with tasks

    Returns:
        List of result paths (local files) or URLs, None for failures.
    """
    submitted = batch_step1_submit_tasks(tasks)

    task_infos = [
        {"task_name": r["task_name"], "task_id": r["task_id"]}
        for r in submitted
    ]
    polled = batch_step2_poll_tasks(task_infos)

    while any(r["status"] == "pending" for r in polled):
        pending_infos = [
            {"task_name": r["task_name"], "task_id": r["task_id"]}
            for r in polled if r["status"] == "pending"
        ]
        re_polled = batch_step2_poll_tasks(pending_infos)
        pending_map = {r["task_name"]: r for r in re_polled}
        for i, r in enumerate(polled):
            if r["status"] == "pending" and r["task_name"] in pending_map:
                polled[i] = pending_map[r["task_name"]]

    results = []
    for poll_result, output_path in zip(polled, outputs):
        file_url = poll_result.get("file_url")
        if poll_result["status"] == "ready" and file_url:
            if output_path:
                if _download_url_to_file(file_url, output_path):
                    print(f"  Saved: {output_path}")
                    results.append(output_path)
                else:
                    print(f"  Warning: local save failed, returning URL: {file_url}")
                    results.append(file_url)
            else:
                print(f"  Image URL: {file_url}")
                results.append(file_url)
        else:
            print(f"  Error: generation failed for {poll_result['task_name']}")
            results.append(None)

    return results


# ---------------------------------------------------------------------------
# Generation entry points (--mode all)
# ---------------------------------------------------------------------------

def generate(args):
    """Generate a single shot (wraps _run_batch for unified code path)."""
    prompt = _build_prompt(args)
    refs = _collect_refs(args)
    ratio = args.ratio or "3:4"
    resolution = args.resolution or "2K"

    label = f"{args.designer} / {args.shot}"
    if args.piece_name:
        label += f" / {args.piece_name}"

    provider = args.provider or os.environ.get("ICON_DESIGNER_PROVIDER", "mock")
    print(f"Generating {label} (provider={provider})...")
    task = {
        "task_name": label,
        "img_urls": refs if refs else None,
        "prompt": prompt,
        "ratio": ratio,
        "resolution": resolution,
        "provider": provider,
    }

    results = _run_batch([task], [args.output])
    return results[0] if results else None


def generate_parallel(args):
    """Generate multiple shots in parallel using the batch pipeline."""
    refs = _collect_refs(args)
    ratio = args.ratio or "3:4"
    resolution = args.resolution or "2K"
    outputs = args.outputs or [None] * len(args.shots)
    provider = args.provider or os.environ.get("ICON_DESIGNER_PROVIDER", "mock")

    tasks = []
    for shot in args.shots:
        shot_args = argparse.Namespace(**vars(args))
        shot_args.shot = shot
        prompt = _build_prompt(shot_args)
        label = f"{args.designer} / {shot}"
        if args.piece_name:
            label += f" / {args.piece_name}"
        tasks.append({
            "task_name": label,
            "img_urls": refs if refs else None,
            "prompt": prompt,
            "ratio": ratio,
            "resolution": resolution,
            "provider": provider,
        })

    print(f"Generating {len(tasks)} shots in parallel: {', '.join(args.shots)}...")
    return _run_batch(tasks, outputs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Icon Designer — Asset Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution modes:
  --mode all     (default) Submit + poll + download in one call. Simple but may hit 60s sandbox timeout.
  --mode step1   Submit task(s), save task_ids to --state_file.          (< 30s)
  --mode step2   Poll task(s) from --state_file, update file_urls.       (< 50s, re-run if PENDING)
  --mode step3   Download images listed in --state_file to output paths. (< 30s)

Step1 requires: --designer, --shot or --shots, garment params, --state_file
Step2 requires: --state_file only
Step3 requires: --state_file only
""")

    # Execution mode
    parser.add_argument("--mode", default="all",
                        choices=["all", "step1", "step2", "step3"],
                        help="all (default) | step1 | step2 | step3")
    parser.add_argument("--state_file", default=None,
                        help="JSON state file path — required for step1 (write) and step2/step3 (read)")

    # Designer — required for step1/all, optional for step2/step3
    parser.add_argument("--designer", default=None,
                        help="Icon designer: Coco Chanel, Alexander McQueen, Giorgio Armani, "
                             "Valentino Garavani, Christian Dior, Yves Saint Laurent")

    # Single-shot mode (backward compatible)
    parser.add_argument("--shot", default="front", choices=["front", "side", "back"],
                        help="Shot angle for single-shot mode: front, side, or back")
    parser.add_argument("--output", default=None,
                        help="Output file path (single-shot / step1 single-shot)")

    # Multi-shot parallel mode
    parser.add_argument("--shots", nargs="+", choices=["front", "side", "back"],
                        help="Multiple shot angles to generate in parallel (e.g. --shots side back)")
    parser.add_argument("--outputs", nargs="+", default=None,
                        help="Output file paths for each shot in --shots (must match order)")

    # Garment brief
    parser.add_argument("--piece_name", default="", help="Piece name")
    parser.add_argument("--category", default="", help="Garment category")
    parser.add_argument("--silhouette", default="", help="Silhouette description")
    parser.add_argument("--materials", default="", help="Materials and fabrics")
    parser.add_argument("--palette", default="", help="Color palette")
    parser.add_argument("--construction", default="", help="Construction details")
    parser.add_argument("--signatures", default="", help="Signature design elements")
    parser.add_argument("--styling", default="", help="Styling direction")
    parser.add_argument("--gender", default="", help="Womenswear/Menswear/Unisex")

    # Reference imagery
    parser.add_argument("--reference", nargs="*", default=[], help="Reference image(s) for product fidelity")
    parser.add_argument("--face_lock", default=None, help="Face-lock anchor for model consistency")
    parser.add_argument("--ratio", default="3:4", help="Output ratio (default: 3:4)")
    parser.add_argument("--resolution", default="2K", help="Output resolution")

    # Provider
    parser.add_argument("--provider", default=os.environ.get("ICON_DESIGNER_PROVIDER", "mock"),
                        choices=["mock", "tencent", "dmxapi", "auto"],
                        help="Image generation provider: mock (default) | tencent | dmxapi | auto")

    args = parser.parse_args()

    if args.mode == "step1":
        if not args.designer:
            parser.error("--designer is required for --mode step1")
        if not args.state_file:
            parser.error("--state_file is required for --mode step1")
        run_step1(args)

    elif args.mode == "step2":
        if not args.state_file:
            parser.error("--state_file is required for --mode step2")
        run_step2(args)

    elif args.mode == "step3":
        if not args.state_file:
            parser.error("--state_file is required for --mode step3")
        run_step3(args)

    else:  # --mode all (default)
        if not args.designer:
            parser.error("--designer is required")
        if args.shots:
            generate_parallel(args)
        else:
            generate(args)


if __name__ == "__main__":
    main()
