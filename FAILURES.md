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
