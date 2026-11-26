"""Stage: assembly. Everything is derived from storyboard.json + outputs/, in code:

  picture   clip (Wan) > pan-and-zoom of keyframe > black, cut to each shot's duration
  voice     each narration wav placed at shot start + narration_offset_s
  music     score looped/trimmed to length, faded, ducked under the voice (sidechain compressor)
  mix       voice + ducked music, loudness-normalised (EBU R128, default -14 LUFS for social)
  subtitles English SRT from translation_en, timed to the narration, burned in
  end card  "made with AI" card rendered per aspect ratio
  export    16:9 (1920x1080) and 9:16 (1080x1920, blurred fill), plus subs.srt

    python -m pipeline.assemble            # both aspect ratios
    python -m pipeline.assemble --radio    # radio cut: narration + music + subs on black, 16:9
"""
from __future__ import annotations

import argparse
import re
import shutil
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.common import OUT, ffmpeg, load_storyboard, media_duration, say
from pipeline.keyframes import keyframe_spec
from pipeline.music import SCORE, run as resolve_music
from pipeline.narration import narration_path
from pipeline.shots import clip_path

WORK = OUT / "assemble"
FINAL = OUT / "final"
WW, WH = 1920, 1080  # working resolution for shot segments (full HD, matches keyframes)
ASPECTS = {"16x9": (1920, 1080), "9x16": (1080, 1920)}
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-an"]


