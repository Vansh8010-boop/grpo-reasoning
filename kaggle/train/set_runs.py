"""Set which training commands the Kaggle notebook runs: python kaggle/train/set_runs.py '<args>' ['<args>' ...]"""
import json
import shlex
import sys

p = "kaggle/train/train.ipynb"
nb = json.load(open(p, encoding="utf-8"))
runs = [shlex.split(a) + ["out_dir=/kaggle/working/checkpoints"] for a in sys.argv[1:]]
nb["cells"][-1]["source"] = [
    f"RUNS = {json.dumps(runs)}\n",
    "env = {**os.environ, \"HF_HUB_DISABLE_PROGRESS_BARS\": \"1\", \"CUDA_VISIBLE_DEVICES\": \"0\"}\n",
    "for i, args in enumerate(RUNS):\n",
    "    path = f\"/kaggle/working/train-{i}.log\"\n",
    "    code = subprocess.run([\"python\", \"-m\", \"grpo.train\", *args], env=env, stdout=open(path, \"w\"), stderr=subprocess.STDOUT).returncode\n",
    "    print(\" \".join(args), \"-> exit code\", code)\n",
    "    print(\"\".join(l for l in open(path) if l.startswith((\"step\", \"resumed\", \"trainable\", \"non-finite\")) or \"Error\" in l)[-6000:])\n",
    "    if code:\n",
    "        break\n",
]
json.dump(nb, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(nb["cells"][-1]["source"][0])
