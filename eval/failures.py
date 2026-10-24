"""Dump a random sample of wrong answers as Markdown, for reading by hand.

  python -m eval.failures results/base-1.5b/gsm8k.jsonl -n 20 > analysis/failures-base-1.5b-gsm8k.md
"""
import argparse
import json
import random
import sys


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)

    with open(a.path, encoding="utf-8") as f:
        wrong = [r for r in map(json.loads, f) if r["correct"] == 0]
    picked = random.Random(a.seed).sample(wrong, min(a.n, len(wrong)))
    out = sys.stdout
    out.write(f"# {len(picked)} of {len(wrong)} failures from `{a.path}`\n\n")
    for k, r in enumerate(picked, 1):
        s = r["samples"][0]
        out.write(f"## {k}. {r['id']}\n\n**Question:** {r['question']}\n\n")
        out.write(f"**Gold:** `{r['gold']}` | **Parsed:** `{s['pred']}` (via {s['source']})"
                  f"{' | TRUNCATED' if s['truncated'] else ''}\n\n")
        out.write(f"**Response ({s['n_tokens']} tokens):**\n\n```\n{s['response'].strip()}\n```\n\n")
        out.write("**Failure type:** _(arithmetic / misread problem / wrong method / format / parser bug / other)_\n\n---\n\n")


if __name__ == "__main__":
    main()
