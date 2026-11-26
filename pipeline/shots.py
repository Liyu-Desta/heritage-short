"""Stage: moving shots (Wan 2.2 TI2V-5B image-to-video, run on a Kaggle GPU).

The GPU is remote, so this stage is split in two halves around a job manifest:

    python -m pipeline.shots prepare     # writes outputs/shots/kaggle_bundle.zip with only the
                                         # shots whose inputs changed (jobs.json + keyframes)
    ... upload the zip as a Kaggle dataset, run kaggle/wan22_i2v.py, download clips.zip ...
    python -m pipeline.shots import clips.zip   # copies clips in, merges GPU logs into runs.jsonl
    python -m pipeline.shots status      # which shots have a clip / will use the pan-and-zoom fallback

Clip cache key = keyframe file hash + motion prompt + seed + Wan settings. A new
keyframe or motion prompt invalidates the clip; a narration edit does not.
Shots without a clip are animated by assemble.py with a pan-and-zoom of the keyframe.
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from pipeline.common import OUT, RUNS, cached, env, file_hash, key, load_storyboard, say, select_shots
from pipeline.keyframes import keyframe_spec

DIR = OUT / "shots"
BUNDLE = DIR / "kaggle_bundle.zip"


def wan_settings() -> dict:
    """Draft at 480p first; switch WAN_SIZE to 1280*704 for finals."""
    return {
        "model": env("WAN_MODEL", "Wan-AI/Wan2.2-TI2V-5B-Diffusers"),
        "size": env("WAN_SIZE", "832*480"),
        "frames": int(env("WAN_FRAMES", "121")),  # 4k+1; 121 frames @24fps ~ 5s
        "steps": int(env("WAN_STEPS", "30")),
        "guidance": float(env("WAN_GUIDANCE", "5.0")),
    }


def clip_path(sb: dict, s: dict) -> Path | None:
    """Expected clip for the shot's current keyframe + motion, or None if no keyframe yet."""
    _, _, kf = keyframe_spec(sb, s)
    if not kf.exists():
        return None
    return cached(DIR, s["id"], key(file_hash(kf), s["motion_prompt"], s["seed"], wan_settings()), "mp4")


def prepare(sb: dict, only: list[str] | None = None) -> None:
    jobs, settings = [], wan_settings()
    say(f"[shots] {settings}")
    for s in select_shots(sb, only):
        _, _, kf = keyframe_spec(sb, s)
        clip = clip_path(sb, s)
        if clip is None:
            say(f"  {s['id']}: no keyframe yet, skipped")
        elif clip.exists():
            say(f"  {s['id']}: cached {clip.name}")
        else:
            jobs.append({"shot": s["id"], "keyframe": kf.name, "output": clip.name, "seed": s["seed"],
                         "prompt": f"{sb['style']['description']}. {s['motion_prompt']}",
                         "negative_prompt": sb["style"].get("negative", ""), **settings})
            say(f"  {s['id']}: queued -> {clip.name}")
    if not jobs:
        say("  nothing to send to the GPU")
        BUNDLE.unlink(missing_ok=True)
        return
    with zipfile.ZipFile(BUNDLE, "w") as z:
        z.writestr("jobs.json", json.dumps(jobs, indent=2, ensure_ascii=False))
        for j in jobs:
            z.write(OUT / "keyframes" / j["keyframe"], j["keyframe"])
    say(f"  {len(jobs)} job(s) -> {BUNDLE.relative_to(OUT.parent)}  (upload as a Kaggle dataset; see kaggle/README.md)")


def import_clips(src: Path) -> None:
    """Accepts the clips.zip downloaded from Kaggle, or a folder."""
    tmp = None
    if src.suffix == ".zip":
        tmp = DIR / "_import"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for mp4 in src.rglob("*.mp4"):
        shutil.copy2(mp4, DIR / mp4.name)
        n += 1
    seen = {json.loads(l).get("job_id") for l in RUNS.read_text(encoding="utf-8").splitlines() if l.strip()} \
        if RUNS.exists() else set()
    merged = 0
    for log in src.rglob("wan_runs.jsonl"):
        with open(RUNS, "a", encoding="utf-8") as out:
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line).get("job_id") not in seen:
                    out.write(line + "\n")
                    merged += 1
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    say(f"imported {n} clip(s), merged {merged} GPU log line(s) into runs.jsonl")


def status(sb: dict) -> None:
    for s in sb["shots"]:
        _, _, kf = keyframe_spec(sb, s)
        clip = clip_path(sb, s)
        if clip and clip.exists():
            st = f"clip     {clip.name}"
        elif kf.exists():
            st = "pan-zoom (keyframe only)"
        else:
            st = "black    (no keyframe)"
        say(f"  {s['id']}: {st}")


def run(sb: dict, only: list[str] | None = None) -> None:
    prepare(sb, only)
    status(sb)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--shot", action="append")
    i = sub.add_parser("import")
    i.add_argument("src", type=Path)
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(load_storyboard(), a.shot)
    elif a.cmd == "import":
        import_clips(a.src)
    else:
        status(load_storyboard())
