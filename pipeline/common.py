"""Shared plumbing for every stage: storyboard loading, hashing/caching,
run logging, HTTP with retries, and ffmpeg helpers.

Design rules (see ARCHITECTURE.md):
  * storyboard.json is the only contract between stages.
  * Every output file is named <shot>.<key>.<ext>, where key is a hash of
    exactly the inputs that affect it. If the file exists, the stage skips it.
  * Every model call (success or failure, every retry) is one line in runs.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
RUNS = ROOT / "runs.jsonl"
SCHEMA = ROOT / "schema" / "storyboard.schema.json"
STORYBOARD = ROOT / "storyboard.json"
PRICES = ROOT / "pipeline" / "prices.json"

try:  # use the OS certificate store, so HTTPS works behind antivirus / corporate TLS inspection (FAILURES.md F4)
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

try:  # .env is optional; real environment variables win
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- env
def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return val


# -------------------------------------------------------------------- storyboard
def load_storyboard(path: Path | str | None = None, validate: bool = True) -> dict:
    path = Path(path or STORYBOARD)
    sb = json.loads(path.read_text(encoding="utf-8"))
    if validate:
        from pipeline.validate import validate_or_exit

        validate_or_exit(sb)
    return sb


def select_shots(sb: dict, only: list[str] | None) -> list[dict]:
    shots = sb["shots"]
    if not only:
        return shots
    picked = [s for s in shots if s["id"] in only]
    missing = set(only) - {s["id"] for s in picked}
    if missing:
        raise SystemExit(f"Unknown shot id(s): {', '.join(sorted(missing))}")
    return picked


def characters_for(sb: dict, shot: dict) -> list[dict]:
    by_id = {c["id"]: c for c in sb["characters"]}
    return [by_id[c] for c in shot.get("characters", [])]


# ---------------------------------------------------------------------- caching
def key(*parts) -> str:
    """Stable 12-char hash of arbitrary JSON-serialisable inputs."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def cached(directory: Path, name: str, k: str, ext: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.{k}.{ext}"


def latest(directory: Path, name: str, ext: str) -> Path | None:
    """Most recent output for `name`, whatever its key (used by downstream stages
    that should prefer the current key but can fall back to an older render)."""
    if not directory.exists():
        return None
    hits = sorted(directory.glob(f"{name}.*.{ext}"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


# ---------------------------------------------------------------------- logging
_prices: dict | None = None


def list_price(model: str) -> float | None:
    """List-price equivalent per call in USD, from pipeline/prices.json (None if unknown)."""
    global _prices
    if _prices is None:
        _prices = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else {}
    for pattern, entry in _prices.get("per_call_usd", {}).items():
        if pattern in model:
            return entry
    return None


def log_call(**fields) -> None:
    fields = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
    fields.setdefault("cost_usd", 0.0)  # free tier: what we actually paid
    if "model" in fields and "list_price_usd" not in fields:
        fields["list_price_usd"] = list_price(fields["model"])
    line = json.dumps(fields, ensure_ascii=False)
    for name in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "GEMINI_API_KEY", "KAGGLE_API_TOKEN"):
        val = os.environ.get(name)
        if val and len(val) >= 8:  # error messages can echo request URLs; never let an id or key reach the log
            line = line.replace(val, f"<{name}>")
    with open(RUNS, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def say(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------------- HTTP
class Retryable(Exception):
    """Transient failure: rate limit, quota window, 5xx, timeout."""

    def __init__(self, msg: str, wait: float | None = None):
        super().__init__(msg)
        self.wait = wait


class ModelError(Exception):
    """Permanent failure: bad request, auth, safety block, unparseable response."""


def http(method: str, url: str, *, timeout: float = 180, **kw):
    import requests

    try:
        r = requests.request(method, url, timeout=timeout, **kw)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise Retryable(f"network: {e}") from e
    if r.status_code == 429 or r.status_code >= 500:
        wait = r.headers.get("Retry-After")
        raise Retryable(f"HTTP {r.status_code}: {r.text[:300]}", float(wait) if wait and wait.isdigit() else None)
    if r.status_code >= 400:
        raise ModelError(f"HTTP {r.status_code}: {r.text[:500]}")
    return r


def call_model(fn, *, stage: str, provider: str, model: str, params: dict, shot: str | None = None,
               seed: int | None = None, retries: int = 4, base_delay: float = 8.0, output: str | None = None):
    """Run fn() with exponential backoff; log every attempt to runs.jsonl."""
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        try:
            result = fn()
        except Retryable as e:
            latency = round(time.perf_counter() - t0, 3)
            log_call(stage=stage, shot=shot, provider=provider, model=model, params=params, seed=seed,
                     latency_s=latency, status="retryable_error", attempt=attempt, error=str(e)[:500])
            if attempt == retries:
                raise ModelError(f"{model}: gave up after {retries} attempts: {e}") from e
            delay = e.wait or base_delay * 2 ** (attempt - 1)
            say(f"    ! {e} -- retry {attempt}/{retries - 1} in {delay:.0f}s")
            time.sleep(delay)
            continue
        except Exception as e:
            latency = round(time.perf_counter() - t0, 3)
            log_call(stage=stage, shot=shot, provider=provider, model=model, params=params, seed=seed,
                     latency_s=latency, status="error", attempt=attempt, error=str(e)[:500])
            raise
        latency = round(time.perf_counter() - t0, 3)
        log_call(stage=stage, shot=shot, provider=provider, model=model, params=params, seed=seed,
                 latency_s=latency, status="ok", attempt=attempt, output=output)
        return result


# ----------------------------------------------------------------------- ffmpeg
def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg not found: pip install imageio-ffmpeg, or install ffmpeg.")


def ffmpeg(*args: str, cwd: Path | None = None) -> None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.stderr.write(" ".join(cmd) + "\n" + p.stderr[-3000:] + "\n")
        raise SystemExit(f"ffmpeg failed ({p.returncode})")


def media_duration(path: Path) -> float:
    """Duration in seconds of any audio/video file, without ffprobe."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for line in p.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hh, mm, ss = line.split(",")[0].split()[1].split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    raise ValueError(f"cannot read duration of {path}")


def write_wav(path: Path, pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
