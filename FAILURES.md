# Failures

Format: **what broke → what I tried → what fixed it → what I learned**. When a tool from the brief had
moved or been replaced, record what replaced it here.

## F1: No ffmpeg or make on the Windows dev machine
- **Broke:** the assembly stage needs ffmpeg with libass, and the one-command run assumed `make`.
- **Tried:** installing ffmpeg system-wide would work here but breaks "clone and run" for strangers.
- **Fixed:** depend on `imageio-ffmpeg`, which ships a static ffmpeg build with `subtitles/ass`, `sidechaincompress`,
  `loudnorm` and `zoompan` (checked with `ffmpeg -filters`). `film.py` is the one command; the Makefile only wraps it.
- **Learned:** check a dependency's capabilities, not just whether it is present.

## F2: Narration mix failed with "Invalid file index 10"
- **Broke:** the audio filter graph referenced input `[10:a]` when there were only 10 inputs.
- **Cause:** input indices were computed from the length of the ffmpeg argument list, which holds two entries (`-i`, path) per input.
- **Fixed:** index = `len(inputs) // 2`. Found by an offline end-to-end test with synthetic narration files at the exact cache paths.
- **Learned:** test each degradation path (black, pan-and-zoom, clip, with and without audio), not just the empty one.

## F3: Vertical subtitles landed in the middle of the picture
- **Broke:** with SRT + `force_style`, `MarginV` did not map to frame pixels the way I assumed on a 1080×1920 frame.
- **Fixed:** generate an ASS file per aspect ratio with `PlayResX/PlayResY` equal to the frame size, so margins are pixels.
  Verified by extracting frames from both exports.

## F4: Every API call failed with CERTIFICATE_VERIFY_FAILED (2026-11-26)
- **Broke:** the first `python -m pipeline.smoke` failed on Gemini *and* Cloudflare with
  `SSL: CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate`, before any key was checked.
- **Tried:** `curl` to the same hosts worked (HTTP 404 from the API root), so the network was fine and the problem was Python.
  `certifi` was up to date. The environment had `SSLKEYLOGFILE=\.swMonFltProxy\...`: Avast's HTTPS scanning
  re-signs TLS traffic with its own root certificate. Windows trusts that root; Python's bundled `certifi` list does not.
- **Fixed:** added `truststore` (requirements.txt) and `truststore.inject_into_ssl()` at the top of `pipeline/common.py`,
  so Python verifies against the OS certificate store. Verification is not disabled (no `verify=False`).
- **Learned:** "works in curl, fails in Python" on Windows usually means a TLS-inspecting antivirus or proxy.
  A stranger cloning the repo behind a corporate proxy hits the same thing, so the fix belongs in the code, not my machine.

## F5: Provider drift on day one: model removed, model overloaded, parameter dropped
- **Broke (three ways):**
  1. `gemini-flash-latest` returned HTTP 503 "high demand" on all 4 attempts; `gemini-2.5-flash` returned 404
     "no longer available to new users"; `gemini-3.5-flash` timed out after 180 s.
  2. Cloudflare `flux-1-schnell` returned 400 `Additional or unevaluated properties '/seed' ... not allowed`: the
     model's input schema no longer accepts a seed.
  3. TTS returned 400 "Model tried to generate text" for the smoke-test prompt `ሰላም። Hello.`. A full sentence works.
- **Tried:** `python -m pipeline.smoke` lists the models the key can see. I tested candidates one by one:
  `gemini-flash-lite-latest` answered; `gemini-3.8-flash` was also 503. Both `gemini-2.5-flash-preview-tts` and
  `gemini-3.8-flash-tts` produced audio for a real narration line.
- **Fixed:** text model → `gemini-flash-lite-latest` (only used for drafting and translation, so lite is enough).
  Keyframes → FLUX.2 klein-9b, which accepts a seed and reference images (see E1). Schnell requests no longer send `seed`.
  The smoke test now sends a full sentence to TTS.
- **Learned:** the retry/backoff in `common.http` handled the 503s correctly, but retries cannot fix a model that is
  gone. Model ids belong in `.env`, not in code, and the smoke test should run before every session.

## F6: Cloudflare free image allowance ran out mid-run (2026-11-26)
- **Broke:** while re-rendering keyframes after E2, Workers AI returned HTTP 429 `you have used up your daily free
  allocation of 10,000 neurons` (code 4006). Two reference sheets and s01 were done; s02–s10 were not.
- **Cause:** full-HD FLUX.2 klein-9b costs far more neurons per image than 1024×576 schnell. Smoke tests, the model
  comparison (E1) and two full keyframe passes (12 + 3 images) used up the day's budget.
- **Tried:** Gemini image models (`gemini-3.1-flash-image`, `gemini-2.5-flash-image`) as a fallback: both 429, no free quota.
  Lyria for music: also 429 on the free tier.
