"""Compare training runs: validation accuracy at each evaluation, and training statistics
averaged over the last 50 steps.

  python -m analysis.compare_runs results/train/grpo-0.5b results/train/abl-kl0 results/train/abl-kl001
"""
import argparse
import json
import os

KEYS = [("accuracy", "train acc", "{:.3f}"), ("format_rate", "format", "{:.3f}"), ("avg_tokens", "tokens", "{:.0f}"),
        ("truncated", "trunc", "{:.3f}"), ("kl", "KL", "{:.4f}"), ("garbage_rate", "garbage", "{:.3f}"),
        ("self_check_rate", "self-check", "{:.3f}")]


def load(run_dir):
    rows = {}
    for line in open(os.path.join(run_dir, "metrics.jsonl")):
        r = json.loads(line)
        rows.setdefault(r["step"], {}).update(r)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+")
    p.add_argument("--window", type=int, default=50, help="average training stats over the last N steps")
    a = p.parse_args(argv)

    data = {os.path.basename(os.path.normpath(r)): load(r) for r in a.runs}
    steps = sorted({s for rows in data.values() for s, r in rows.items() if "val_accuracy" in r})
    print("| run | " + " | ".join(f"val @{s}" for s in steps) + " | best |")
    print("|---|" + "---|" * (len(steps) + 1))
    for name, rows in data.items():
        vals = [rows.get(s, {}).get("val_accuracy") for s in steps]
        best = max((v, s) for v, s in zip(vals, steps) if v is not None)
        print(f"| {name} | " + " | ".join("-" if v is None else f"{100 * v:.1f}" for v in vals)
              + f" | {100 * best[0]:.1f} (step {best[1]}) |")
    print(f"\nTraining statistics, mean over the last {a.window} steps:\n")
    print("| run | " + " | ".join(label for _, label, _ in KEYS) + " |")
    print("|---|" + "---|" * len(KEYS))
    for name, rows in data.items():
        tail = [rows[s] for s in sorted(rows) if s > 0][-a.window :]
        cells = []
        for key, _, fmt in KEYS:
            xs = [r[key] for r in tail if key in r]
            cells.append(fmt.format(sum(xs) / len(xs)) if xs else "-")
        print(f"| {name} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
