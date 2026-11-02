"""Build the website's data files from results/ (run from the repo root after any new result).

  python site/build_data.py

Writes site/data/{summary,explorer,training,ablations,gallery}.json. The site reads only these.
"""
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
from grpo.train import NON_MATH  # noqa: E402

OUT = "site/data"


def jl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def by_id(path):
    return {r["id"]: r for r in jl(path)}


def sign_p(g, l):
    n, k = g + l, min(g, l)
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0


def compare(base_path, trained_path):
    b, t = by_id(base_path), by_id(trained_path)
    g = sum(bool(t[i]["correct"]) and not b[i]["correct"] for i in b)
    l = sum(bool(b[i]["correct"]) and not t[i]["correct"] for i in b)
    acc = lambda d: round(100 * sum(bool(r["correct"]) for r in d.values()) / len(d), 1)
    return {"base": acc(b), "trained": acc(t), "fixed": g, "broken": l, "p": round(sign_p(g, l), 4), "n": len(b)}


def metrics(run, every=5):
    rows = {}
    for r in jl(f"results/train/{run}/metrics.jsonl"):
        rows.setdefault(r["step"], {}).update(r)
    steps = sorted(s for s in rows if s > 0)
    out = {"step": [], "reward": [], "kl": [], "avg_tokens": [], "garbage_rate": [], "self_check_rate": [], "accuracy": []}
    for k in range(0, len(steps), every):  # mean over blocks of `every` steps
        block = [rows[s] for s in steps[k : k + every]]
        out["step"].append(block[-1]["step"])
        for key in list(out)[1:]:
            xs = [r[key] for r in block if key in r]
            out[key].append(round(sum(xs) / len(xs), 5) if xs else None)
    val = {s: round(100 * rows[s]["val_accuracy"], 1) for s in sorted(rows) if "val_accuracy" in rows[s]}
    out["val_step"], out["val"] = list(val), list(val.values())
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {
        "0.5b": {ds: compare(f"results/base-0.5b/{ds}.jsonl", f"results/ablations/grpo-0.5b/{ds}.jsonl") for ds in ("gsm8k", "svamp")},
        "1.5b": {ds: compare(f"results/base-1.5b-rerun/{ds}.jsonl", f"results/grpo-1.5b-step350/{ds}.jsonl")
                 for ds in ("gsm8k", "math500", "svamp")},
    }
    json.dump(summary, open(f"{OUT}/summary.json", "w"), indent=1)

    # Before/after explorer: 0.5B on GSM8K test. Mostly fixes, some breaks, so it does not oversell.
    b, t = by_id("results/base-0.5b/gsm8k.jsonl"), by_id("results/ablations/grpo-0.5b/gsm8k.jsonl")
    short = lambda i: len(b[i]["samples"][0]["response"]) < 1500 and len(t[i]["samples"][0]["response"]) < 1500
    fixed = sorted(i for i in b if t[i]["correct"] and not b[i]["correct"] and short(i))
    broke = sorted(i for i in b if b[i]["correct"] and not t[i]["correct"] and short(i))
    rng = random.Random(0)
    picks = [(i, "fixed") for i in rng.sample(fixed, 12)] + [(i, "broken") for i in rng.sample(broke, 4)]
    explorer = []
    for i, kind in picks:
        side = lambda r: {"answer": r["samples"][0]["pred"], "correct": bool(r["correct"]), "response": r["samples"][0]["response"].strip()}
        explorer.append({"id": i, "kind": kind, "question": b[i]["question"], "gold": b[i]["gold"], "base": side(b[i]), "grpo": side(t[i])})
    json.dump(explorer, open(f"{OUT}/explorer.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    training = {run: metrics(run) for run in ("grpo-0.5b", "grpo-0.5b-lr3e-5", "grpo-1.5b")}
    json.dump(training, open(f"{OUT}/training.json", "w"))

    labels = {"grpo-0.5b": "Baseline (G=8, KL 0.04, format on, std)", "abl-g4": "Group size 4 (x 32 problems)",
              "abl-g16": "Group size 16 (x 8 problems)", "abl-kl0": "No KL penalty", "abl-kl001": "KL 0.01",
              "abl-nofmt": "Format reward off", "abl-meanonly": "Mean-only advantages", "grpo-0.5b-lr3e-5": "Learning rate 3e-5 (collapsed)"}
    ablations = []
    for run, label in labels.items():
        c = compare("results/base-0.5b/gsm8k.jsonl", f"results/ablations/{run}/gsm8k.jsonl")
        v = metrics(run)
        ablations.append({"run": run, "label": label, "test": c["trained"], "fixed": c["fixed"], "broken": c["broken"],
                          "p": c["p"], "val_step": v["val_step"], "val": v["val"]})
    json.dump({"base_test": summary["0.5b"]["gsm8k"]["base"], "runs": ablations}, open(f"{OUT}/ablations.json", "w"), indent=1)

    # Gallery: the questionable high-reward answers found by analysis/reward_hacking.py, and a collapsed answer.
    flagged = jl("analysis/reward_hacking/flagged.jsonl")
    pick = lambda run, pid: next(x for x in flagged if x["run"] == run and x["id"] == pid)
    gallery = [
        {"title": "Right answer, wrong reasoning", "note": "The working ends at x = 12, then the model boxes 13, which happens to be the correct answer. "
         "An exact-answer reward cannot tell. The base model has likely seen GSM8K's training split, so it may simply remember this one.",
         "run": "1.5B, step 50", **{k: pick("grpo-1.5b", "gsm8k-train-7353")[k] for k in ("gold", "response")}},
        {"title": "Garbled reasoning, full reward", "note": "The explanation dissolves into word salad, but the boxed 17 is right, so it earned the full reward. "
         "Rare: 2 of 1,297 high-reward answers looked questionable, and garbled answers were almost always wrong (2 of 59).",
         "run": "1.5B, step 350", **{k: pick("grpo-1.5b", "gsm8k-train-3337")[k] for k in ("gold", "response")}},
    ]
    collapsed = [x for x in jl("results/train/grpo-0.5b-lr3e-5/samples-0200.jsonl") if len(NON_MATH.findall(x["response"])) > 5]
    x = collapsed[0]
    gallery.append({"title": "Collapse: what training at lr 3e-5 produced", "note": "From about step 150, a growing share of sampled answers drifted into "
                    "random tokens and never recovered (33 of 128 at step 200). Greedy validation stayed around 66%, so only the sampled answers showed it. "
                    "These answers got about zero reward: the collapse was not reward hacking.",
                    "run": "0.5B, lr 3e-5, step 200", "gold": x["gold"], "response": x["response"]})
    json.dump(gallery, open(f"{OUT}/gallery.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for f in sorted(os.listdir(OUT)):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
