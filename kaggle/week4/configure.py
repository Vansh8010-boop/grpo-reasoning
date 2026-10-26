"""Configure the week 4 notebook: python kaggle/week4/configure.py --solve-rates yes|no [--train '<grpo.train args>']"""
import argparse
import json
import shlex

p = argparse.ArgumentParser()
p.add_argument("--solve-rates", choices=["yes", "no"], required=True)
p.add_argument("--train", default="")
a = p.parse_args()
path = "kaggle/week4/week4.ipynb"
nb = json.load(open(path, encoding="utf-8"))
nb["cells"][3]["source"][0] = f"DO_SOLVE_RATES = {a.solve_rates == 'yes'}\n"
args = shlex.split(a.train)
if args:
    args += ([] if "--set" in args else ["--set"]) + ["out_dir=/kaggle/working/checkpoints"]
nb["cells"][4]["source"][0] = f"TRAIN_ARGS = {json.dumps(args)}\n"
json.dump(nb, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(nb["cells"][3]["source"][0] + nb["cells"][4]["source"][0])
