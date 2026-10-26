"""Configure the week 4 notebook.

  python kaggle/week4/configure.py --solve-rates no --train '<grpo.train args>' [--resume-run grpo-1.5b --resume-dataset vanshkulshrestha/grpo-1p5b-resume]
"""
import argparse
import json
import shlex

p = argparse.ArgumentParser()
p.add_argument("--solve-rates", choices=["yes", "no"], required=True)
p.add_argument("--train", default="")
p.add_argument("--resume-run", default="", help="run name whose checkpoint folder is in the attached dataset")
p.add_argument("--resume-dataset", default="", help="owner/slug of the Kaggle dataset holding that folder")
a = p.parse_args()

path = "kaggle/week4/week4.ipynb"
nb = json.load(open(path, encoding="utf-8"))
cell = {c["source"][0].split(" =")[0]: c for c in nb["cells"] if c["cell_type"] == "code" and " = " in c["source"][0]}
cell["DO_SOLVE_RATES"]["source"][0] = f"DO_SOLVE_RATES = {a.solve_rates == 'yes'}\n"
cell["RESUME_RUN"]["source"][0] = f"RESUME_RUN = {json.dumps(a.resume_run)}\n"
args = shlex.split(a.train)
if args:
    args += ([] if "--set" in args else ["--set"]) + ["out_dir=/kaggle/working/checkpoints"]
cell["TRAIN_ARGS"]["source"][0] = f"TRAIN_ARGS = {json.dumps(args)}\n"
json.dump(nb, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

meta_path = "kaggle/week4/kernel-metadata.json"
meta = json.load(open(meta_path))
meta["dataset_sources"] = [a.resume_dataset] if a.resume_dataset else []
json.dump(meta, open(meta_path, "w"), indent=2)
for k in ("DO_SOLVE_RATES", "RESUME_RUN", "TRAIN_ARGS"):
    print(cell[k]["source"][0].rstrip())
print("dataset_sources", meta["dataset_sources"])
