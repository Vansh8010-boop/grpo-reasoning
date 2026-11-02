# GRPO Reasoning

Teaching Qwen2.5-1.5B-Instruct to solve math problems better with GRPO
(Group Relative Policy Optimization), implemented from scratch in PyTorch with LoRA.

Status: week 5 done. GRPO raised Qwen2.5-0.5B's GSM8K test accuracy from 49.1% to 53.3% (paired p = 0.001); on 1.5B it did not move GSM8K test (75.8% vs 75.7%), see [docs/week4.md](docs/week4.md). Ablations and analysis: [docs/week5.md](docs/week5.md). Earlier: [week 1](docs/week1.md), [week 2](docs/week2.md), [week 3](docs/week3.md).

| Model | GSM8K test | MATH-500 | SVAMP | Avg response length |
|---|---|---|---|---|
| Qwen2.5-0.5B-Instruct (base) | 49.1% | 33.2% | 61.6% | 317 tokens (GSM8K) |
| + GRPO, 250 steps (this repo) | **53.3%** | – | 63.7% | 301 tokens (GSM8K) |
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
