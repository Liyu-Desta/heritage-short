"""Run the GPU stages on Kaggle from the command line, no browser needed.

    python -m pipeline.kaggle_run music     # prepare music job -> upload -> run ACE-Step on a T4 -> import candidates
    python -m pipeline.kaggle_run shots     # prepare changed shots -> upload -> run Wan 2.2 on 2xT4 -> import clips
    python -m pipeline.kaggle_run status music|shots
    python -m pipeline.kaggle_run pull music|shots   # download + import the output of a finished run

Needs KAGGLE_USERNAME and KAGGLE_API_TOKEN (in .env) and a phone-verified Kaggle account (GPU access).
Each run uploads a private dataset <user>/heritage-<job> (new version per run) and pushes a private
script kernel <user>/heritage-<job>-run that mounts it. Kaggle's own logs are saved next to the imported outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from pipeline.common import OUT, ROOT, env, load_storyboard, say

KAGGLE_DIR = ROOT / "kaggle"

KERNEL_SCRIPTS = {
    # Each script finds its inputs with a glob, because Kaggle's mount path for datasets has changed over time.
    "music": r'''
import glob, os, shutil, subprocess
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
src = os.path.dirname(glob.glob("/kaggle/input/**/acestep_music.py", recursive=True)[0])
sh("nvidia-smi --query-gpu=name,memory.total --format=csv")
# ACE-Step pins spacy==3.8.4 / requires Python <3.13, but Kaggle's image is 3.13 (FAILURES.md F7):
# build an isolated Python 3.12 env with uv instead of fighting the system packages.
sh("pip install -q uv && uv venv -q -p 3.12 /tmp/venv")
sh("git clone -q --depth 1 https://github.com/ace-step/ACE-Step /tmp/acestep")
sh("uv pip install -q -p /tmp/venv/bin/python torch==2.7.1 torchaudio==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu126")
sh("uv pip install -q -p /tmp/venv/bin/python -e /tmp/acestep")
sh(f"/tmp/venv/bin/python {src}/acestep_music.py --job {src}/music_job.json --out /kaggle/working/music")
shutil.make_archive("/kaggle/working/music", "zip", "/kaggle/working", "music")
''',
    "shots": r'''
import glob, os, shutil, subprocess
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
src = os.path.dirname(glob.glob("/kaggle/input/**/wan22_i2v.py", recursive=True)[0])
sh("nvidia-smi --query-gpu=name,memory.total --format=csv")
sh("pip install -q -U diffusers transformers accelerate ftfy imageio imageio-ffmpeg")
w = f"python {src}/wan22_i2v.py --bundle {src} --out /kaggle/working/clips"
p0 = subprocess.Popen(f"{w} --gpu 0 --of 2 > /kaggle/working/log0.txt 2>&1", shell=True)
sh(f"{w} --gpu 1 --of 2 2>&1 | tee /kaggle/working/log1.txt")
p0.wait(); print(open("/kaggle/working/log0.txt").read()[-3000:])
sh("cat /kaggle/working/clips/wan_runs_gpu*.jsonl > /kaggle/working/clips/wan_runs.jsonl || true")
shutil.make_archive("/kaggle/working/clips", "zip", "/kaggle/working", "clips")
''',
}


def kaggle(*args: str, check: bool = True) -> str:
    """Kaggle CLI through the OS certificate store (TLS-inspecting antivirus breaks certifi; FAILURES.md F4)."""
    user, token = env("KAGGLE_USERNAME", required=True), env("KAGGLE_API_TOKEN", required=True)
    code = "import truststore; truststore.inject_into_ssl(); import sys; from kaggle.cli import main; sys.exit(main())"
    for attempt in range(4):  # Kaggle's API sometimes drops the connection mid-request
        r = subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env={**os.environ, "KAGGLE_USERNAME": user, "KAGGLE_API_TOKEN": token})
        out = (r.stdout or "") + (r.stderr or "")
        transient = any(t in out for t in ("Connection aborted", "RemoteDisconnected", "Read timed out", " 429", " 503"))
        if r.returncode == 0 or not transient or attempt == 3:
            break
        say(f"    ! kaggle {args[0]} {args[1]}: transient error, retry {attempt + 1}/3 in {10 * 2 ** attempt}s")
        time.sleep(10 * 2 ** attempt)
    if check and r.returncode != 0:
        raise SystemExit(f"kaggle {' '.join(args)} failed:\n{out[-2000:]}")
    return out


def slugs(job: str) -> tuple[str, str]:
    user = env("KAGGLE_USERNAME", required=True)
    return f"{user}/heritage-{job}", f"{user}/heritage-{job}-run"


def upload_dataset(job: str, files: dict[str, Path]) -> None:
    ds, _ = slugs(job)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, src in files.items():
            shutil.copy2(src, d / name)
        (d / "dataset-metadata.json").write_text(json.dumps(
            {"title": f"heritage-{job}", "id": ds, "licenses": [{"name": "other"}]}), encoding="utf-8")
        exists = "error" not in kaggle("datasets", "status", ds, check=False).lower()
        if exists:
            say(f"  new version of dataset {ds}")
            kaggle("datasets", "version", "-p", str(d), "-m", time.strftime("run %Y-%m-%d %H:%M"), "-r", "zip")
        else:
            say(f"  creating private dataset {ds}")
            kaggle("datasets", "create", "-p", str(d), "-r", "zip")
    for _ in range(60):  # wait until the new version is ready, or the kernel mounts the old one
        if "ready" in kaggle("datasets", "status", ds, check=False).lower():
            return
        time.sleep(10)
    say("  warning: dataset not reported ready after 10 min; pushing the kernel anyway")


def push_kernel(job: str) -> None:
    ds, kn = slugs(job)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "run.py").write_text(KERNEL_SCRIPTS[job].lstrip(), encoding="utf-8")
        (d / "kernel-metadata.json").write_text(json.dumps({
            "id": kn, "title": f"heritage-{job}-run", "code_file": "run.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
            "dataset_sources": [ds], "machine_shape": "NvidiaTeslaT4" if job == "music" else "NvidiaTeslaT4Highmem",
        }), encoding="utf-8")
        say(f"  pushing kernel {kn}")
        say("  " + kaggle("kernels", "push", "-p", str(d)).strip().replace("\n", "\n  "))


def status(job: str) -> str:
    # Parse only Kaggle's status field: a transient network message containing "error" is not a failed kernel.
    import re
    out = kaggle("kernels", "status", slugs(job)[1], check=False)
    m = re.search(r'status "(?:KernelWorkerStatus\.)?([A-Za-z_]+)"', out)
    return m.group(1).lower().replace("cancel_acknowledged", "cancel") if m else "unknown"


def wait(job: str, timeout_min: int) -> str:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_min * 60:
        st = status(job)
        if st != last:
            say(f"  [{(time.time() - t0) / 60:4.1f} min] {st}")
            last = st
        if st in ("complete", "error", "cancel"):
            return st
        time.sleep(30)
    return "timeout"


def pull(job: str) -> None:
    _, kn = slugs(job)
    dest = OUT / ("music" if job == "music" else "shots") / "_kaggle_output"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    kaggle("kernels", "output", kn, "-p", str(dest))
    say(f"  downloaded output to {dest.relative_to(ROOT)}")
    zips = list(dest.rglob("music.zip" if job == "music" else "clips.zip"))
    if not zips:
        logs = [p for p in dest.rglob("*") if p.suffix in (".log", ".txt")]
        raise SystemExit(f"no result zip in the kernel output; read the logs: {[str(p) for p in logs]}")
    if job == "music":
        from pipeline.music import import_candidates
        import_candidates(zips[0])
    else:
        from pipeline.shots import import_clips
        import_clips(zips[0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["music", "shots", "status", "pull"])
    ap.add_argument("job", nargs="?", choices=["music", "shots"])
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--attach", action="store_true", help="do not upload or push; wait for the current run, then pull")
    ap.add_argument("--timeout", type=int, default=180, help="minutes to wait for the kernel")
    a = ap.parse_args()

    if a.cmd == "status":
        print(status(a.job or "music"))
        return
    if a.cmd == "pull":
        pull(a.job or "music")
        return

    job = a.cmd
    if a.attach:
        st = wait(job, a.timeout)
        say(f"  kernel ended with '{st}'")
        pull(job)
        return
    sb = load_storyboard()
    if job == "music":
        from pipeline.music import prepare
        prepare(sb)
        files = {"music_job.json": OUT / "music" / "music_job.json", "acestep_music.py": KAGGLE_DIR / "acestep_music.py"}
    else:
        from pipeline.shots import BUNDLE, prepare
        prepare(sb)
        if not BUNDLE.exists():
            say("nothing to render")
            return
        tmp = OUT / "shots" / "_bundle"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(BUNDLE).extractall(tmp)
        files = {p.name: p for p in tmp.iterdir()} | {"wan22_i2v.py": KAGGLE_DIR / "wan22_i2v.py"}
    say(f"[kaggle] {job}")
    upload_dataset(job, files)
    push_kernel(job)
    if a.no_wait:
        say(f"  running; check with: python -m pipeline.kaggle_run status {job}")
        return
    st = wait(job, a.timeout)
    if st != "complete":
        say(f"  kernel ended with '{st}'; fetching logs")
    pull(job)


if __name__ == "__main__":
    main()
