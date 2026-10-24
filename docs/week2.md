# Week 2: rewards and rollouts

## Rewards (`grpo/rewards.py`)

| Component | Value | Default weight |
|---|---|---|
| correct | 1 if the parsed final answer matches gold (same grader as eval), else 0 | 1.0 |
| format | 1 if there is exactly one `\boxed{}`, it is non-empty and closed, at least 50 characters of reasoning come before it, and at most 200 characters after it | 0.2 |
| length | 0 up to 384 tokens, sliding linearly to -1 at 512; -1 if truncated | 0.0 (off) |

Total = 1.0 x correct + 0.2 x format + 0.0 x length, so the range is 0 to 1.2.

## Rollouts (`grpo/rollout.py`)

8 samples per problem, temperature 0.9, top-k and top-p off, no repetition
penalty, 512 new tokens max. Problems are drawn from the GSM8K train split
(never val or test).

## Rollout statistics: 128 GSM8K train problems x 8 samples, base models

| | 0.5B | 1.5B |
|---|---|---|
| sample accuracy | 46.6% | 71.9% |
| format reward earned | 85.1% | 89.4% |
| mean total reward | 0.64 | 0.90 |
| groups mixed (some right, some wrong) | **67.2%** | **60.9%** |
| groups all correct | 14.8% | 34.4% |
| groups all wrong | 18.0% | 4.7% |
| groups with zero reward spread (no learning signal) | 14.8% | 28.1% |
| truncated at 512 tokens | 8.9% | 5.0% |
| mean response length (tokens) | 321 | 298 |
| time on one T4 (HF generate, fp16) | 401 s | 790 s |

Groups by number of correct answers out of 8:

| correct | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| 0.5B | 23 | 21 | 11 | 9 | 11 | 6 | 15 | 13 | 19 |
| 1.5B | 6 | 6 | 5 | 12 | 8 | 6 | 17 | 24 | 44 |

## What this means for training

- **0.5B is a good debugging model**: two thirds of its groups are mixed, so most
  of each batch carries signal.
- **1.5B wastes about a third of each batch** on problems it always solves.
  Before the week 4 run, filter out training problems the base 1.5B solves 8/8,
  or sample more of the harder ones.
- **All-wrong groups are not always silent**: 16 of the 23 all-wrong 0.5B groups
  still have different rewards because format differs, so they teach format only.
  This is why "zero reward spread" (14.8%) is lower than "all correct + all wrong"
  (32.8%).
- Generation is the bottleneck: 1,024 samples of 1.5B took 13 minutes on a T4
  with HF generate. With 16 problems x 8 samples per step that is about 1.6 minutes
  of generation per step, before any training compute; vLLM (week 4) matters.
- Every format failure in the first 16-problem sample was either truncation (17)
  or no `\boxed{}` at all (8); none were parser mistakes.
