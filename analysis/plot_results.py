"""Before/after plots from evaluation results: accuracy per dataset (grouped bars) and GSM8K test
accuracy by difficulty (number of steps in the reference solution).

  python -m analysis.plot_results --base results/base-1.5b-rerun --trained results/grpo-1.5b-step350 --out analysis/plots/week4-before-after.png
"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from eval.data import load_gsm8k  # noqa: E402

DATASETS = [("gsm8k", "GSM8K test"), ("math500", "MATH-500"), ("svamp", "SVAMP")]
BUCKETS = [(1, 2), (3, 4), (5, 6), (7, 99)]


def load(run, ds):
    return {r["id"]: r["correct"] for r in map(json.loads, open(os.path.join(run, f"{ds}.jsonl"), encoding="utf-8"))}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--trained", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    w = 0.38
    for k, (run, label) in enumerate(((a.base, "base"), (a.trained, "GRPO"))):
        accs = [100 * sum(load(run, ds).values()) / len(load(run, ds)) for ds, _ in DATASETS]
        bars = ax1.bar([i + (k - 0.5) * w for i in range(len(DATASETS))], accs, w, label=label)
        ax1.bar_label(bars, fmt="%.1f", fontsize=8)
    ax1.set_xticks(range(len(DATASETS)), [n for _, n in DATASETS])
    ax1.set_ylabel("accuracy (%)")
    ax1.set_ylim(0, 100)
    ax1.set_title("Accuracy per dataset (greedy, 1,024 tokens)", fontsize=10)
    ax1.legend()

    steps = {q["id"]: q["meta"]["n_steps"] for q in load_gsm8k("test")}
    labels = [f"{lo}-{hi}" if hi < 99 else f"{lo}+" for lo, hi in BUCKETS]
    for k, (run, label) in enumerate(((a.base, "base"), (a.trained, "GRPO"))):
        res = load(run, "gsm8k")
        accs, ns = [], []
        for lo, hi in BUCKETS:
            ids = [i for i in res if lo <= steps[i] <= hi]
            accs.append(100 * sum(res[i] for i in ids) / len(ids))
            ns.append(len(ids))
        bars = ax2.bar([i + (k - 0.5) * w for i in range(len(BUCKETS))], accs, w, label=label)
        ax2.bar_label(bars, fmt="%.1f", fontsize=8)
    ax2.set_xticks(range(len(BUCKETS)), [f"{l} steps\n(n={n})" for l, n in zip(labels, ns)])
    ax2.set_ylim(0, 100)
    ax2.set_title("GSM8K test accuracy by solution length", fontsize=10)
    ax2.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.savefig(a.out, dpi=120)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
