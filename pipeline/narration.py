"""Stage: narration. One Gemini TTS call per shot line, cached by
(text, voice, style prompt, model). Editing one line re-voices only that shot.

    python -m pipeline.narration [--shot s03]
"""
from __future__ import annotations

import argparse

from pipeline import gemini
from pipeline.common import OUT, cached, call_model, env, key, load_storyboard, media_duration, say, select_shots, write_wav

DIR = OUT / "narration"


def tts_model() -> str:
    return env("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")


def narration_path(sb: dict, s: dict):
    """Expected wav for this shot's current line, or None if the shot is silent."""
    if not s["narration"]["text"].strip():
        return None
    v = sb["voice"]
    k = key(s["narration"]["text"], v["tts_voice"], v.get("style_prompt", ""), tts_model())
    return cached(DIR, s["id"], k, "wav")


def run(sb: dict, only: list[str] | None = None) -> None:
    model, v = tts_model(), sb["voice"]
    style = v.get("style_prompt", "")
    say(f"[narration] model={model} voice={v['tts_voice']}")
    for s in select_shots(sb, only):
        text = s["narration"]["text"].strip()
        path = narration_path(sb, s)
        if path is None:
            say(f"  {s['id']}: (no narration)")
            continue
        if path.exists():
            say(f"  {s['id']}: cached {path.name}")
            continue
        prompt = f"{style}\n\n{text}" if style else text
        pcm, rate = call_model(lambda: gemini.tts(model, prompt, v["tts_voice"]), stage="narration",
                               provider="gemini", model=model, shot=s["id"], output=path.name,
                               params={"voice": v["tts_voice"], "language": sb["language"], "chars": len(text),
                                       "style_prompt": style[:120]})
        write_wav(path, pcm, rate)
        d = media_duration(path)
        flag = "  <-- overruns shot!" if d + sb.get("render", {}).get("narration_offset_s", 0.4) > s["duration_s"] else ""
        say(f"  {s['id']}: new {path.name} ({d:.1f}s for a {s['duration_s']}s shot){flag}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", action="append")
    a = ap.parse_args()
    run(load_storyboard(), a.shot)
