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
