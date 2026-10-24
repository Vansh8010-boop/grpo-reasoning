# Week 1: evaluation harness and baselines

## Baseline results

Greedy decoding, max 1024 new tokens, one prompt template for every dataset
(`eval/prompt.py`), vLLM 0.32 in fp16 on a Kaggle T4. Raw responses are in
`results/base-*/`, 20 random failures per model and dataset in `analysis/failures/`.

| Model | GSM8K test (1,319) | MATH-500 (500) | SVAMP (1,000) |
|---|---|---|---|
| Qwen2.5-0.5B-Instruct | 49.1% | 33.2% | 61.6% |
| Qwen2.5-1.5B-Instruct | **75.8%** | 55.8% | 83.2% |

| Model | Dataset | `\boxed{}` used | Truncated at 1024 | Avg tokens |
|---|---|---|---|---|
| 0.5B | GSM8K | 97.2% | 1.4% | 317 |
| 0.5B | MATH-500 | 83.4% | 16.4% | 583 |
| 0.5B | SVAMP | 98.4% | 1.2% | 229 |
| 1.5B | GSM8K | 99.1% | 0.3% | 303 |
| 1.5B | MATH-500 | 87.2% | 13.0% | 557 |
| 1.5B | SVAMP | 95.5% | 0.7% | 211 |

Sanity check: Qwen's own reported numbers for these models (GSM8K about 50% and
73%, MATH about 34% and 55%) are close to ours, so the harness and parser are
not obviously broken.

## Grader audit

Every wrong answer whose parsed prediction contains the gold answer, or whose
last 60 characters contain it, was listed and read (36 cases for 1.5B). All were
genuine model errors (e.g. `16.50` for 16, `-30` for 30, `\frac{1}{332}` for 332),
not parser misses.

## Notes for later weeks

- MATH-500 answers are truncated 13-16% of the time at 1024 tokens; those count
  as wrong. Training uses 512-token answers, so watch for this.
- T4s have no fast bf16, so Kaggle runs use fp16 (the weights are stored in bf16
  and are cast on load). Local runs on the RTX 3050 use bf16.
- `TQDM_DISABLE=1` crashes vLLM 0.32's `generate` (division by zero); the
  harness passes `use_tqdm=False` instead.
- Installing vLLM on Kaggle upgrades torch to a CUDA 13 build; the preinstalled
  torchaudio must be uninstalled or transformers fails on import.

## Still to do (by hand)

- Read the 20 failures in `analysis/failures/base-1.5b-gsm8k.md` and fill in a
  failure type for each.
- One-page summary of the DeepSeekMath and DeepSeek-R1 papers.
