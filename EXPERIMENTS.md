# Experiments

Format: **hypothesis → change → result (measured) → decision**. Reference the runs.jsonl lines (ts or output file)
that are the evidence. Aim for about ten entries. One well-measured experiment that changed your mind beats five vague ones.

Suggested experiments the pipeline already supports (each one is a storyboard or `.env` change plus a re-run):

1. Character consistency: locked description only (FLUX.1 schnell) vs. reference sheet as input image (a FLUX.2 model in `KEYFRAME_MODEL`).
2. Seed sensitivity: same prompt, 3 seeds; does the character stay recognisable?
3. Wan draft vs final: 832×480/30 steps vs 1280×704/50 steps; GPU seconds vs visible quality.
4. Wan on T4: `--dtype float16` vs `bfloat16` (speed, NaN/black frames).
5. TTS delivery: with and without `style_prompt`; which did listeners prefer?
6. TTS voice: two or three voices for the narration language; pronunciation of names and places.
7. Ducking depth: `music.duck.ratio` 4 vs 8 vs 12; can listeners follow every word?
8. Score: ACE-Step candidates c1–c3; why the chosen one won.
9. Narration language: Amharic vs Afaan Oromo / Tigrinya with the same TTS. Where does it fail?
10. Pan-and-zoom fallback vs Wan clip for the same shot: did viewers notice?

---

## E1: Keyframe model: FLUX.1 schnell vs FLUX.2 dev vs FLUX.2 klein-9b (2026-11-26)
- **Hypothesis:** FLUX.2 gives sharper, more faithful keyframes than schnell, and the extra latency is worth it,
  because every later stage (Wan motion, pan-and-zoom, 9:16 export) can only lose detail, never add it.
- **Change:** same prompt (style block + s02 "tying her netela inside a tukul" + Etete's locked description),
  seed 102, 1280×720, on `@cf/black-forest-labs/flux-2-dev` and `flux-2-klein-9b`. Schnell could not take part with a fixed seed (F5).
- **Result:** dev took 11.3 s, klein-9b 12.6 s (wall clock, run by hand outside runs.jsonl, files in `outputs/smoke/`).
  dev: soft, washed-out, the "film grain" read as low resolution, and the tibeb border came out as rainbow stripes.
  klein-9b: crisp face and braids, a correct narrow green-yellow-red tibeb on the dress hem and sleeves, and warm
  directional light that matches the style block. A follow-up klein-9b render at 1920×1088 (15.1 s) stayed sharp,
  with a painterly finish.
- **Decision:** `KEYFRAME_MODEL=@cf/black-forest-labs/flux-2-klein-9b`, keyframes rendered natively at 1920×1088 and
  cropped to 1920×1080 (previously 1024×576, upscaled twice). The assemble working resolution is raised from 1280×720 to 1920×1080
  and the encode from `veryfast/crf19` to `medium/crf17`, so the final 16:9 export is never upscaled.

## E2: Reference images leak their background into shots (FLUX.2 klein-9b)
- **Hypothesis:** passing each character's reference sheet as an input image keeps young me and the neighbourhood
  kids consistent across shots without hurting scene composition.
- **Change:** first pass: reference sheets generated with the full style block (which names the neighbourhood);
  shot prompt = style, then scene, then characters.
- **Result:** characters were consistent, but the references took over composition. The `sefer_kids` sheet came out
  as an alley scene, and s05 (meant to be *indoors at night*) rendered the TV outside in that alley; s02 and s04 reused
  the same pose. s03 and s07 drew young me twice. The boy in blue came out light-skinned, because his text gave no skin tone.
- **Decision:** reference sheets on a plain white background ("rendering style only, ignore any place"); shot prompt
  puts the scene first and says references are "appearance only… each character appears exactly once"; every
  character description states skin tone; "No text, signs or writing" appended (klein ignores negative prompts;
  s10 had a painted shop sign). Re-render pending (F6); compare the s05 keyframes before and after.

## E3: Amharic TTS clarity: model and language of the delivery note
- **Hypothesis:** the newer `gemini-3.8-flash-tts`, or a delivery note written in Amharic, pronounces short Amharic
  lines more clearly than `gemini-2.5-flash-preview-tts` with an English note.
- **Method:** round-trip ASR: synthesise s01/s02/s08/s10, transcribe back with `gemini-flash-lite-latest`, compare with
  the script (`outputs/smoke/e3_tts.json`, `outputs/narration/roundtrip.json`). As a calibration, the same ASR
  transcribed my own 61 s voice notes almost perfectly.
- **Result:** 2.5 + English note (the current narration): long lines (s04, s09) came back near verbatim, short lines
  were garbled (s01 "ሊጀነቲም በጣም ይወርዳል"). 3.8 + English note *looked* best in the Amharic-only transcript. An Amharic note made the
  model *speak the note* ("በአማርኛ፣ በዝግታና…" heard before every line). Follow-up (F8): 3.8 speaks the English note too.
- **Decision:** keep 2.5 + English note. Short lines are the weak spot, so the next step is my own native-speaker
  listening test of every line. Round-trip ASR is a screening tool, not a verdict.

## E4: Score prompt: naming Ethiopian instruments vs describing their sound (ACE-Step, Kaggle T4)
- **Hypothesis:** ACE-Step does not know "krar / masinko / kebero" as tokens. Describing what they sound like (plucked lyre,
  bowed single-string fiddle, hand drums, pentatonic, tizita, ethio-jazz) and excluding synths will give a more
  Ethiopian-sounding score.
- **Change:** round 1 prompt = "nostalgic Ethiopian instrumental, playful krar melody, soft masinko, light kebero…" (key
  `c004dd0ca3b8`); round 2 = "acoustic, organic, ethio-jazz, East African folk, plucked lyre, bowed single-string fiddle,
  wooden flute, hand drums, pentatonic melody, tizita… no synthesizer, no electronic drums" (key `cbe59d023da9`). Same seeds
  4200–4202, 87 s, 60 steps, float32 with CPU offload; 184–222 GPU-s per candidate (runs.jsonl, stage=music).
- **Evaluation:** loudness/LRA/silence via ffmpeg `ebur128`/`silencedetect`, plus a blind written review per track by
  `gemini-flash-lite-latest` with the same 5 questions (`outputs/music/candidate_review.json`). Then my own listening.
- **Result:** round 1: all three judged electronic/synth, 0/3 "sounds Ethiopian"; best 6/10 (c1, nice build), c2 3/10 (ends abruptly at 1:04).
  Round 2: c2 judged "plucked acoustic instruments reminiscent of krar… evokes traditional Ethiopian folk", 8.5/10, no glitches;
  c1 acoustic guitar 6/10; c3 still synth-pop 4/10 despite "no synthesizer" (negative words in the prompt are only weakly obeyed).
- **Decision:** `music.selected = c2` (round 2). Describing timbre beats naming instruments the model does not know.
  One of three seeds still drifted to synth, so generating several candidates is necessary, not optional.