- **Worked around:** `assemble` now falls back to the newest older keyframe for a shot when the current one is missing,
  and prints a warning naming it, so a preview can always be cut. The remaining keyframes render after the 00:00 UTC
  reset; the cache means only the 9 missing frames are requested.
- **Learned:** budget the image allowance per day: comparisons at low resolution, finals at full HD.
  `runs.jsonl` makes the spend visible.

## F7: ACE-Step would not install on Kaggle (Python 3.13)
- **Broke:** the Kaggle music kernel failed after 0.9 min: `No matching distribution found for spacy==3.8.4`.
  Kaggle's image is now Python 3.13; ACE-Step pins spacy 3.8.4 (Python <3.13), and ACE-Step 1.5's `pyproject.toml`
  also says `requires-python = ">=3.11,<3.13"`.
- **Tried:** reading both repos' requirements before guessing (pinning around one package would hit the next pin).
- **Fixed:** the kernel builds an isolated Python 3.12 env with `uv venv -p 3.12`, installs CUDA torch from the
  cu126 index, then ACE-Step into that env, and runs the worker with that interpreter.
- **Also:** `kaggle kernels push` once failed with `RemoteDisconnected`; `pipeline/kaggle_run.py` now retries
  transient Kaggle API errors with backoff.

## F8: Newer TTS model read the stage direction aloud
- **Broke:** after switching to `gemini-3.8-flash-tts` (E3), s01 (3 words) came back 13.0 s long and s02 17.3 s.
  The validator's overrun warning flagged it.
- **Diagnosis:** transcribing the wav in *any* language (not just Amharic) showed the model speaking
  "Read this Amharic line slowly and warmly…" for ~8–10 s before the line. My E3 round-trip prompt had asked only for
  an Amharic transcript, so the evaluator silently dropped the English and the comparison looked good.
- **Fixed:** back to `gemini-2.5-flash-preview-tts`, which treats the style prompt as direction. The old clips were still
  in the cache (the key includes the model), so the revert cost zero API calls. Deleted the bad clips.
- **Learned:** an automatic check is only as good as its question. Ask the evaluator for *everything* it hears.
  Duration is a cheap sanity check that caught what the ASR missed.

## F9: ACE-Step ran, but every candidate failed in 0 s (API drift)
- **Broke:** with the Python 3.12 env (F7), the kernel reported "complete" in 1.7 min, but `music_runs.jsonl` showed
  `TypeError: ACEStepPipeline.__call__() got an unexpected keyword argument 'min_guidance'` for c1–c3. The worker
  catches per-candidate errors so one bad seed cannot kill the job, which meant the run *looked* successful.
- **Also:** my status poller once reported `error` for a kernel that was only queued: it searched the CLI output for the
  word "error", and a transient network message contained it. It now parses only Kaggle's `status "..."` field.
- **Fixed:** read the current `pipeline_ace_step.py`: the argument is now `min_guidance_scale`, and `oss_steps` is a
  string or None. Pinned torch/torchaudio 2.7.1 (cu126), because ACE-Step saves with `torchaudio.save(..., backend=...)`,
  which newer torchaudio releases changed.
- **Learned:** "kernel complete" is not "job succeeded". Check the result count (the importer says how many candidates
  it imported) and the per-item status in the GPU log.

## F10: ACE-Step out of GPU memory on a T4
- **Broke:** with F9 fixed, c1 ran 56 s and died: `CUDA out of memory ... 14.55 GiB in use` (T4 = 15 GB). c2 and c3 then
  failed within seconds, because c1's memory was never freed.
- **Cause:** a T4 has no bfloat16, so the 3.5B model runs in float32 (twice the memory), with everything resident on
  the GPU, for an 87 s clip.
- **Fixed:** `cpu_offload=True` and `overlapped_decode=True` (both in ACE-Step's constructor), `gc.collect()` and
  `torch.cuda.empty_cache()` after each candidate. A `--no-offload` flag remains for bigger GPUs. Float16 was the
  alternative, but it risks NaN/silent audio, which is harder to detect than an OOM.

## F11: The film used the wrong music candidate
- **Broke:** after selecting round 2's c2 (E4), the log said `score = c2.c004dd0ca3b8.wav`: round 1's c2, the 3/10
  track that ends abruptly at 1:04. The marker file said `c2:cbe59d023da9`, so the cache believed it was correct.
- **Cause:** `music.run` resolved `selected` with `glob("c2.*")` and took the first match alphabetically, ignoring the
  prompt key. Harmless with one round of candidates; wrong as soon as two rounds sit side by side.
- **Fixed:** resolve `{selected}.{music_key}.*` (the candidate made from the current prompt); fall back to the newest
  file with a warning. Caught only because I read the stage's log line rather than trusting "done".
