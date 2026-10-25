"""Set which training commands the Kaggle notebook runs, one per GPU, in parallel:

  python kaggle/train/set_runs.py '<args for GPU 0>' ['<args for GPU 1>']
"""
import json
import shlex
import sys

p = "kaggle/train/train.ipynb"
nb = json.load(open(p, encoding="utf-8"))
runs = [shlex.split(a) for a in sys.argv[1:]]
for r in runs:  # out_dir must sit inside the (single) --set list
    r += ([] if "--set" in r else ["--set"]) + ["out_dir=/kaggle/working/checkpoints"]
assert 1 <= len(runs) <= 2, "Kaggle gives two GPUs"
nb["cells"][-1]["source"] = [
    f"RUNS = {json.dumps(runs)}\n",
    "env = {**os.environ, \"HF_HUB_DISABLE_PROGRESS_BARS\": \"1\"}\n",
    "procs = []\n",
    "for gpu, args in enumerate(RUNS):\n",
    "    path = f\"/kaggle/working/train-{gpu}.log\"\n",
    "    p = subprocess.Popen([\"python\", \"-m\", \"grpo.train\", *args], env={**env, \"CUDA_VISIBLE_DEVICES\": str(gpu)},\n",
    "                         stdout=open(path, \"w\"), stderr=subprocess.STDOUT)\n",
    "    procs.append((args, path, p))\n",
    "for args, path, p in procs:\n",
    "    print(\" \".join(args), \"-> exit code\", p.wait())\n",
    "    print(\"\".join(l for l in open(path) if l.startswith((\"step\", \"resumed\", \"trainable\", \"non-finite\")) or \"Error\" in l)[-8000:])\n",
]
json.dump(nb, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(nb["cells"][-1]["source"][0])
