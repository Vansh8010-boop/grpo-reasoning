# GRPO Reasoning

Teaching Qwen2.5-1.5B-Instruct to solve math problems better with GRPO
(Group Relative Policy Optimization), implemented from scratch in PyTorch with LoRA.

Status: setup (week 0). The results table goes here once there are numbers.

| Model | GSM8K test | MATH-500 | SVAMP | Avg response length |
|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct (base) | – | – | – | – |
| + GRPO (this repo) | – | – | – | – |

## Layout

```
grpo/      rollout, rewards, advantages, loss, training loop
eval/      evaluation harness and answer parsing
configs/   one YAML per experiment
analysis/  notebooks: reward hacking, length, behaviors
results/   eval JSON per checkpoint
site/      project website
tests/     unit tests (answer parser, advantages, loss)
kaggle/    Kaggle notebooks that clone this repo and run on GPU
```

## Local setup (Windows)

```
py -3.11 -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\pip install -r requirements.txt
```

vLLM has no Windows build; it is installed only on Kaggle / Linux GPUs.
