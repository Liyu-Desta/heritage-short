# Heritage Short: a storyboard-to-film pipeline

This repository turns one file, [`storyboard.json`](storyboard.json), into a narrated, scored and
subtitled 60–90 second short film in 9:16 and 16:9. Each stage is a script that reads the storyboard and
writes into `outputs/`. Outputs are cached by a hash of their inputs, so editing one shot regenerates only that shot.

```
storyboard.json ──validate──► narration (Gemini TTS) ───────────────┐
                 ├──────────► keyframes (FLUX on Cloudflare) ──► shots (Wan 2.2 on Kaggle) ──► assemble (FFmpeg) ──► outputs/final/*.mp4
                 └──────────► music (ACE-Step on Kaggle) ───────────┘
```

## Run it

```bash
git clone <this repo> && cd heritage-short
python -m pip install -r requirements.txt     # ffmpeg comes bundled via imageio-ffmpeg
cp .env.example .env                          # add your Gemini key and Cloudflare account/token
python -m pipeline.smoke                      # one call per provider, logged to runs.jsonl
python film.py                                # the whole pipeline (or: make film)
```

`python film.py` validates the storyboard, then voices every line, draws every keyframe, queues the
shots that need video for the GPU, resolves the score, and edits both aspect ratios into
`outputs/final/`. Shots without a Wan clip yet are animated with a pan-and-zoom of their keyframe,
so the command always finishes with a watchable film.

| Command | What it does |
|---|---|
| `python film.py --radio` | Radio cut: narration + music + subtitles on black (the phase 1 user test) |
| `python film.py --shot s03` | Regenerate only what changed in shot s03, then re-edit |
| `python film.py --offline` | No model calls; re-edit from whatever is already in `outputs/` |
| `python film.py --stages narration,assemble` | Run chosen stages only |
| `python -m pipeline.validate` | Schema and semantic checks (length, ids, narration fit) |
| `python -m pipeline.script draft story/notes.md` | Draft a storyboard from story notes with Gemini |
| `python -m pipeline.script translate` | Fill missing English subtitles |
| `python -m pipeline.shots prepare / import clips.zip / status` | Round trip to the Kaggle GPU; see [kaggle/README.md](kaggle/README.md) |
| `python -m pipeline.music prepare / import music.zip` | Same for the ACE-Step score |
| `python -m pipeline.report --write` | Summarise `runs.jsonl` into the table in COSTS.md |

The GPU stages (Wan 2.2, ACE-Step) run in a Kaggle notebook because they need a GPU. A clean clone with no
GPU still produces the complete film from the cached clips committed in `outputs/shots/`.

## What it costs
On free tiers it costs $0. The real limits are daily image allowance, TTS rate limits and Kaggle GPU hours.
Measured latency, GPU minutes and list-price equivalents are in [COSTS.md](COSTS.md).

## The repository
| Path | Purpose |
|---|---|
| `storyboard.json` | The contract: shots, durations, prompts, characters, narration, music, end card |
| `schema/storyboard.schema.json` | JSON Schema, checked before every run |
| `pipeline/` | One module per stage, plus `common.py` (cache, retries, logging, ffmpeg) |
| `kaggle/` | GPU workers for Wan 2.2 and ACE-Step |
| `runs.jsonl` | One line per model call: stage, shot, model, params, seed, latency, status, cost |
| `outputs/` | Reference sheets, keyframes, clips, narration, music, final films |
| [DESIGN.md](DESIGN.md) | Audience, intent, both user tests and what they changed |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stages, contracts, caching, failure handling |
| [EXPERIMENTS.md](EXPERIMENTS.md) | Hypothesis → change → result |
| [FAILURES.md](FAILURES.md) | What broke, what was tried, what fixed it |
| [COSTS.md](COSTS.md) | Measured latency, GPU minutes, list-price equivalent |
| [ETHICS.md](ETHICS.md) | Consent, licences, labelling, data handling |
