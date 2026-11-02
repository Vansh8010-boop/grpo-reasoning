"""Ablation curves: validation accuracy over training, one panel per experiment, each against the baseline.

  python -m analysis.plot_ablations --out analysis/plots/week5-ablations.png
"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASELINE = ("grpo-0.5b", "baseline: G=8, KL 0.04, format on, std")
PANELS = [
    ("Group size (128 answers per step)", [("abl-g4", "G=4 x 32 problems"), ("abl-g16", "G=16 x 8 problems")]),
    ("KL coefficient", [("abl-kl0", "KL 0"), ("abl-kl001", "KL 0.01")]),
    ("Format reward", [("abl-nofmt", "format reward off")]),
    ("Advantage normalization", [("abl-meanonly", "mean only (no / std)")]),
]


def val_curve(run, root):
    rows = {}
    for line in open(os.path.join(root, run, "metrics.jsonl")):
        r = json.loads(line)
        if "val_accuracy" in r:
            rows[r["step"]] = 100 * r["val_accuracy"]
    steps = sorted(rows)
    return steps, [rows[s] for s in steps]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="results/train")
    p.add_argument("--test-root", default="results/ablations")
    p.add_argument("--base-summary", default="results/base-0.5b/summary.json")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.2), sharey=True)
    for ax, (title, runs) in zip(axes, PANELS):
        for run, label in [BASELINE] + runs:
            xs, ys = val_curve(run, a.root)
            ax.plot(xs, ys, marker="o", label=label, color="black" if run == BASELINE[0] else None,
                    linestyle="--" if run == BASELINE[0] else "-")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("step")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="lower right")
    axes[0].set_ylabel("validation accuracy (%)\n500 GSM8K train-split problems, greedy")
    fig.suptitle("GRPO ablations on Qwen2.5-0.5B (one change at a time; each point has ~2 pts standard error)", fontsize=11)
    fig.tight_layout()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.savefig(a.out, dpi=120)
    print("wrote", a.out)

    # Final (step 250) checkpoints on GSM8K test, the number that matters.
    runs = [BASELINE] + [r for _, rs in PANELS for r in rs] + [("grpo-0.5b-lr3e-5", "lr 3e-5 (collapsed)")]
    accs = []
    for run, _ in runs:
        s = json.load(open(os.path.join(a.test_root, run, "summary.json")))["datasets"]["gsm8k"]
        accs.append(100 * s["accuracy"])
    base = 100 * json.load(open(a.base_summary))["datasets"]["gsm8k"]["accuracy"]
    fig, ax = plt.subplots(figsize=(11, 4))
    bars = ax.bar(range(len(runs)), accs, color=["black"] + ["C0"] * (len(runs) - 2) + ["C3"])
    ax.bar_label(bars, fmt="%.1f", fontsize=8)
    ax.axhline(base, color="gray", linestyle="--", label=f"base model {base:.1f}%")
    ax.set_xticks(range(len(runs)), [label.split(":")[0] for _, label in runs], rotation=20, ha="right", fontsize=8)
    ax.set_ylim(40, 60)
    ax.set_ylabel("GSM8K test accuracy (%)")
    ax.set_title("Final checkpoints (step 250) on GSM8K test, greedy, 1,024 tokens (standard error ~1.4 pts)", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = a.out.replace(".png", "-test.png")
    fig.savefig(out, dpi=120)
    print("wrote", out)


if __name__ == "__main__":
    main()
