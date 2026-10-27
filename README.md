# GRPO Reasoning

Teaching Qwen2.5-1.5B-Instruct to solve math problems better with GRPO
(Group Relative Policy Optimization), implemented from scratch in PyTorch with LoRA.

Status: week 4 done. The 1.5B GRPO run did **not** improve GSM8K test accuracy (75.8% → 75.7%) although held-out validation rose 83.4% → 88.4%; [docs/week4.md](docs/week4.md) explains why. Earlier: [week 1](docs/week1.md), [week 2](docs/week2.md), [week 3](docs/week3.md).

| Model | GSM8K test | MATH-500 | SVAMP | Avg response length |
|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct (base, re-scored with the trained model) | 75.8% | 56.4% | 83.4% | 303 tokens (GSM8K) |
| + GRPO, step 350 (this repo) | 75.7% | 56.8% | 85.3% | 299 tokens (GSM8K) |

## Reproduce the evaluation

```
python -m eval.harness --model Qwen/Qwen2.5-1.5B-Instruct --dtype float16 --out results/base-1.5b
python -m pytest -q tests/
```

## Reproduce training

```
python -m grpo.train --config configs/grpo-0.5b.yaml          # 250 steps, ~6.5 h on a T4
python -m grpo.train --config configs/grpo-1.5b.yaml          # 500 steps, two T4s (train + vLLM), ~12 h
python analysis/plot_training.py checkpoints/grpo-0.5b --out analysis/plots/run.png
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
