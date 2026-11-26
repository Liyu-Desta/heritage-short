# Architecture

## One contract, independent stages
`storyboard.json` is the only thing stages share, apart from files in `outputs/`. Each stage reads it,
works out which outputs the current storyboard needs, and creates only the missing ones. No stage calls
another stage's internals except to ask where an output should be (`keyframe_spec`, `narration_path`,
`clip_path`), so the path rule exists in exactly one place.

| Stage | Module | Reads | Writes | Runs on |
|---|---|---|---|---|
| validate | `pipeline/validate.py` | storyboard + schema | (exit code) | local |
| script | `pipeline/script.py` | story notes | `storyboard.draft.json`, `translation_en` | Gemini API |
| narration | `pipeline/narration.py` | `narration.text`, `voice` | `outputs/narration/<shot>.<key>.wav` | Gemini TTS |
| keyframes | `pipeline/keyframes.py` | `style`, `characters`, `image_prompt`, `seed` | `outputs/refs/<char>.<key>.png`, `outputs/keyframes/<shot>.<key>.png` | Cloudflare Workers AI |
| shots | `pipeline/shots.py` + `kaggle/wan22_i2v.py` | keyframe file, `motion_prompt`, `seed`, WAN_* | `outputs/shots/<shot>.<key>.mp4` | Kaggle T4 ×2 |
| music | `pipeline/music.py` + `kaggle/acestep_music.py` | `music` | `outputs/music/candidates/c*.wav`, `score.wav` | Kaggle / local placeholder |
| assemble | `pipeline/assemble.py` | everything above | `outputs/final/*_16x9.mp4`, `*_9x16.mp4`, `*.en.srt` | local FFmpeg |

## Validation
`schema/storyboard.schema.json` (JSON Schema 2020-12) enforces types, 8–12 shots, id formats, a required
`purpose` for every shot, consent references for real people, and an end-card line containing "AI".
`validate.py` adds checks a schema cannot express: unique ids, known character references, a 60–90 s total,
an English subtitle for every narrated line, and, once audio exists, **narration fit** (a line that overruns
its shot is flagged). Every entry point validates first and refuses to run on an invalid storyboard.

## Caching
Every output is named `<shot>.<key>.<ext>`, where `key` is a 12-character SHA-256 of exactly the inputs
that affect that output:

- narration: text, voice, style prompt, TTS model
- keyframe: style, the shot's character descriptions, image prompt, seed, model, steps (+ reference-sheet hashes for FLUX.2)
- clip: **file hash of the keyframe**, motion prompt, seed, Wan settings

Keys chain: a new keyframe changes the clip key, so a shot never shows motion from an old frame. A narration
edit touches nothing visual. Old renders stay on disk, which makes A/B comparison in experiments easy.
Assembly is cheap and not cached: it re-edits from scratch every time.

## Remote GPU round trip
Kaggle cannot be called like an API, so the shots and music stages split around a manifest.
`prepare` writes `jobs.json` (only the jobs whose key file is missing) and zips it with their keyframes.
The Kaggle worker renders those jobs (one process per T4) and logs each one in runs.jsonl format.
`import` copies the clips back and merges the GPU log lines into `runs.jsonl`, de-duplicated by `job_id`.
The worker names its outputs with the key computed locally, so the cache stays consistent across machines.

## Failure handling
- `common.call_model` wraps every hosted call: exponential backoff on 429/5xx/timeouts (honouring
  `Retry-After`), immediate failure on 4xx, and a `runs.jsonl` line for **every attempt**, including failures.
- The Kaggle worker catches per-shot exceptions, logs them, frees GPU memory, and moves on, so one bad prompt
  cannot burn the session.
- Graceful degradation in assembly: Wan clip → pan-and-zoom of the keyframe (camera move from `camera`) → black
  frame. Missing narration still shows its subtitle. No selected score → placeholder drone.
- `--offline` re-edits without any network access, for when a quota runs out at the worst moment.

## Assembly details
- Clips are scaled and cropped to 1280×720, slowed by up to 1.6× to fill the shot, then the last frame is held.
- Voice lines are placed at shot start + `narration_offset_s`. The score is looped, trimmed and faded, then ducked
  under the voice with `sidechaincompress`. The mix is normalised with `loudnorm` to `loudness_lufs` (−14 by
  default, the common target for social platforms). Verified at −14.0 LUFS integrated with `ebur128`.
- Subtitles are timed to the actual length of each narration file, long lines are split at punctuation,
  and they are burned in from an ASS file in pixel coordinates (sidecar `.srt` exported too).
- 9:16 places the 16:9 picture on a blurred, darkened copy of itself, with subtitles just below the picture.
- The end card is rendered per aspect ratio by Pillow. File metadata carries a "Made with AI" comment.

## Logging
`runs.jsonl` holds one JSON object per model call attempt:
`ts, stage, shot, provider, model, params, seed, latency_s, status, attempt, output, error, cost_usd, list_price_usd`
(+ `gpu_s`, `gpu`, `job_id` for Kaggle jobs). API keys travel in headers and are never logged.
`pipeline/report.py` aggregates it for COSTS.md.