# -------------------------------------------------------------------- picture
def kenburns_filter(camera: str, frames: int, fps: int) -> str:
    n = max(frames - 1, 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = {
        "push_in": (f"1+0.12*on/{n}", cx, cy),
        "pull_out": (f"1.12-0.12*on/{n}", cx, cy),
        "pan_right": ("1.12", f"(iw-iw/zoom)*on/{n}", cy),
        "pan_left": ("1.12", f"(iw-iw/zoom)*(1-on/{n})", cy),
        "static": (f"1+0.03*on/{n}", cx, cy),
    }[camera]
    # upscale first so sub-pixel zoom steps do not jitter
    return f"scale=3840:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WW}x{WH}:fps={fps}"


def shot_segment(sb: dict, s: dict, out: Path, fps: int, radio: bool) -> str:
    d = s["duration_s"]
    frames = round(d * fps)
    clip = None if radio else clip_path(sb, s)
    _, _, kf = keyframe_spec(sb, s)
    if clip and clip.exists():
        cd = media_duration(clip)
        stretch = min(max(d / cd, 1.0), 1.6)  # slow down up to 1.6x, then hold the last frame
        ffmpeg("-i", clip, "-vf",
               f"scale={WW}:{WH}:force_original_aspect_ratio=increase,crop={WW}:{WH},setpts={stretch:.4f}*PTS,"
               f"fps={fps},tpad=stop_mode=clone:stop_duration={d}", "-frames:v", frames, *ENC, out)
        return "clip"
    if not radio and kf.exists():
        ffmpeg("-loop", "1", "-i", kf, "-vf", kenburns_filter(s.get("camera", "push_in"), frames, fps),
               "-frames:v", frames, *ENC, out)
        return "pan-zoom"
    ffmpeg("-f", "lavfi", "-i", f"color=c=black:s={WW}x{WH}:r={fps}", "-frames:v", frames, *ENC, out)
    return "black"


def font(size: int, bold: bool = False):
    for name in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def end_card(sb: dict, w: int, h: int, path: Path) -> None:
    im = Image.new("RGB", (w, h), (14, 12, 10))
    dr = ImageDraw.Draw(im)
    lines = [sb["title"]] + sb["end_card"]["lines"]
    unit = min(w, h)
    fonts = [font(int(unit * 0.065), bold=True)] + [font(int(unit * 0.036))] * (len(lines) - 1)
    wrapped = [(textwrap.fill(t, width=28 if w < h else 48), f) for t, f in zip(lines, fonts)]
    gap = int(unit * 0.035)
    sizes = [dr.multiline_textbbox((0, 0), t, font=f, align="center") for t, f in wrapped]
    total = sum(b[3] - b[1] for b in sizes) + gap * (len(sizes) - 1)
    yy = (h - total) // 2
    for (t, f), b in zip(wrapped, sizes):
        tw = b[2] - b[0]
        dr.multiline_text(((w - tw) // 2, yy), t, font=f, fill=(240, 232, 220), align="center")
        yy += b[3] - b[1] + gap
    im.save(path)


# ---------------------------------------------------------------------- audio
def build_audio(sb: dict, total: float, starts: list[float], out: Path) -> list[tuple[float, float, str]]:
    """Returns subtitle cues (start, end, text) timed to the actual narration."""
    offset = sb.get("render", {}).get("narration_offset_s", 0.4)
    m = sb["music"]
    duck = {"threshold": 0.03, "ratio": 8, "attack_ms": 20, "release_ms": 400} | m.get("duck", {})
    inputs, filters, labels, cues = [], [], [], []
    for s, t0 in zip(sb["shots"], starts):
        wav = narration_path(sb, s)
        sub = s["narration"]["translation_en"].strip()
        if wav and wav.exists():
            i = len(inputs) // 2  # two argv entries per input
            inputs += ["-i", wav]
            ms = int((t0 + offset) * 1000)
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[n{i}]")
            labels.append(f"[n{i}]")
            dur = media_duration(wav)
            cues.append((t0 + offset, t0 + offset + dur, sub))
        elif sub:  # narration not generated yet: still show the subtitle for the shot
            if s["narration"]["text"].strip():
                say(f"  warn: {s['id']} has no narration audio yet (run the narration stage)")
            cues.append((t0 + offset, t0 + s["duration_s"] - 0.2, sub))
    mi = len(inputs) // 2
    inputs += ["-stream_loop", "-1", "-i", SCORE]
    fade_out = max(total - 3.5, 0)
    filters.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total},asetpts=N/SR/TB,"
                   f"volume={m.get('bed_db', -6)}dB,afade=t=in:d=1.5,afade=t=out:st={fade_out}:d=3.5[music]")
    lufs = sb.get("render", {}).get("loudness_lufs", -14)
    if labels:
        filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad=whole_dur={total},"
                       f"atrim=0:{total}[voice]")
        filters.append("[voice]asplit=2[vsc][vmix]")
        filters.append(f"[music][vsc]sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:"
                       f"attack={duck['attack_ms']}:release={duck['release_ms']}[ducked]")
        filters.append("[ducked][vmix]amix=inputs=2:normalize=0[mix]")
    else:
        filters.append("[music]anull[mix]")
    filters.append(f"[mix]loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000[out]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-t", total, "-ar", "48000",
           "-c:a", "pcm_s16le", out)
    return cues


