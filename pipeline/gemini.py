"""Minimal Gemini REST client (no SDK, so the dependency list stays small).
The key travels in a header, never in the URL, so it cannot leak into logs."""
from __future__ import annotations

import base64
import json
import re

from pipeline.common import ModelError, env, http

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _headers() -> dict:
    return {"x-goog-api-key": env("GEMINI_API_KEY", required=True), "Content-Type": "application/json"}


def generate(model: str, body: dict) -> dict:
    r = http("POST", f"{BASE}/models/{model}:generateContent", headers=_headers(), data=json.dumps(body))
    data = r.json()
    if not data.get("candidates"):
        raise ModelError(f"no candidates (blocked?): {json.dumps(data)[:400]}")
    return data


def text(model: str, prompt: str, json_mode: bool = False, temperature: float = 0.7) -> str:
    cfg = {"temperature": temperature}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    data = generate(model, {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg})
    parts = data["candidates"][0].get("content", {}).get("parts", [])
    out = "".join(p.get("text", "") for p in parts)
    if not out:
        raise ModelError(f"empty text response: {json.dumps(data)[:400]}")
    return out


def tts(model: str, prompt: str, voice: str) -> tuple[bytes, int]:
    """Returns (16-bit mono PCM, sample rate)."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    data = generate(model, body)
    for part in data["candidates"][0].get("content", {}).get("parts", []):
        inline = part.get("inlineData")
        if inline:
            m = re.search(r"rate=(\d+)", inline.get("mimeType", ""))
            return base64.b64decode(inline["data"]), int(m.group(1)) if m else 24000
    raise ModelError(f"no audio in TTS response: {json.dumps(data)[:400]}")


def list_models() -> list[str]:
    r = http("GET", f"{BASE}/models?pageSize=200", headers=_headers())
    return [m["name"].removeprefix("models/") for m in r.json().get("models", [])]
