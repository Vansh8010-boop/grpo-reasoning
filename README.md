# GRPO Reasoning

Teaching Qwen2.5-1.5B-Instruct to solve math problems better with GRPO
(Group Relative Policy Optimization), implemented from scratch in PyTorch with LoRA.

Status: week 1 done (evaluation harness and baselines, see [docs/week1.md](docs/week1.md)).

| Model | GSM8K test | MATH-500 | SVAMP | Avg response length |
|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct (base) | 75.8% | 55.8% | 83.2% | 303 tokens (GSM8K) |
| + GRPO (this repo) | – | – | – | – |

## Reproduce the evaluation

```
python -m eval.harness --model Qwen/Qwen2.5-1.5B-Instruct --dtype float16 --out results/base-1.5b
python -m pytest -q tests/
```

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
