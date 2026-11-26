"""Stage: keyframes. First a reference sheet per character, then one 16:9
keyframe per shot, on Cloudflare Workers AI.

Consistency strategy (see EXPERIMENTS.md):
  * every shot prompt = style + the character's locked description + shot prompt
  * fixed per-shot seeds
  * with a FLUX.2 model, the character reference sheet is also passed as an
    input image (multipart); FLUX.1 schnell is text-only.

Cache key = style + character descriptions (+ reference-sheet hash for FLUX.2)
+ image prompt + seed + model + steps. Changing narration never re-renders a frame.

    python -m pipeline.keyframes [--shot s03] [--refs-only]
"""
from __future__ import annotations

import argparse
import base64
import io

from PIL import Image

from pipeline.common import (OUT, ModelError, cached, call_model, characters_for, env, file_hash, http, key,
                             load_storyboard, say, select_shots)

REF_DIR, KF_DIR = OUT / "refs", OUT / "keyframes"
W, H = 1920, 1080  # native full-HD keyframes: no upscaling before the edit (EXPERIMENTS.md)


def model() -> str:
    return env("KEYFRAME_MODEL", "@cf/black-forest-labs/flux-2-klein-9b")


def is_flux2(m: str) -> bool:
    return "flux-2" in m


def steps(m: str) -> int:
    return int(env("KEYFRAME_STEPS", "8" if not is_flux2(m) else "20"))


def _cf_run(m: str, prompt: str, seed: int, refs: list[bytes], width: int, height: int) -> bytes:
    acct = env("CLOUDFLARE_ACCOUNT_ID", required=True)
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{m}"
    headers = {"Authorization": f"Bearer {env('CLOUDFLARE_API_TOKEN', required=True)}"}
    if is_flux2(m):  # FLUX.2 on Workers AI takes multipart form data with optional input images
        fields = {"prompt": (None, prompt[:2048]), "seed": (None, str(seed)), "steps": (None, str(steps(m))),
                  "width": (None, str(width)), "height": (None, str(height))}
        for i, img in enumerate(refs[:4]):
            fields[f"input_image_{i}"] = (f"ref{i}.png", img, "image/png")
        r = http("POST", url, headers=headers, files=fields)
    else:
        r = http("POST", url, headers=headers, json={"prompt": prompt[:2048], "steps": steps(m)})  # schnell no longer accepts seed (FAILURES.md F5)
    if r.headers.get("content-type", "").startswith("image/"):
        return r.content
    data = r.json()
    img = (data.get("result") or {}).get("image")
    if not img:
        raise ModelError(f"no image in response: {str(data)[:300]}")
    return base64.b64decode(img)


def _to_frame(raw: bytes, w: int, h: int) -> Image.Image:
    """Centre-crop to the target aspect and resize."""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    target = w / h
    if im.width / im.height > target:
        nw = round(im.height * target)
        im = im.crop(((im.width - nw) // 2, 0, (im.width + nw) // 2, im.height))
    else:
        nh = round(im.width / target)
        im = im.crop((0, (im.height - nh) // 2, im.width, (im.height + nh) // 2))
    return im.resize((w, h), Image.LANCZOS)


def ref_spec(sb: dict, c: dict):
    m = model()
    # Plain background on purpose: FLUX.2 copies whatever is in a reference image, so a sheet drawn inside a
    # scene leaked its alley into indoor shots (EXPERIMENTS.md E2).
    prompt = (f"Character reference sheet on a plain flat white background, no scenery, no buildings, no ground, "
              f"front view and full-body view, same face and clothing in every view: {c['description']}. "
              f"Rendering style only (ignore any place it mentions): {sb['style']['description']}")
    seed = 1000 + sum(map(ord, c["id"]))
    return prompt, seed, cached(REF_DIR, c["id"], key(prompt, seed, m, steps(m)), "png")


def keyframe_spec(sb: dict, s: dict):
    """(prompt, reference paths, expected output path) for a shot. Used by
    shots.py/assemble.py to locate the keyframe that matches the storyboard."""
    m = model()
    chars = characters_for(sb, s)
    char_text = " ".join(f"{c['name']}: {c['description']}" for c in chars)
    ref_paths = [ref_spec(sb, c)[2] for c in chars] if is_flux2(m) else []
    if ref_paths:  # scene first so it wins; references constrain appearance only (EXPERIMENTS.md E2)
        prompt = (f"Scene: {s['image_prompt']}. Style: {sb['style']['description']}. "
                  f"Characters, appearance only, taken from the reference images (do not copy their background or pose; "
                  f"each character appears exactly once): {char_text}. No text, signs or writing anywhere.")
    else:
        prompt = f"{sb['style']['description']}. {s['image_prompt']}. {char_text}. No text, signs or writing anywhere."
    ref_hashes = [file_hash(p) if p.exists() else "missing" for p in ref_paths] if ref_paths else None
    k = key(prompt, s["seed"], m, steps(m), ref_hashes)
    return prompt, ref_paths, cached(KF_DIR, s["id"], k, "png")


def reference_sheets(sb: dict) -> None:
    m = model()
    for c in sb["characters"]:
        prompt, seed, path = ref_spec(sb, c)
        if path.exists():
            say(f"  ref {c['id']}: cached {path.name}")
        else:
            raw = call_model(lambda: _cf_run(m, prompt, seed, [], 1024, 1024), stage="keyframes", provider="cloudflare",
                             model=m, shot=f"ref:{c['id']}", seed=seed, output=path.name,
                             params={"steps": steps(m), "kind": "reference_sheet"})
            Image.open(io.BytesIO(raw)).convert("RGB").save(path)
            say(f"  ref {c['id']}: new {path.name}")


def run(sb: dict, only: list[str] | None = None, refs_only: bool = False) -> None:
    m = model()
    say(f"[keyframes] model={m} steps={steps(m)}")
    reference_sheets(sb)
    if refs_only:
        return
    for s in select_shots(sb, only):
        prompt, ref_paths, path = keyframe_spec(sb, s)
        if path.exists():
            say(f"  {s['id']}: cached {path.name}")
            continue
        ref_bytes = [open(p, "rb").read() for p in ref_paths]
        raw = call_model(lambda: _cf_run(m, prompt, s["seed"], ref_bytes, 1920, 1088), stage="keyframes",
                         provider="cloudflare", model=m, shot=s["id"], seed=s["seed"], output=path.name,
                         params={"steps": steps(m), "refs": len(ref_bytes), "prompt_chars": len(prompt)})
        _to_frame(raw, W, H).save(path)
        say(f"  {s['id']}: new {path.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", action="append")
    ap.add_argument("--refs-only", action="store_true")
    a = ap.parse_args()
    run(load_storyboard(), a.shot, a.refs_only)
