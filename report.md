# Report: *The Only TV on Our Street*

A storyboard-to-film pipeline that turns my own childhood story, told in two Amharic voice notes, into an
85-second AI short film with Amharic narration, English subtitles and an Ethiopian-sounding score, in 16:9 and 9:16.

> **Status (2026-11-26).** Pipeline end to end: working. Narration, score, subtitles and both exports: done.
> Corrected keyframes: 2 of 11 rendered, the rest blocked by the daily image quota (F6). Wan 2.2 motion clips: not yet run.
> User tests 1 and 2: **not yet done**; the sections below that depend on them are marked *pending*.
> Every claim here points to a file, a log line or a numbered entry (F = [FAILURES.md](FAILURES.md),
> E = [EXPERIMENTS.md](EXPERIMENTS.md)).

---

## 1. What the project does

One file, [`storyboard.json`](storyboard.json), describes the whole film: audience, intent, visual style, characters,
voice, music, and for each of the 10 shots its duration, purpose, image prompt, motion prompt, camera move, seed and
narration line. Each pipeline stage reads that file and produces only what is missing:

```
story/tenx1.ogg + tenx2.ogg ──(Gemini: transcribe + translate)──► story/transcript.json ──(me)──► storyboard.json
                                                                                                    │ validate
          ┌──────────────────────────────┬───────────────────────────────┬──────────────────────────┤
     narration                       keyframes                         music                         │
  Gemini TTS (Amharic)        FLUX.2 klein-9b, Cloudflare         ACE-Step on Kaggle T4              │
          │                             │ ──► shots: Wan 2.2 on Kaggle    │                            │
          └──────────────────────────────┴───────────────┬───────────────┘                            │
                                                 assemble (FFmpeg) ──► outputs/final/*_16x9.mp4, *_9x16.mp4, *.en.srt
```

**One command:** `python film.py`. Run it from a clean clone; see [README.md](README.md).
Re-running regenerates only what changed: every output is named `<shot>.<hash-of-its-inputs>.<ext>`.

## 2. The story, audience and intent

- **Story:** my own childhood in an Addis Ababa *sefer* (neighbourhood). We played with the neighbours' children all
  day; only one house had a TV, and we all gathered there to watch the drama *Gemena*, then talked about it on the way
  home. I look back with joy, not regret, and I learned that children need to play: children who never played find it hard
  to get along with people.
- **Audience:** Ethiopians aged 18–35, in Ethiopia and the diaspora, who grew up in a sefer, plus young parents raising
  children among screens. They watch on phones (TikTok, Telegram, Facebook), think in Amharic, and already know *Gemena*.
- **Intent:** *feel* the warmth of a shared childhood; *understand* that playing together teaches children to connect;
  *do*: send their children outside to play, or message a childhood friend.
