"""Wan 2.2 TI2V-5B image-to-video worker. Runs on Kaggle (GPU T4 x2) or Colab.

It reads jobs.json from the bundle made by `python -m pipeline.shots prepare`,
renders only those clips, and writes one log line per clip in the same format as
runs.jsonl, so `pipeline.shots import` can merge GPU timings into the main log.

Two T4s: run one process per GPU, each taking every 2nd job:
    !python wan22_i2v.py --bundle /kaggle/input/<dataset> --gpu 0 --of 2 &> log0.txt &
    !python wan22_i2v.py --bundle /kaggle/input/<dataset> --gpu 1 --of 2 &> log1.txt
See kaggle/README.md for the full notebook.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--bundle", required=True, help="folder containing jobs.json and keyframes")
ap.add_argument("--out", default="/kaggle/working/clips")
ap.add_argument("--gpu", type=int, default=0)
ap.add_argument("--of", type=int, default=1, help="number of parallel workers")
ap.add_argument("--dtype", default="float16", help="T4 has no native bf16; try float16 first, bfloat16 if you see NaN/black frames")
ap.add_argument("--fps", type=int, default=24)
args = ap.parse_args()
os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)

import torch  # noqa: E402  (after CUDA_VISIBLE_DEVICES)
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline  # noqa: E402
from diffusers.utils import export_to_video, load_image  # noqa: E402

bundle = next(Path(args.bundle).rglob("jobs.json")).parent
jobs = json.loads((bundle / "jobs.json").read_text(encoding="utf-8"))
mine = [j for i, j in enumerate(jobs) if i % args.of == args.gpu]
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
log_path = out / f"wan_runs_gpu{args.gpu}.jsonl"
if not mine:
    sys.exit(0)

model_id = mine[0]["model"]
t_load = time.perf_counter()
vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(model_id, vae=vae, torch_dtype=getattr(torch, args.dtype))
pipe.enable_model_cpu_offload()  # 16 GB T4: keep only the active module on the GPU
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
print(f"loaded {model_id} in {time.perf_counter() - t_load:.0f}s; {len(mine)} job(s) on GPU {args.gpu}", flush=True)


def log(**f):
    f = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": "shots", "provider": "kaggle",
         "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "cost_usd": 0.0, **f}
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(f, ensure_ascii=False) + "\n")


for j in mine:
    dst = out / j["output"]
    if dst.exists():
        continue
    w, h = map(int, j["size"].split("*"))
    params = {k: j[k] for k in ("size", "frames", "steps", "guidance")} | {"dtype": args.dtype}
    t0 = time.perf_counter()
    try:
        image = load_image(str(bundle / j["keyframe"])).resize((w, h))
        frames = pipe(image=image, prompt=j["prompt"], negative_prompt=j.get("negative_prompt") or None,
                      height=h, width=w, num_frames=j["frames"], num_inference_steps=j["steps"],
                      guidance_scale=j["guidance"], generator=torch.Generator("cpu").manual_seed(j["seed"])).frames[0]
        export_to_video(frames, str(dst), fps=args.fps)
        lat = round(time.perf_counter() - t0, 1)
        log(job_id=j["output"], shot=j["shot"], model=model_id, params=params, seed=j["seed"],
            latency_s=lat, gpu_s=lat, status="ok", attempt=1, output=j["output"])
        print(f"{j['shot']}: {lat:.0f}s -> {dst.name}", flush=True)
    except Exception as e:  # keep going: one bad shot must not burn the session
        lat = round(time.perf_counter() - t0, 1)
        log(job_id=j["output"] + ":err:" + str(int(time.time())), shot=j["shot"], model=model_id, params=params,
            seed=j["seed"], latency_s=lat, gpu_s=lat, status="error", attempt=1, error=repr(e)[:500])
        print(f"{j['shot']}: FAILED {e!r}", flush=True)
        torch.cuda.empty_cache()
