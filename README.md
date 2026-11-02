# GRPO From Scratch

GRPO (Group Relative Policy Optimization, the RL method behind DeepSeek-R1) implemented from scratch
in PyTorch with LoRA, used to train Qwen2.5-Instruct models on grade-school math with an exact-answer reward.
Everything ran on Kaggle's free T4 GPUs.

**Results:** GRPO raised Qwen2.5-0.5B-Instruct's GSM8K test accuracy from **49.1% to 53.3%**
(153 problems fixed, 98 broken, paired sign test p = 0.001). On Qwen2.5-1.5B-Instruct it did **not** move
GSM8K test (75.8% → 75.7%), although held-out validation rose 5 points; the write-up explains why
(most likely contamination of GSM8K's training split).

| Model | GSM8K test | MATH-500 | SVAMP | Avg response length (GSM8K) |
|---|---|---|---|---|
| Qwen2.5-0.5B-Instruct (base) | 49.1% | 33.2% | 61.6% | 317 tokens |
| + GRPO, 250 steps (this repo) | **53.3%** | – | 63.7% | 301 tokens |
| Qwen2.5-1.5B-Instruct (base) | 75.8% | 56.4% | 83.4% | 303 tokens |
| + GRPO, step 350 of 500 (this repo) | 75.7% | 56.8% | 85.3% | 299 tokens |

Greedy decoding, 1,024 new tokens, vLLM fp16, identical prompt and answer parser before and after.

- **Write-up:** [docs/report.md](docs/report.md) (method, results, ablations, what didn't work)
- **Website:** `site/` (before/after explorer, training curves, ablations, reward-hacking gallery)
- **Model:** the 0.5B LoRA adapter and model card are in [release/](release/)
- **Weekly notes:** [week 1](docs/week1.md) evaluation and baselines · [week 2](docs/week2.md) rewards and rollouts ·
  [week 3](docs/week3.md) GRPO on 0.5B · [week 4](docs/week4.md) 1.5B main run · [week 5](docs/week5.md) ablations and analysis

## Reproduce

```
python -m pytest -q tests/                                     # answer parser, rewards, advantages, loss

# evaluation (vLLM, Linux GPU)
python -m eval.harness --model Qwen/Qwen2.5-0.5B-Instruct --dtype float16 --out results/base-0.5b
python -m eval.harness --model Qwen/Qwen2.5-0.5B-Instruct --dtype float16 \
    --adapter checkpoints/grpo-0.5b/ckpt-0250 --out results/grpo-0.5b

# training
python -m grpo.train --config configs/grpo-0.5b.yaml          # 250 steps, ~6.5 h on one T4
python -m grpo.train --config configs/grpo-1.5b.yaml          # 500 steps, two T4s (train + vLLM), ~13 h
python -m grpo.train --config configs/abl-kl0.yaml            # any ablation: configs/abl-*.yaml

# figures and website data
python analysis/plot_training.py results/train/grpo-0.5b --out analysis/plots/run.png
python -m analysis.plot_ablations --out analysis/plots/week5-ablations.png
python site/build_data.py
```

Every reported experiment has a config in `configs/`; the Kaggle notebooks that ran them are in `kaggle/`.

## Layout

```
grpo/      rollout (HF and vLLM), rewards, advantages, loss, training loop, solve-rate filter
eval/      evaluation harness, answer parsing, datasets, prompt
configs/   one YAML per experiment
analysis/  plots, reward-hacking screen, run comparisons, side-by-side examples
results/   evaluation outputs, training metrics, validation and sample dumps
site/      project website (static; reads site/data/*.json)
release/   model card and Hugging Face upload script
tests/     unit tests (CI runs them on every push)
kaggle/    Kaggle notebooks that clone this repo and run on GPU
docs/      weekly notes and the write-up
```

## Local setup (Windows)

```
py -3.11 -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\pip install -r requirements.txt
```

vLLM has no Windows build; it is installed only on Kaggle / Linux GPUs.
