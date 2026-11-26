"""ACE-Step score generator. Runs on Kaggle/Colab with a GPU.

Reads music_job.json (from `python -m pipeline.music prepare`), renders N
candidates with different seeds, and writes c1.<key>.wav, c2.<key>.wav, ... plus
music_runs.jsonl in runs.jsonl format.

The only ACE-Step-specific code is generate_one(). It uses the pipeline API from
the ACE-Step repository. If the 1.5 release has changed its entry point, replace
the body of generate_one() with the snippet from the ACE-Step 1.5 README and
record the change in FAILURES.md. Everything else stays the same.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--job", required=True, help="path to music_job.json")
ap.add_argument("--out", default="/kaggle/working/music")
ap.add_argument("--steps", type=int, default=60)
ap.add_argument("--dtype", default="float32", help="T4: float32 (no native bf16)")
ap.add_argument("--no-offload", action="store_true", help="keep all modules on the GPU (needs >16 GB in float32)")
args = ap.parse_args()

job = json.loads(Path(args.job).read_text(encoding="utf-8"))
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
log_path = out / "music_runs.jsonl"
MODEL = "ACE-Step"

from acestep.pipeline_ace_step import ACEStepPipeline  # noqa: E402

# float32 on a 16 GB T4 runs out of memory for an ~90 s score (FAILURES.md F10): offload idle modules to CPU
# and decode the latent in overlapping chunks.
pipe = ACEStepPipeline(checkpoint_dir=None, dtype=args.dtype, torch_compile=False,
                       cpu_offload=not args.no_offload, overlapped_decode=not args.no_offload)


def generate_one(prompt: str, lyrics: str, duration: float, seed: int, path: Path) -> None:
    pipe(audio_duration=duration, prompt=prompt, lyrics=lyrics, infer_step=args.steps, guidance_scale=15,
         scheduler_type="euler", cfg_type="apg", omega_scale=10, manual_seeds=[seed], guidance_interval=0.5,
         guidance_interval_decay=0.0, min_guidance_scale=3.0, use_erg_tag=True, use_erg_lyric=True, use_erg_diffusion=True,
         oss_steps=None, guidance_scale_text=0.0, guidance_scale_lyric=0.0, save_path=str(path))


prompt = job["prompt"] + (f", {job['bpm']} bpm" if job.get("bpm") else "")
for c in job["candidates"]:
    dst = out / f"{c['id']}.{job['key']}.wav"
    t0 = time.perf_counter()
    status, err = "ok", None
    try:
        generate_one(prompt, job["lyrics"], job["duration_s"], c["seed"], dst)
    except Exception as e:
        status, err = "error", repr(e)[:500]
    lat = round(time.perf_counter() - t0, 1)
    try:  # free what a failed candidate left behind, so the next one starts clean
        import gc, torch
        gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "job_id": f"{dst.name}:{status}:{int(time.time())}", "stage": "music",
                             "shot": c["id"], "provider": "kaggle", "model": MODEL,
                             "params": {"prompt": prompt, "duration_s": job["duration_s"], "steps": args.steps},
                             "seed": c["seed"], "latency_s": lat, "gpu_s": lat, "status": status,
                             "error": err, "cost_usd": 0.0, "output": dst.name}) + "\n")
    print(f"{c['id']}: {status} in {lat:.0f}s {err or ''}", flush=True)
