"""Stage 0: validate storyboard.json against the schema plus rules JSON Schema
cannot express (unique ids, character references, total length, narration fit).

    python -m pipeline.validate [storyboard.json]
"""
from __future__ import annotations

import json
import sys

from jsonschema import Draft202012Validator

from pipeline.common import SCHEMA, STORYBOARD, media_duration

MIN_TOTAL, MAX_TOTAL = 60, 90


def check(sb: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(sb), key=lambda e: list(e.path)):
        where = "/".join(map(str, e.path)) or "(root)"
        errors.append(f"schema: {where}: {e.message}")
    if errors:
        return errors, warnings

    ids = [s["id"] for s in sb["shots"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate shot ids: {sorted(dupes)}")
    char_ids = {c["id"] for c in sb["characters"]}
    for s in sb["shots"]:
        for c in s.get("characters", []):
            if c not in char_ids:
                errors.append(f"{s['id']}: unknown character '{c}'")
        n = s["narration"]
        if n["text"].strip() and not n["translation_en"].strip():
            errors.append(f"{s['id']}: narration has no English subtitle (run: python -m pipeline.script translate)")

    total = sum(s["duration_s"] for s in sb["shots"]) + sb["end_card"]["duration_s"]
    if not MIN_TOTAL <= total <= MAX_TOTAL:
        errors.append(f"total length {total:.1f}s is outside {MIN_TOTAL}-{MAX_TOTAL}s (shots + end card)")

    # Narration fit: only checkable once narration has been generated.
    from pipeline.narration import narration_path

    offset = sb.get("render", {}).get("narration_offset_s", 0.4)
    for s in sb["shots"]:
        wav = narration_path(sb, s)
        if wav and wav.exists():
            d = media_duration(wav)
            if d + offset > s["duration_s"]:
                warnings.append(f"{s['id']}: narration {d:.1f}s + {offset}s offset overruns shot ({s['duration_s']}s); "
                                f"lengthen the shot or shorten the line")
    return errors, warnings


def validate_or_exit(sb: dict) -> None:
    errors, warnings = check(sb)
    for w in warnings:
        print(f"  warn: {w}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        raise SystemExit("storyboard.json is invalid; fix the errors above.")


def main(argv: list[str]) -> None:
    path = argv[0] if argv else STORYBOARD
    with open(path, encoding="utf-8") as f:
        sb = json.load(f)
    validate_or_exit(sb)
    total = sum(s["duration_s"] for s in sb["shots"]) + sb["end_card"]["duration_s"]
    print(f"OK  {path}: {len(sb['shots'])} shots, {total:.1f}s incl. end card, language={sb['language']}")


if __name__ == "__main__":
    main(sys.argv[1:])
