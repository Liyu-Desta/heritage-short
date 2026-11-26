# Ethics: consent, licences, labelling, data

## Consent
Record this **before** generating anything of a real person's face, likeness or voice.

| Person (role, e.g. "my grandmother") | What is depicted (story / likeness / voice) | Informed of | Agreed to the exact narration text? | How recorded (audio / written / message) | Date | `consent_ref` |
|---|---|---|---|---|---|---|
| Me, the filmmaker and storyteller (my own childhood) | My story, told in my words; **no likeness** (young me is an invented AI character; the adult me is shown only from behind); **no voice clone** (prebuilt Gemini voice Sulafat) | AI generates all images, motion, music and the narrator voice; the film is posted publicly with an AI label (TikTok / Telegram / Facebook) | Yes: I wrote and approved every narration line in storyboard.json | My own two voice notes (story/tenx1.ogg, tenx2.ogg, kept out of git) and this record | 2026-11-26 | C1 |

- Characters with `"real_person": true` in storyboard.json must carry a `consent_ref` (the schema enforces it).
- The narration uses a **prebuilt** Gemini TTS voice. No real person's voice is cloned. (If you change this, record consent above.)
- Words spoken in the film: they are my own, condensed from my voice notes; I approved the final Amharic lines and English subtitles.
- Other people: the neighbourhood children and the child with a tablet are invented, not real neighbours. No real person's face or voice appears.
- *Gemena* is a real Ethiopian TV drama. The film names it in narration as part of my memory, but shows no footage, logo, title card or actors; the TV screen is only glow.

## Licences
Verify each entry against the model card on the day you use it.

| Component | Model | Licence / terms | Output use |
|---|---|---|---|
| Keyframes | FLUX.1 [schnell] (Black Forest Labs) via Cloudflare Workers AI | Apache 2.0 weights; Cloudflare Workers AI terms | TODO: verify |
| Keyframes (used) | FLUX.2 [klein] 9B via Cloudflare Workers AI | TODO: verify on the model card: the 4B is Apache 2.0, the 9B uses a non-commercial weights licence; generated via Cloudflare's hosted API under Workers AI terms | Non-commercial heritage film |
| Moving shots | Wan 2.2 TI2V-5B | Apache 2.0 | Permitted |
| Music | ACE-Step 1.5 | TODO: weights licence | Outputs usable commercially (per challenge brief; verify) |
| Narration | Gemini TTS (Google), gemini-2.5-flash-preview-tts | Gemini API terms; free-tier data may be used to improve Google products | Prebuilt voice; output usable per terms |
| Story transcription | Gemini flash-lite (audio in) | Gemini API terms | My own voice notes, sent once for transcription (story/transcript.json) |
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
Free-tier endpoints may use prompts for training. Kept out of all prompts: my full name, neighbours' names, the exact neighbourhood (prompts say only "an Addis Ababa neighbourhood"),
phone numbers. The story notes file used for `pipeline.script draft` was reviewed for this.
