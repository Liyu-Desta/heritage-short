"""Stage: script. Drafts a storyboard from your story notes, and translates
narration into English subtitles. Both outputs are validated before saving.

    python -m pipeline.script draft story/notes.md          # -> storyboard.draft.json
    python -m pipeline.script translate                      # fills empty translation_en

Privacy: free Gemini tiers may use prompts for training. Keep private family
details (addresses, phone numbers, health) out of your notes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import gemini
from pipeline.common import ROOT, SCHEMA, STORYBOARD, call_model, env, say
from pipeline.validate import check


def text_model() -> str:
    return env("GEMINI_TEXT_MODEL", "gemini-flash-lite-latest")


DRAFT_PROMPT = """You are a documentary story editor. Turn the story notes below into a storyboard
for a 60-90 second vertical/horizontal short film narrated in language code "{lang}".

Rules:
- 8 to 12 shots; shot durations + end card duration must total 60-90 seconds.
- Narration lines are short and spoken (about 2 words per second of shot, max).
- Every shot has a one-sentence "purpose": why it is in the film.
- Image prompts describe one frame concretely (subject, setting, light, lens). Never name a living artist.
- Motion prompts describe what moves in ~5 seconds (people, cloth, smoke, light, camera).
- Characters get one locked, detailed appearance description reused across shots.
- End card lines must include one that says the film was made with AI.
- Output ONLY JSON valid against this JSON Schema:
{schema}

Audience: {audience}
Intent: {intent}

Story notes:
{notes}
"""


def draft(notes_path: Path, lang: str, audience: str, intent: str, out: Path) -> None:
    model = text_model()
    schema = SCHEMA.read_text(encoding="utf-8")
    prompt = DRAFT_PROMPT.format(lang=lang, schema=schema, audience=audience, intent=intent,
                                 notes=notes_path.read_text(encoding="utf-8"))
    raw = call_model(lambda: gemini.text(model, prompt, json_mode=True), stage="script", provider="gemini",
                     model=model, params={"task": "draft", "notes_chars": len(prompt)})
    sb = json.loads(raw)
    errors, _ = check(sb)
    out.write_text(json.dumps(sb, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"wrote {out} ({len(sb.get('shots', []))} shots)")
    for e in errors:
        say(f"  needs fixing: {e}")
    say("Review it by hand, then copy it over storyboard.json.")


def translate(path: Path) -> None:
    model = text_model()
    sb = json.loads(path.read_text(encoding="utf-8"))
    todo = [s for s in sb["shots"] if s["narration"]["text"].strip() and not s["narration"]["translation_en"].strip()]
    if not todo:
        say("nothing to translate")
        return
    lines = {s["id"]: s["narration"]["text"] for s in todo}
    prompt = (f"Translate these narration lines from language '{sb['language']}' into natural, concise English "
              f"subtitles. Keep proverbs meaningful rather than literal. Return JSON object id->English.\n\n"
              + json.dumps(lines, ensure_ascii=False, indent=1))
    raw = call_model(lambda: gemini.text(model, prompt, json_mode=True, temperature=0.2), stage="script",
                     provider="gemini", model=model, params={"task": "translate", "lines": len(lines)})
    result = json.loads(raw)
    for s in todo:
        s["narration"]["translation_en"] = result.get(s["id"], "")
        say(f"  {s['id']}: {s['narration']['translation_en']}")
    path.write_text(json.dumps(sb, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say("Check the translations with a fluent speaker before release.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("notes", type=Path)
    d.add_argument("--lang", default="am")
    d.add_argument("--audience", default="My family and their friends, watching on phones via WhatsApp and TikTok.")
    d.add_argument("--intent", default="They should feel proud and want to ask their elders for more stories.")
    d.add_argument("--out", type=Path, default=ROOT / "storyboard.draft.json")
    t = sub.add_parser("translate")
    t.add_argument("--file", type=Path, default=STORYBOARD)
    a = ap.parse_args()
    if a.cmd == "draft":
        draft(a.notes, a.lang, a.audience, a.intent, a.out)
    else:
        translate(a.file)
