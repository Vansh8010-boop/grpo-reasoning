"""Training curves for one or more runs: reward, validation accuracy, KL, response length, self-check rate.

  python analysis/plot_training.py results/train/grpo-0.5b results/train/grpo-0.5b-lr3e-5 --out analysis/plots/week3.png

Each run directory needs a metrics.jsonl written by grpo/train.py.
"""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load(run_dir):
    rows = [json.loads(l) for l in open(os.path.join(run_dir, "metrics.jsonl"))]
    by_step = {}
    for r in rows:  # a resumed run may log a step twice; keep the last
        by_step.setdefault(r["step"], {}).update(r)
    return [by_step[s] for s in sorted(by_step)]


def smooth(xs, k=10):
    out = []
    for i in range(len(xs)):
        w = xs[max(0, i - k + 1) : i + 1]
        out.append(sum(w) / len(w))
    return out


PANELS = [
    ("reward", "training reward (mean, 10-step avg)", True),
    ("val_accuracy", "validation accuracy (500 GSM8K train problems, greedy)", False),
    ("kl", "KL to reference (10-step avg)", True),
    ("avg_tokens", "response length, tokens (10-step avg)", True),
    ("self_check_rate", "answers with self-check phrases (10-step avg)", True),
    ("groups_mixed", "groups with mixed correctness (10-step avg)", True),
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for run in a.runs:
        rows = load(run)
        name = os.path.basename(os.path.normpath(run))
        for ax, (key, title, do_smooth) in zip(axes.flat, PANELS):
            pts = [(r["step"], r[key]) for r in rows if key in r]
            if not pts:
                continue
            xs, ys = zip(*pts)
            ax.plot(xs, smooth(list(ys)) if do_smooth else ys, marker=None if do_smooth else "o", label=name)
            ax.set_title(title, fontsize=10)
            ax.set_xlabel("step")
            ax.grid(alpha=0.3)
    axes.flat[0].legend(fontsize=8)
    fig.tight_layout()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.savefig(a.out, dpi=120)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
