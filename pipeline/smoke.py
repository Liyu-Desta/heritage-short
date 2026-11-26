"""Smoke test: one cheap call to each hosted provider, logged to runs.jsonl.
Also lists the Gemini models your key can see, because model names change.

    python -m pipeline.smoke
"""
from __future__ import annotations

from pipeline import gemini
from pipeline.common import OUT, call_model, say, write_wav
from pipeline.keyframes import _cf_run, model as kf_model
from pipeline.narration import tts_model
from pipeline.script import text_model


def main() -> None:
    ok = True
    try:
        names = gemini.list_models()
        say("Gemini models with 'tts': " + ", ".join(n for n in names if "tts" in n))
        say("Gemini flash text models: " + ", ".join(n for n in names if "flash" in n and "tts" not in n)[:600])
    except Exception as e:
        ok = False
        say(f"FAIL gemini list: {e}")

    for name, fn in [
        ("gemini text", lambda: call_model(lambda: gemini.text(text_model(), "Reply with the single word: ready"),
                                           stage="smoke", provider="gemini", model=text_model(), params={})),
        ("gemini tts", lambda: call_model(lambda: gemini.tts(tts_model(), "Say warmly: Hello, and welcome to our story.", "Kore"),
                                          stage="smoke", provider="gemini", model=tts_model(), params={"voice": "Kore"})),
        ("cloudflare image", lambda: call_model(lambda: _cf_run(kf_model(), "a clay coffee pot on a wooden table, morning light",
                                                                 1, [], 512, 512),
                                                stage="smoke", provider="cloudflare", model=kf_model(), params={})),
    ]:
        try:
            out = fn()
            if name == "gemini tts":
                write_wav(OUT / "smoke" / "tts.wav", out[0], out[1])
                out = f"{len(out[0])} bytes of audio -> outputs/smoke/tts.wav"
            elif name == "cloudflare image":
                (OUT / "smoke").mkdir(parents=True, exist_ok=True)
                (OUT / "smoke" / "image.png").write_bytes(out)
                out = f"{len(out)} bytes -> outputs/smoke/image.png"
            say(f"OK   {name}: {str(out).strip()[:80]}")
        except Exception as e:
            ok = False
            say(f"FAIL {name}: {e}")
    say("Kaggle cannot be smoke-tested from here: run one job from kaggle/README.md.")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
