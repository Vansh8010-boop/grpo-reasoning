# Week 5: ablations and analysis

## Headline: GRPO improves the 0.5B model on GSM8K test

The week 3 0.5B run (lr 1e-5, 250 steps, final checkpoint, no checkpoint selection), scored
on the untouched test sets with the week 1 harness (vLLM, fp16, greedy, 1,024 tokens):

| Model | GSM8K test | vs base (paired) | SVAMP | vs base (paired) |
|---|---|---|---|---|
| Qwen2.5-0.5B-Instruct (base) | 49.1% | | 61.6% | |
| + GRPO (this repo) | **53.3%** | +153 / -98, **p = 0.001** | 63.7% | +107 / -86, p = 0.15 |

So GRPO from scratch works on the 0.5B model (+4.2 points, significant), while on 1.5B it did
not move GSM8K test (week 4). The 0.5B model starts much lower (49% vs 76%), leaving more room
for RL to fix errors in procedure, which is the kind of mistake the fixed examples show.

## Ablations (Qwen2.5-0.5B, 250 steps, one change at a time)

Settings as `configs/grpo-0.5b.yaml` except the named change (`configs/abl-*.yaml`). Group-size
runs keep 128 answers per step so the comparison is about how a fixed sampling budget is split.

| Run | Best val (train split) | GSM8K test (step 250) | vs base | vs baseline run | SVAMP |
|---|---|---|---|---|---|
| base model | 62.6% | 49.1% | | | 61.6% |
| **baseline** (G=8, KL 0.04, format 0.2, std) | 69.2% | **53.3%** | +153/-98 p=0.001 | | 63.7% |
| G=4 x 32 problems | 65.2% | 51.9% | +135/-98 p=0.02 | +97/-115 p=0.24 | 62.7% |
| G=16 x 8 problems | 69.4% | 52.8% | +139/-90 p=0.001 | +96/-102 p=0.72 | 60.5% |
| KL 0 | 70.0% | 53.2% | +181/-127 p=0.002 | +138/-139 p=1.0 | 61.6% |
| KL 0.01 | 68.2% | 52.9% | +172/-122 p=0.004 | +117/-122 p=0.80 | 58.7% |
| format reward off | 66.8% | 53.9% | +153/-90 p<0.001 | +114/-106 p=0.64 | 62.7% |
| mean-only advantages | 66.4% | 51.9% | +115/-79 p=0.01 | +107/-126 p=0.24 | 64.6% |
| lr 3e-5 (collapsed, week 3) | 67.6% | 51.4% | +154/-124 p=0.08 | +103/-128 p=0.11 | 63.2% |

Plots: `analysis/plots/week5-ablations.png` (validation curves) and
`analysis/plots/week5-ablations-test.png` (test accuracy).

**Every variant beats the base model on GSM8K test, and none is significantly different from
the baseline run.** At this scale (250 steps, LoRA, 0.5B) GRPO is robust to these choices; the
differences seen on validation were mostly noise. One sentence per experiment:

- **Group size**: G=4 wastes compute (42% of groups had all-equal rewards and no signal, vs 26%
  at G=8 and 15% at G=16) and learned slowest on validation; on test it is 1.4 points behind the
  baseline, not significant. G=8 is a sound default.
- **KL coefficient**: removing the KL penalty let the policy drift 6x further (KL 0.052 vs 0.009)
  and made answers 13% shorter, with the same test accuracy. Within 250 steps the penalty only
  limited drift; it did not prevent or cause collapse here.
- **Format reward**: without it the model still learned to box its answers (88% -> 92% of
  samples, vs 91% -> 96% with it) because correct answers are mostly boxed already; test accuracy
  is unchanged. The format reward is not necessary for clean answers on GSM8K.
- **Advantage normalization**: dropping the division by group std halves the average advantage
  (0.25 vs 0.57) and the gradient norm, so it behaves like a smaller learning rate; it learned a
  little slower (51.9% test), not significantly. The effect on which problems get weight cannot be
  separated from the step-size effect in this design.
- **Learning rate** (week 3): 3e-5 collapsed into garbage tokens and ended with the smallest gain
  (51.4%, not significant vs base) and 3x the truncation of the baseline.

## Reward-hacking hunt

`python -m analysis.reward_hacking` screened all 1,297 high-reward (correct + format) answers in the
0.5B and 1.5B sample dumps for five patterns; 31 were flagged and every flagged answer was read:

| Flag | Count | After reading |
|---|---|---|
| boxed number not supported by the reasoning | 5 | 1 real case (reasoning ends at x = 12, boxes the correct 13), 1 garbled-but-correct, 3 honest |
| gold answer stated early | 4 | false positives (e.g. 20 appearing in "100 + 20") |
| garbage tokens | 1 | honest; a few Chinese words mixed in |
| several final answers | 21 | false positives of the pattern ("therefore ... is 3 x 5") |

**2 questionable answers out of 1,297.** The exact-answer reward is hard to game on GSM8K. The
one wrong-reasoning/right-answer case on 1.5B fits the contamination finding from week 4 (the
model may remember the train-split answer). A 100-answer random sample for reading by hand is in
`analysis/reward_hacking/sample-100.md`.

The collapse is **not** reward hacking: degenerate (garbled) answers were correct only 2 times out
of 59 and averaged a reward near 0, so GRPO was pushing them down, not up. Its cause is an
optimisation problem left open (candidates: the k3 KL term on very unlikely tokens, fp16
numerics, the mismatch between vLLM sampling and the trainer's probabilities).

## Behaviour over training

- Response length stayed around 300 tokens on both models (0.5B: 313 -> 296; 1.5B: 323 -> 308
  before the collapse); without KL it fell to 258.
- Self-checking phrases ("wait", "let me verify") stayed at 1-2% of answers with no upward trend
  in any run. No "aha moment" at this scale and training length.
- The base 1.5B switches into Chinese mid-answer in ~5% of samples; training removed this within
  ~20 steps.

## Qualitative examples

`analysis/examples-1.5b.md`: 5 GSM8K test problems the 1.5B GRPO model fixed and 5 it broke
(e.g. the base model forgets to multiply snowshoe pairs by the 6 dogs; the trained model does not).
