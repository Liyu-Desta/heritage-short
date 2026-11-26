"""Stage: music (ACE-Step 1.5 on a Kaggle/Colab GPU), plus a local placeholder.

    python -m pipeline.music prepare        # writes outputs/music/music_job.json for kaggle/acestep_music.py
    python -m pipeline.music import x.zip   # copies candidates c1..cN in, merges GPU logs
    python -m pipeline.music                # resolves outputs/music/score.wav:
                                            #   storyboard.music.selected -> that candidate
                                            #   otherwise                 -> placeholder drone (radio cut)
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from pipeline.common import OUT, RUNS, ffmpeg, key, load_storyboard, say

DIR = OUT / "music"
CAND = DIR / "candidates"
SCORE = DIR / "score.wav"


def total_duration(sb: dict) -> float:
    return sum(s["duration_s"] for s in sb["shots"]) + sb["end_card"]["duration_s"]


def music_key(sb: dict) -> str:
    m = sb["music"]
    return key(m["prompt"], m.get("lyrics", "[instrumental]"), m.get("bpm"), round(total_duration(sb)))


def prepare(sb: dict) -> None:
    m = sb["music"]
    job = {"key": music_key(sb), "prompt": m["prompt"], "lyrics": m.get("lyrics", "[instrumental]"),
           "bpm": m.get("bpm"), "duration_s": round(total_duration(sb)) + 2,
           "candidates": [{"id": f"c{i + 1}", "seed": 4200 + i} for i in range(m.get("candidates", 3))]}
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "music_job.json").write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    say(f"[music] wrote outputs/music/music_job.json ({len(job['candidates'])} candidates, {job['duration_s']}s)")


def import_candidates(src: Path) -> None:
    tmp = None
    if src.suffix == ".zip":
        tmp = DIR / "_import"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(src).extractall(tmp)
        src = tmp
    CAND.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in list(src.rglob("*.wav")) + list(src.rglob("*.mp3")) + list(src.rglob("*.flac")):
        shutil.copy2(f, CAND / f.name)
        n += 1
    seen = {json.loads(l).get("job_id") for l in RUNS.read_text(encoding="utf-8").splitlines() if l.strip()} \
        if RUNS.exists() else set()
    for log in src.rglob("music_runs.jsonl"):
        with open(RUNS, "a", encoding="utf-8") as out:
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line).get("job_id") not in seen:
                    out.write(line + "\n")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    say(f"imported {n} candidate(s) into outputs/music/candidates/. Listen, then set music.selected in storyboard.json.")


def placeholder(duration: float, out: Path) -> None:
    """A soft A-minor drone with slow tremolo: clearly temporary, never mistaken for the score."""
    expr = ("0.05*sin(2*PI*110*t)+0.035*sin(2*PI*164.81*t)+0.03*sin(2*PI*220*t)+0.02*sin(2*PI*261.63*t)")
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={duration}", "-af",
           f"tremolo=f=0.25:d=0.4,afade=t=in:d=2,afade=t=out:st={max(duration - 3, 0)}:d=3", "-ac", "2", out)


def run(sb: dict, only=None) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    sel = sb["music"].get("selected")
    marker = DIR / "score.source"
    want = f"{sel}:{music_key(sb)}" if sel else f"placeholder:{total_duration(sb)}"
    if SCORE.exists() and marker.exists() and marker.read_text() == want:
        say(f"[music] score cached ({want})")
        return SCORE
    if sel:
        # Match the candidate rendered from the *current* prompt (its key), not any file named c2.* (FAILURES.md F11).
        hits = sorted(CAND.glob(f"{sel}.{music_key(sb)}.*")) if CAND.exists() else []
        if not hits and CAND.exists():
            hits = sorted(CAND.glob(f"{sel}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if hits:
                say(f"  warn: no {sel} for the current music prompt; using the newest {hits[0].name}")
        if not hits:
            raise SystemExit(f"music.selected='{sel}' but no outputs/music/candidates/{sel}.* file. Run the import first.")
        if hits[0].suffix == ".wav":
            shutil.copy2(hits[0], SCORE)
        else:
            ffmpeg("-i", hits[0], "-ar", "48000", "-ac", "2", SCORE)
        say(f"[music] score = {hits[0].name}")
    else:
        prepare(sb)
        placeholder(total_duration(sb), SCORE)
        say("[music] no candidate selected -> placeholder drone (fine for the radio cut)")
    marker.write_text(want)
    return SCORE


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="resolve", choices=["resolve", "prepare", "import"])
    ap.add_argument("src", nargs="?", type=Path)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(load_storyboard())
    elif a.cmd == "import":
        import_candidates(a.src)
    else:
        run(load_storyboard())
