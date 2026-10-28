"""Side-by-side answers for problems where base and trained models disagree (GSM8K test).

  python -m analysis.examples --base results/base-1.5b-rerun --trained results/grpo-1.5b-step350 --out analysis/examples-1.5b.md

Picks n problems the trained model fixed and n it broke (random, seeded): on GSM8K test both
happened about equally often, so showing only fixes would mislead.
"""
import argparse
import json
import os
import random


def load(run):
    return {r["id"]: r for r in map(json.loads, open(os.path.join(run, "gsm8k.jsonl"), encoding="utf-8"))}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--trained", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("-n", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)

    b, t = load(a.base), load(a.trained)
    fixed = sorted(i for i in b if t[i]["correct"] and not b[i]["correct"])
    broke = sorted(i for i in b if b[i]["correct"] and not t[i]["correct"])
    rng = random.Random(a.seed)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"# Base vs GRPO on GSM8K test\n\nThe trained model fixed {len(fixed)} problems and broke {len(broke)}. "
                f"{a.n} random examples of each.\n\n")
        for title, ids in ((f"Fixed by GRPO ({len(fixed)} total)", fixed), (f"Broken by GRPO ({len(broke)} total)", broke)):
            f.write(f"## {title}\n\n")
            for i in rng.sample(ids, min(a.n, len(ids))):
                f.write(f"### {i} (gold {b[i]['gold']})\n\n{b[i]['question']}\n\n")
                for name, r in (("Base", b[i]), ("GRPO", t[i])):
                    s = r["samples"][0]
                    mark = "right" if r["correct"] else "wrong"
                    f.write(f"**{name}: {s['pred']} ({mark})**\n\n```\n{s['response'].strip()}\n```\n\n")
    print(f"wrote {a.out}: {len(fixed)} fixed, {len(broke)} broke")


if __name__ == "__main__":
    main()
