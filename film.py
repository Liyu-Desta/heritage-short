"""One command for the whole pipeline.

    python film.py                     # validate -> narration -> keyframes -> shots -> music -> assemble
    python film.py --radio             # radio cut: validate -> narration -> music -> assemble --radio
    python film.py --shot s03          # regenerate only what changed for shot s03, then re-edit
    python film.py --stages narration,assemble
    python film.py --offline           # skip every model call; edit with whatever is in outputs/

Every stage is cached by a hash of its inputs, so a re-run only calls models for
what changed. Each model call is logged to runs.jsonl.
"""
from __future__ import annotations

import argparse
import sys
import time

from pipeline import assemble, keyframes, music, narration, shots
from pipeline.common import RUNS, load_storyboard, say

ALL = ["narration", "keyframes", "shots", "music", "assemble"]
MODEL_STAGES = {"narration", "keyframes"}


def count_calls() -> int:
    return sum(1 for _ in open(RUNS, encoding="utf-8")) if RUNS.exists() else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stages", help=f"comma list from {ALL}")
    ap.add_argument("--shot", action="append", help="limit generation stages to these shot ids")
    ap.add_argument("--radio", action="store_true", help="narration + music on black (phase 1 checkpoint)")
    ap.add_argument("--offline", action="store_true", help="no model calls; assemble from existing outputs")
    a = ap.parse_args()

    sb = load_storyboard()  # validates; exits on error
    say(f"storyboard OK: {sb['title']!r}, {len(sb['shots'])} shots, language={sb['language']}")
    stages = a.stages.split(",") if a.stages else (["narration", "music", "assemble"] if a.radio else ALL)
    if a.offline:
        stages = [s for s in stages if s not in MODEL_STAGES]
    unknown = set(stages) - set(ALL)
    if unknown:
        sys.exit(f"unknown stage(s): {unknown}")

    before, t0 = count_calls(), time.perf_counter()
    for st in stages:
        if st == "narration":
            narration.run(sb, a.shot)
        elif st == "keyframes":
            keyframes.run(sb, a.shot)
        elif st == "shots":
            shots.run(sb, a.shot)
        elif st == "music":
            music.run(sb)
        elif st == "assemble":
            assemble.run(sb, radio=a.radio)
    say(f"done in {time.perf_counter() - t0:.0f}s; {count_calls() - before} new line(s) in runs.jsonl")


if __name__ == "__main__":
    main()