- These were written in [DESIGN.md](DESIGN.md) and the storyboard's `audience` and `intent` fields **before** any image was generated.
  Every shot has a `purpose` field explaining why it exists (for example s06 is deliberately silent: "a silent beat:
  let the audience sit inside the feeling of watching").

## 3. How I got from voice notes to storyboard

1. I recorded the story as two Telegram voice notes (51 s + 10 s). They are kept out of git (`.gitignore`), because they hold a real voice.
2. The pipeline joined them in order with FFmpeg and sent them once to Gemini (`gemini-flash-lite-latest`; the larger
   models returned 503) for a verbatim Amharic transcript, an English translation, key moments and named places
   ([story/transcript.json](story/transcript.json)).
3. I checked the transcript. The translation had one error: "children who play and children who play" should be "children who
   played and those who didn't". I fixed it in the narration (s09).
4. I condensed my own sentences into 9 narration lines (s06 has none) and wrote the visual plan. Additions beyond my
   words are listed in DESIGN.md (the skipping rope and hide-and-seek images, and the present-day contrast in s09).

## 4. Engineering (Assignment 1: software engineering and reproducibility)

| Requirement | Where it is |
|---|---|
| Stage boundaries around a validated contract | [schema/storyboard.schema.json](schema/storyboard.schema.json) + [pipeline/validate.py](pipeline/validate.py) (schema, unique ids, 60–90 s, subtitle per line, narration fits its shot); every entry point validates first |
| Caching | `key()` in [pipeline/common.py](pipeline/common.py); keys chain (a new keyframe changes the clip key). Demonstrated: reverting the TTS model re-used the cached clips with **0 API calls** (F8) |
| Retries | `common.call_model`: exponential backoff on 429/5xx/timeouts, immediate failure on other 4xx. 40+ rate-limit and overload retries logged and recovered today |
| No secrets committed | keys live in `.env` (gitignored, verified with `git check-ignore`); the Gemini key travels in a header, never a URL |
| runs.jsonl complete | 120 lines: every attempt, success or failure, with stage, shot, model, params, seed, latency, status, error, GPU-s. Kaggle GPU logs are merged on import |
| One documented command | `python film.py`; `--radio`, `--shot s03`, `--offline` variants in the README |
| Remote GPU without a browser | **new:** [pipeline/kaggle_run.py](pipeline/kaggle_run.py) uploads the job as a private dataset, pushes a GPU kernel, polls, downloads and imports, in one command |

Changes I made to the starter pipeline today, each traceable to a FAILURES or EXPERIMENTS entry:
- `truststore` so HTTPS works behind Avast's TLS inspection (F4)
- model ids moved to current ones (F5)
- full-HD keyframes and a 1080p edit (E1)
- prompt structure against reference leakage (E2)
- Ethiopic font on the end card
- keyframe fallback in assembly (F6)
- the Kaggle runner, with retries and correct status parsing (F7, F9)
- ACE-Step API and memory fixes (F9, F10)
- the music-candidate resolution bug (F11)

## 5. Experiments (E1–E4, more pending)

| # | Question | Evidence | Decision |
|---|---|---|---|
| E1 | Which FLUX model gives the clearest keyframes? | Same prompt and seed on FLUX.2 dev (11.3 s) vs klein-9b (12.6 s); dev soft and washed out with wrong tibeb colours; klein-9b crisp and correct; full HD 15.1 s | klein-9b, rendered natively at 1920×1088 |
| E2 | Do reference images keep characters consistent without hurting composition? | First pass: consistent faces, but the alley from the reference sheet leaked into the indoor s05; young me drawn twice in s03/s07 | Plain-background reference sheets; scene first in the prompt; "appearance only, each character once"; explicit skin tone |
| E3 | Which TTS model and delivery-note language pronounce Amharic best? | Round-trip ASR on four lines × three settings (`outputs/smoke/e3_tts.json`) | Keep 2.5 + English note. An Amharic note gets *spoken aloud*; 3.8 also speaks the English note (F8) |
| E4 | Does ACE-Step understand "krar / masinko / kebero"? | 6 candidates in 2 rounds, ffmpeg loudness + blind written review (`outputs/music/candidate_review.json`) | Round 1: 0/3 sound Ethiopian (best 6/10). Round 2, describing timbre: c2 8.5/10 "evokes Ethiopian folk". Selected |

Planned next, to reach ten or more: E5 Wan draft vs final resolution; E6 Wan clip vs pan-and-zoom (did viewers notice?);
E7 ducking depth; E8 seed sensitivity for young me; E9 short-line pronunciation fixes (adding context to a line);
E10 9:16 framing (blurred fill vs native vertical keyframes).

## 6. Troubleshooting (F4–F11, all from today)

| # | Blocker | Resolution |
|---|---|---|
| F4 | Every API call failed `CERTIFICATE_VERIFY_FAILED` | Diagnosed Avast HTTPS scanning (curl worked, Python did not); `truststore` uses the Windows store, verification stays on |
| F5 | Text model 503/404/timeout; FLUX schnell rejects `seed`; TTS rejects a 2-word prompt | Listed available models, switched ids in `.env`, and moved to FLUX.2 |
| F6 | Cloudflare daily allowance (10,000 neurons) exhausted; Gemini image models and Lyria have no free quota | Older-keyframe fallback so a preview is always possible; corrected frames render after the reset |
| F7 | ACE-Step would not install: Kaggle is Python 3.13, ACE-Step needs <3.13 | Isolated Python 3.12 env with `uv` inside the kernel |
| F8 | Newer TTS read the stage direction aloud (13 s for 3 words) | Caught by the duration check, confirmed with a transcribe-everything check; reverted at zero cost via the cache |
| F9 | Kernel "complete" but all 3 candidates failed (renamed argument) | Read the current source, fixed the call, pinned torch 2.7.1; poller now parses only the status field |
| F10 | CUDA out of memory on the T4 | CPU offload, overlapped decode, free memory between candidates |
| F11 | The film silently used the wrong music candidate | Resolve by prompt key; found by reading the log line, verified by file hash |

The pattern I learned: *success signals lie*. "Kernel complete", "transcript looks right" and "score cached" were all
wrong at least once. What caught them was a second, independent check: a duration, an item count, a file hash.

## 7. Measurement

From `runs.jsonl` (`python -m pipeline.report --write` regenerates the table in [COSTS.md](COSTS.md)):

| Stage | Model | Median latency | Notes |
|---|---|---|---|
| Narration | gemini-2.5-flash-preview-tts | 5.1 s / line | 4 rate-limit retries, all recovered |
| Keyframes | FLUX.2 klein-9b (Cloudflare) | 15.9 s / image | ≈ 15–17 full-HD images per free day |
| Music | ACE-Step 3.5B on a Kaggle T4 | 184–222 GPU-s / 87 s track | 6 tracks = **19.9 GPU-min** |
| Assembly | FFmpeg, local | 10–20 min | both ratios at 1080p, x264 medium/crf 17 |

- **Cash cost:** $0 (free tiers only).
- **List-price equivalent:** *to finish.* Per-call prices still need to go into `pipeline/prices.json` from each
  provider's pricing page with the date. For GPU time, 19.9 T4-minutes at a typical on-demand T4 hourly price is
  well under a dollar; the exact figure goes in once the price page is cited.
- **Frontier comparison:** I tried Gemini's frontier image models and Lyria 3 for music; both returned 429 on the free tier,
  so there is no head-to-head yet. The attempts are logged in F6.

## 8. Consent, labelling, licences

- **Consent (C1 in [ETHICS.md](ETHICS.md)):** the story is my own and I am the storyteller.
- **No real person is shown or voiced:** young me and the neighbourhood children are invented AI characters, the adult me is
  shown only from behind, and the narrator is a prebuilt Gemini voice (Sulafat), not a clone of my voice.
- ***Gemena* is a real TV drama:** it is named in my narration as a memory, but no footage, logo or actor appears. The TV screen is only light.
- **Labelling:** the end card in both exports says "Made with AI…" (the schema requires it), and the platform AI label will be switched on when posting.
- **Licences:** listed per component in ETHICS.md. The FLUX.2 klein-9B weights licence must be verified on the model card (the 4B
  variant is Apache 2.0, the 9B differs). I have flagged it rather than assumed it.

## 9. Learning from my audience: *pending*

User test 1 (radio cut: `python film.py --radio`) and user test 2 (this near-final cut), at least three people
from the audience each, are not done yet. After each test, I will record in [DESIGN.md](DESIGN.md):
- what landed and what confused them, with direct quotes
- the exact storyboard change it caused

The questions I most want answered:
1. Do the short Amharic lines sound natural? The automated check flagged s01, s02, s08 and s10.
2. Does the silent s06 beat land, or feel like a gap?
3. Does s09 (a child alone with a tablet) feel true or preachy?
4. Do people recognise the one-TV-house ritual without explanation?

## 10. Suggested practices tested honestly

- **A practice that beat my instinct: generate several candidates and choose.** My instinct was that one good prompt is enough.
  E4 shows otherwise: with the *same* improved prompt, one seed gave an 8.5/10 Ethiopian-sounding score and another
  slid back to synth-pop (4/10). Without three candidates I would have kept a worse score and blamed the prompt.
- **A practice that did not beat my instinct (as I applied it): automated checks as a stand-in for listening.** I used
  round-trip ASR to judge Amharic pronunciation (E3). It ranked the newer TTS model best, and that model was speaking the stage
  direction aloud (F8). The automatic check was useful for screening, but my instinct (a native speaker must listen) was right.
  It is still the open item.

## 11. Curiosity beyond the floor

- **A tool others can use:** `pipeline/kaggle_run.py` runs any Kaggle GPU job from the command line (upload, run, poll,
  fetch, import) with retries and honest status. It turned the browser round trip into one command and made it practical to run four
  debugging iterations in an evening.
- **Native-language narration:** Amharic narration (not the brief's English default), with a round-trip ASR method
  to screen TTS output in a language I could otherwise only check by ear. It also documents a real failure mode
  (instructions spoken aloud) that others narrating in Amharic are likely to hit.
- **Prompting an open music model for a culture it barely knows (E4):** describing timbre instead of instrument names
  is a transferable finding for anyone scoring Ethiopian (or other under-represented) music with ACE-Step.

## 12. Hardest problem so far

The music. It took five Kaggle runs:
1. Install failure on Python 3.13
2. Transient upload drop
3. A "complete" run that produced nothing (renamed argument)
4. Out of GPU memory
5. Three working tracks that sounded Western

That was followed by a second prompt round and a silent wrong-file bug in my own resolution code. Each fix is in F7, F9, F10, F11 and E4.
What solved it was refusing to trust the top-level signal and reading the per-item log every time.

---

## Appendix: repository map

| Path | What it is |
|---|---|
| `film.py` | The one command: validate → narration → keyframes → shots → music → assemble |
| `storyboard.json` | The contract: the whole film as data |
| `schema/storyboard.schema.json` | JSON Schema the storyboard must pass |
| `pipeline/common.py` | Cache keys, retries, `runs.jsonl` logging, ffmpeg, OS certificate store |
| `pipeline/validate.py` | Schema plus semantic checks (length, ids, subtitle per line, narration fit) |
| `pipeline/narration.py` | Gemini TTS per line |
| `pipeline/keyframes.py` | Reference sheets plus one full-HD keyframe per shot (FLUX.2 on Cloudflare) |
| `pipeline/shots.py`, `kaggle/wan22_i2v.py` | Wan 2.2 image-to-video job bundle and GPU worker |
| `pipeline/music.py`, `kaggle/acestep_music.py` | ACE-Step job, GPU worker, candidate selection |
| `pipeline/kaggle_run.py` | One-command Kaggle round trip |
| `pipeline/assemble.py` | Ken Burns or clip, voice placement, ducking, loudness, subtitles, both aspect ratios, end card |
| `pipeline/report.py` | Builds the cost and latency table from `runs.jsonl` |
| `pipeline/smoke.py` | One call per provider, to check keys and models |
| `story/transcript.json` | Transcript and translation of my voice notes (the audio itself is not committed) |
| `runs.jsonl` | Every model call |
| `outputs/` | Reference sheets, keyframes, narration, music candidates, final films |
| `DESIGN.md` · `ARCHITECTURE.md` · `EXPERIMENTS.md` · `FAILURES.md` · `COSTS.md` · `ETHICS.md` | Process documents |
