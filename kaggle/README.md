# Running the GPU stages on Kaggle

Wan 2.2 and ACE-Step need a GPU, so they run in a Kaggle notebook. Your machine
prepares the jobs and imports the results. The storyboard stays the single source of truth.

## One-time setup
1. Verify your phone number on Kaggle (this unlocks GPUs, about 30 h/week).
2. Create a notebook and set **Accelerator → GPU T4 ×2** and **Internet → On**.
3. Upload this `kaggle/` folder as a Kaggle dataset named `heritage-code`.

## Moving shots (Wan 2.2 TI2V-5B)
```bash
python -m pipeline.keyframes          # make sure keyframes exist
python -m pipeline.shots prepare      # -> outputs/shots/kaggle_bundle.zip (only changed shots)
```
Upload `kaggle_bundle.zip` as a new version of a dataset named `heritage-shots`, attach it to the notebook, then run:

```python
!pip install -q -U diffusers transformers accelerate ftfy imageio imageio-ffmpeg
# one worker per T4; the first one runs in the background
!nohup python /kaggle/input/heritage-code/wan22_i2v.py --bundle /kaggle/input/heritage-shots --gpu 0 --of 2 > log0.txt 2>&1 &
!python /kaggle/input/heritage-code/wan22_i2v.py --bundle /kaggle/input/heritage-shots --gpu 1 --of 2 2>&1 | tee log1.txt
!sleep 30; tail -n 5 log0.txt   # wait until worker 0 has finished too
!cd /kaggle/working && cat clips/wan_runs_gpu*.jsonl > clips/wan_runs.jsonl && zip -r clips.zip clips
```
Download `clips.zip` from the Output panel, then:
```bash
python -m pipeline.shots import path/to/clips.zip
python -m pipeline.shots status
```

**Budget:** draft at `WAN_SIZE=832*480` with `WAN_STEPS=30`. Re-render only your best shots at `1280*704`.
GPU seconds per clip are logged as `gpu_s`, and `python -m pipeline.report` adds them up.

## Score (ACE-Step)
```bash
python -m pipeline.music prepare      # -> outputs/music/music_job.json
```
Upload `music_job.json` to a dataset called `heritage-music`, then in a notebook:
```python
!git clone https://github.com/ace-step/ACE-Step-1.5 acestep && pip install -q -e acestep
!python /kaggle/input/heritage-code/acestep_music.py --job /kaggle/input/heritage-music/music_job.json
!cd /kaggle/working && zip -r music.zip music
```
Check the repository URL and install steps against the current ACE-Step README. Then:
```bash
python -m pipeline.music import path/to/music.zip
# listen to c1..c3, write down why you chose one in EXPERIMENTS.md, then set
# "selected": "c2" under "music" in storyboard.json
```

If Kaggle is unavailable or your quota runs out, the same scripts run in Colab: change `--bundle`/`--out` to `/content/...`.
If you get no clips at all, the film still renders: `assemble` animates each keyframe with a pan-and-zoom.
