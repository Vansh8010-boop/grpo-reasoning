# Week 3: GRPO loop on Qwen2.5-0.5B

## Code

| File | What it does |
|---|---|
| `grpo/advantages.py` | `(R_i - group mean) / (group std + 1e-4)`, or mean-only for the ablation |
| `grpo/loss.py` | padded batch layout, per-token log-probs over answer tokens only, clipped policy loss + k3 KL penalty |
| `grpo/train.py` | the loop: rollouts → rewards → advantages → one optimizer step; LoRA, validation, checkpoints, resume |
| `analysis/plot_training.py` | training curves for one or more runs |
| `tests/test_grpo_math.py` | advantages, loss values and gradient signs, clipping, KL masking, padded vs unpadded log-probs |

Design choices:
- **Reference model = base weights with the LoRA adapter disabled**, so it costs no memory.
- **One optimizer step per batch of rollouts** (GRPO with μ = 1), so the "old" policy is the
  current one and the ratio is exactly 1. Clipping only becomes active with several updates
  per batch; `clip_frac` was 0 throughout, as expected.
- **Loss = average over each answer's own tokens, then over answers** (the 1/|o_i| in the plan's formula).
- LoRA r=16, alpha=32 on all attention and MLP projections: 8.8M trainable parameters (1.75%).
- fp16 on Kaggle T4s with a GradScaler; LoRA weights stay in fp32.

## Runs

Same settings except learning rate: 16 problems x 8 answers per step, temperature 0.9,
512 tokens, KL beta 0.04, 250 steps, both runs saw the same problems in the same order.
About 95 s per step on one T4 (60 s generating, 35 s training); both runs in parallel took 6.6 h.

### Validation accuracy (500 held-out GSM8K train problems, greedy, 512 tokens)

| step | lr 1e-5 (plan) | lr 3e-5 |
|---|---|---|
| 0 (base) | 62.6% | 62.6% |
| 50 | 62.0% | **67.6%** |
| 100 | 63.8% | 66.4% |
| 150 | 67.6% | 65.8% |
| 200 | 68.8% | 67.0% |
| 250 | **69.2%** | 65.8% |

**lr 1e-5: +6.6 points, still rising at step 250.** Each number has a standard error of about
2 points (500 problems), so single steps are noisy, but the rise is steady across four
evaluations. Per-problem validation results are saved from now on (`val-<step>.jsonl`) so
later comparisons can be paired.

### Training statistics (averages over 50-step windows, lr 1e-5)

| | steps 1-50 | 101-150 | 201-250 |
|---|---|---|---|
| sample accuracy | 50.7% | 58.5% | 59.1% |
| format reward earned | 91.3% | 95.8% | 95.5% |
| mean reward | 0.69 | 0.78 | 0.78 |
| response length (tokens) | 313 | 288 | 296 |
| truncated at 512 | 6.4% | 3.2% | 3.5% |
| KL to base | 0.001 | 0.004 | 0.009 |
| answers with "wait"/"verify" phrases | 1.6% | 1.3% | 1.0% |

Plots: `analysis/plots/week3-0.5b.png`. The training reward of the two runs moves together
from step to step because they saw the same problems: much of the per-step noise is problem
difficulty, not learning.

## The lr 3e-5 run collapsed

From about step 150 its KL rose 10x (0.015 → 0.17) and sampled answers started degenerating
into random multilingual tokens partway through, usually right after the model hit something
confusing (e.g. a negative intermediate result). Answers with more than 5 such characters, out
of 128 dumped per step:

| step | 50 | 100 | 150 | 200 | 250 |
|---|---|---|---|---|---|
| lr 1e-5 | 0 | 0 | 1 | 0 | 0 |
| lr 3e-5 | 0 | 1 | 9 | 33 | 24 |

Truncation went to 15% and format reward fell to 84% in its last 50 steps. **Greedy
validation hid this** (it stayed around 66%) because the most likely token is still sensible;
the damage is in the tail of the distribution, which is exactly where sampling at
temperature 0.9 with top-k/top-p off draws from. `grpo/train.py` now logs `garbage_rate`
every step as an early warning.

## Reward hacking check (lr 1e-5)

Read through the five sample dumps (steps 50-250, 128 answers each): no correct answers
under 60 tokens, no garbage, truncations are long-winded reasoning, not loops. Nothing that
looks like gaming the reward yet. The full 100-answer hunt is week 5.

## Not seen

No growth in self-checking phrases (about 1-2% of answers throughout). Emergent "wait,
let me check" behaviour is reported for larger models and longer training; at 0.5B and
250 LoRA steps it did not appear. Worth tracking again on 1.5B.

## Done-when check

- Training reward rises: yes, 0.69 → 0.78 (sample accuracy 51% → 59%).
- Validation accuracy beats the 0.5B baseline: yes, 62.6% → 69.2% at lr 1e-5.

## Implications for week 4 (1.5B)

- Keep lr 1e-5; 3e-5 is unstable here, and the 1.5B model is likely no more forgiving.
- 1e-5 had not plateaued at 250 steps: the 1.5B run should go to 500+ as planned.
- Watch `garbage_rate` and KL, not only validation.
- Adapters: `ckpt-0050` ... `ckpt-0250` for both runs are in the Kaggle output of
  `vanshkulshrestha/grpo-train` (version 4), not in git.