def split_cues(cues: list[tuple[float, float, str]], max_chars: int = 84) -> list[tuple[float, float, str]]:
    """Split long lines at a sentence/comma boundary, timed in proportion to length."""
    out = []
    for start, end, text in cues:
        if not text:
            continue
        parts = [text]
        if len(text) > max_chars:
            cut = max((m.end() for m in re.finditer(r"[.,;:!?]\s", text[: len(text) // 2 + 20])), default=0) \
                  or text.rfind(" ", 0, len(text) // 2 + 1)
            parts = [text[:cut].strip(), text[cut:].strip()]
        span, t = end - start, start
        for p in parts:
            dt = span * len(p) / max(sum(map(len, parts)), 1)
            out.append((t, t + dt, p))
            t += dt
    return out


def write_srt(cues, path: Path) -> None:
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    path.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)),
                    encoding="utf-8")


def write_ass(cues, path: Path, aspect: str) -> None:
    """Burn-in subtitles in pixel coordinates (PlayRes = frame size), so placement is exact."""
    w, h = ASPECTS[aspect]
    if aspect == "16x9":
        size, align, mv, ml = 52, 2, 48, 140  # bottom centre
    else:
        size, align, mv, ml = 56, 8, round((h + w * 9 / 16) / 2) + 36, 70  # hang just below the picture

    def ts(t: float) -> str:
        cs = int(round(t * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{size},&H00FFFFFF,&H000000FF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,3,1.5,{align},{ml},{ml},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,{ts(a)},{ts(b)},Default,,0,0,0,,{t.replace(chr(10), ' ')}" for a, b, t in cues]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- export
def compose(body: Path, aspect: str, fps: int, out: Path) -> None:
    w, h = ASPECTS[aspect]
    if aspect == "16x9":
        vf = f"scale={w}:{h},ass=subs_{aspect}.ass"
    else:  # 16:9 picture centred on a blurred, darkened fill
        vf = (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=24:2,"
              f"eq=brightness=-0.18[bg];[b]scale={w}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,ass=subs_{aspect}.ass")
    ffmpeg("-i", body.name, "-filter_complex", vf, "-r", fps, *ENC, out.name, cwd=WORK)


def build(sb: dict, radio: bool = False, aspects: list[str] | None = None) -> list[Path]:
    fps = sb.get("render", {}).get("fps", 24)
    aspects = ["16x9"] if radio else (aspects or list(ASPECTS))
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    resolve_music(sb)

    starts, t = [], 0.0
    for s in sb["shots"]:
        starts.append(t)
        t += s["duration_s"]
    body_dur, ec = t, sb["end_card"]["duration_s"]
    total = body_dur + ec
    say(f"[assemble] {'RADIO CUT ' if radio else ''}{len(sb['shots'])} shots, {body_dur:.1f}s + {ec}s end card")

    names = []
    for i, s in enumerate(sb["shots"]):
        seg = WORK / f"seg_{i:02d}.mp4"
        kind = shot_segment(sb, s, seg, fps, radio)
        say(f"  {s['id']}: {kind:8s} {s['duration_s']}s")
        names.append(seg.name)
    (WORK / "segs.txt").write_text("".join(f"file '{n}'\n" for n in names), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", "segs.txt", "-c", "copy", "body.mp4", cwd=WORK)

    cues = split_cues(build_audio(sb, total, starts, WORK / "mix.wav"))
    slug = re.sub(r"[^a-z0-9]+", "_", sb["title"].lower()).strip("_")[:40]
    write_srt(cues, FINAL / f"{slug}.en.srt")  # sidecar for platforms that take caption files

    results = []
    for a in aspects:
        w, h = ASPECTS[a]
        write_ass(cues, WORK / f"subs_{a}.ass", a)
        compose(WORK / "body.mp4", a, fps, WORK / f"body_{a}.mp4")
        end_card(sb, w, h, WORK / f"endcard_{a}.png")
        ffmpeg("-loop", "1", "-i", f"endcard_{a}.png", "-vf", f"fps={fps},fade=t=in:d=0.6", "-frames:v",
               round(ec * fps), *ENC, f"endcard_{a}.mp4", cwd=WORK)
        (WORK / f"final_{a}.txt").write_text(f"file 'body_{a}.mp4'\nfile 'endcard_{a}.mp4'\n", encoding="utf-8")
        ffmpeg("-f", "concat", "-safe", "0", "-i", f"final_{a}.txt", "-c", "copy", f"video_{a}.mp4", cwd=WORK)
        dst = FINAL / (f"{slug}_radio_cut.mp4" if radio else f"{slug}_{a}.mp4")
        ffmpeg("-i", WORK / f"video_{a}.mp4", "-i", WORK / "mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
               "-metadata", f"title={sb['title']}", "-metadata",
               "comment=Made with AI (Gemini TTS, FLUX, Wan 2.2, ACE-Step). See ETHICS.md.", dst)
        say(f"  -> {dst.relative_to(OUT.parent)}  ({media_duration(dst):.1f}s)")
        results.append(dst)
    return results


def run(sb: dict, only=None, radio: bool = False) -> list[Path]:
    return build(sb, radio=radio)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--radio", action="store_true")
    ap.add_argument("--aspect", action="append", choices=list(ASPECTS))
    a = ap.parse_args()
    build(load_storyboard(), radio=a.radio, aspects=a.aspect)
