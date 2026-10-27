# Week 4: main run on Qwen2.5-1.5B

## Headline (test sets, scored once)

Week 1 harness settings: vLLM, fp16, greedy, 1,024 new tokens. The base model was re-scored in
the same session and matched week 1 on all 1,319 GSM8K problems.

| Model | GSM8K test | MATH-500 | SVAMP | Avg tokens (GSM8K) |
|---|---|---|---|---|
| Qwen2.5-1.5B-Instruct (base) | 75.8% | 56.4% | 83.4% | 303 |
| + GRPO, step 350 (selected on validation) | **75.7%** | 56.8% | 85.3% | 299 |

Paired, problem by problem (newly solved / newly failed, two-sided sign test):

| | GSM8K | MATH-500 | SVAMP |
|---|---|---|---|
| change | +87 / -88 (p = 1.0) | +45 / -43 (p = 0.92) | +74 / -55 (p = 0.11) |

**No gain on GSM8K test.** Training changed which problems the model solves (175 flipped) but
not how many. SVAMP's +1.9 points is suggestive but not significant; MATH-500 is flat.

## What was built

- `grpo/vllm_worker.py`: vLLM in its own process on GPU 1. Before each rollout the trainer
  saves the LoRA adapter and the worker loads it under a new LoRA id, so generation always uses
  the current weights. Prompts are passed as token ids.
- `grpo/solve_rates.py`: 8 samples per GSM8K train problem from the base model. 3,137 of 6,973
  (45%) were solved 8/8 and dropped; training used the other 3,836 (`results/filter/`).
- `skip_zero_std_groups`: groups whose 8 answers all got the same reward are not
  back-propagated (about 30% of groups), which cut training time per step by ~20%.
- Resume across Kaggle sessions: the step-250 checkpoint was uploaded as a private Kaggle
  dataset and session 2 continued from it (`kaggle/week4/`).

Run: lr 1e-5, 16 problems x 8 answers, 500 steps, about 87 s per step (38 s vLLM generation,
48 s training), two sessions of ~6.5 h each.

## Training curves

`analysis/plots/week4-1.5b.png`. Validation (500 held-out GSM8K *train* problems, greedy,
512 tokens), paired against step 0:

| step | 0 | 50 | 100 | 150 | 200 | 250 | 300 | 350 | 400 | 450 | 500 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| val | 83.4 | 83.4 | 83.2 | 82.8 | 85.8 | 85.4 | 87.4 | **88.4** | 86.8 | 86.6 | 86.4 |
| vs base | | +19/-19 | +19/-20 | +23/-26 | +31/-19 | +34/-24 | +38/-18 | +40/-15 | +43/-26 | +38/-22 | +38/-23 |

Step 350 was selected by the plan's rule (best validation; p = 0.001 vs base).

## Collapse after step ~330, again

Same failure as the 0.5B run at lr 3e-5 (week 3), later and at the plan's learning rate:

| steps | 1-300 | 301-350 | 351-400 | 451-500 |
|---|---|---|---|---|
| KL to base | < 0.013 | 0.025 | 0.10 | 0.19 |
| sampled answers with garbage tokens | ~0% | 1.5% | 13% | 17% |
| truncated at 512 | 3-6% | 5.6% | 15% | 17% |
| format reward earned | 92-96% | 93% | 84% | 82% |

Greedy answers stayed clean at every checkpoint (0 of 500 validation answers had garbage), so
greedy validation again did not show it; the `garbage_rate` metric added after week 3 did.
Step 350 sits at the start of the collapse (5 of 128 sampled answers garbled), but its greedy
test answers contain no garbage.

The early part of the garbage curve is also interesting: the base 1.5B switches into Chinese
mid-answer in about 5% of samples, and training removed that within ~20 steps.

## Why validation and test disagree

Validation rose +5 points (p = 0.001) while test stayed flat. Checked explanations:

1. **Near-duplicates of training problems in validation: ruled out.** Using word-bigram
   overlap with numbers masked, validation and test are equally far from the training
   problems (median nearest similarity 0.10 for both), and all 40 validation gains came from
   problems with no close training neighbour.
2. **The 512-token cap: a small part.** Validation and training stop at 512 tokens, test at
   1,024. Only 5 of the 40 validation gains were problems the base model had truncated.
3. **Contamination of the GSM8K train split: most likely.** At equal difficulty (number of
   reference solution steps) the *base* model is about 8 points better on validation problems
   than on test problems:

   | solution steps | 1-2 | 3-4 | 5-6 | 7+ |
   |---|---|---|---|---|
   | base accuracy, validation (train split) | 95% | 84% | 72% | 50% |
   | base accuracy, test | 86% | 76% | 68% | 57% |
   | GRPO net change, validation | +1 | +13 | +9 | +2 |
   | GRPO net change, test | -2 | -3 | +2 | +2 |

   Qwen2.5 has very likely seen GSM8K's train split. RL on train-split problems seems to have
   sharpened what the model already knew about that split, which helps other train-split
   problems but not unseen test problems. A validation set drawn from the train split is
   therefore an optimistic proxy for test accuracy, and checkpoint selection on it is biased.

Selection itself adds a little optimism too (best of 10 checkpoints on the same 500 problems).

## What to change next (week 5 candidates)

- **Validation that behaves like test**: a split that the base model scores like test
  (e.g. the base 1.5B gets 75.8% on test vs 83.4% on train-split validation), or a different
  dataset such as SVAMP, so checkpoint selection is not biased by contamination.
- **Stop the collapse**: lower lr after warm-up or decay it, a larger KL beta, or a smaller
  max grad norm; and treat a rising `garbage_rate` as a stop signal.
- **Harder training data**: GSM8K train is both partly memorised and mostly easy for 1.5B;
  the plan's optional MATH levels 1-3 phase is now more attractive.
- The ablations (group size, KL, format reward, std normalisation) on 0.5B, as planned.
