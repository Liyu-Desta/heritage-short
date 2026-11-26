"""Summarise runs.jsonl per stage and model: calls, failures, latency, GPU minutes,
list-price equivalent. Paste the output into COSTS.md, or use --write.

    python -m pipeline.report [--write]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict

from pipeline.common import ROOT, RUNS

BEGIN, END = "<!-- report:begin -->", "<!-- report:end -->"


def table() -> str:
    rows = [json.loads(l) for l in RUNS.read_text(encoding="utf-8").splitlines() if l.strip()] if RUNS.exists() else []
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("stage", "?"), r.get("model", "?"))].append(r)
    out = ["| stage | model | calls | ok | failed | median latency s | max s | total s | GPU min | list-price equiv. USD |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for (stage, model), rs in sorted(groups.items()):
        lat = [r.get("latency_s", 0) for r in rs]
        ok = sum(r.get("status") == "ok" for r in rs)
        gpu = sum(r.get("gpu_s", 0) or 0 for r in rs) / 60
        prices = [r.get("list_price_usd") for r in rs if r.get("status") == "ok"]
        price = f"{sum(p for p in prices if p):.4f}" if prices and all(p is not None for p in prices) else "n/a"
        out.append(f"| {stage} | {model} | {len(rs)} | {ok} | {len(rs) - ok} | {statistics.median(lat):.1f} | "
                   f"{max(lat):.1f} | {sum(lat):.0f} | {gpu:.1f} | {price} |")
    out.append(f"\n{len(rows)} logged calls in total.")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="replace the generated block in COSTS.md")
    a = ap.parse_args()
    t = table()
    print(t)
    if a.write:
        p = ROOT / "COSTS.md"
        doc = p.read_text(encoding="utf-8")
        start, end = doc.index(BEGIN) + len(BEGIN), doc.index(END)
        p.write_text(doc[:start] + "\n" + t + "\n" + doc[end:], encoding="utf-8")
        print("updated COSTS.md")
