# Ethics: consent, licences, labelling, data

## Consent
Record this **before** generating anything of a real person's face, likeness or voice.

| Person (role, e.g. "my grandmother") | What is depicted (story / likeness / voice) | Informed of | Agreed to the exact narration text? | How recorded (audio / written / message) | Date | `consent_ref` |
|---|---|---|---|---|---|---|
| TODO | | that AI will generate images/voice, that it will be posted publicly, which platforms | | | | C1 |

- Characters with `"real_person": true` in storyboard.json must carry a `consent_ref` (the schema enforces it).
- The narration uses a **prebuilt** Gemini TTS voice. No real person's voice is cloned. (If you change this, record consent above.)
- Words spoken in the film: TODO: confirm the storyteller heard or read the final narration and agreed.

## Licences
Verify each entry against the model card on the day you use it.

| Component | Model | Licence / terms | Output use |
|---|---|---|---|
| Keyframes | FLUX.1 [schnell] (Black Forest Labs) via Cloudflare Workers AI | Apache 2.0 weights; Cloudflare Workers AI terms | TODO: verify |
| Keyframes (alt) | FLUX.2 [klein] | TODO: check the variant's licence (they differ by size) | |
| Moving shots | Wan 2.2 TI2V-5B | Apache 2.0 | Permitted |
| Music | ACE-Step 1.5 | TODO: weights licence | Outputs usable commercially (per challenge brief; verify) |
| Narration | Gemini TTS (Google) | Gemini API terms; free-tier data may be used to improve Google products | TODO |
| Script/translation | Gemini Flash | Gemini API terms | |
| Edit | FFmpeg (via imageio-ffmpeg) | LGPL/GPL build | Tool only |
| Fonts | Arial (Windows) / DejaVu Sans | System font / free licence | Burned into video |

## Labelling
- End card in both exports: "Made with AI ..." (the schema requires an end-card line containing "AI").
- MP4 metadata `comment`: "Made with AI (Gemini TTS, FLUX, Wan 2.2, ACE-Step)".
- Platform AI-content disclosure switched on when posting: TODO: platform, screenshot link.
- Provenance: no watermark or metadata removal steps exist in the pipeline. SynthID in Gemini audio is left intact.
- Style prompts describe qualities (warm, grainy, hand-painted) and never name a living artist.

## Private data
Free-tier endpoints may use prompts for training. Kept out of all prompts: TODO (e.g. full names of living relatives,
village names, phone numbers, health details). The story notes file used for `pipeline.script draft` was reviewed for this.
