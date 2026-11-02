# GRPO From Scratch: What Worked, What Didn't, and Why

*Teaching Qwen2.5 to do grade-school math with reinforcement learning, on free GPUs.*

I implemented GRPO (Group Relative Policy Optimization), the reinforcement learning method behind
DeepSeek-R1, from scratch in PyTorch and used it to train small open models on GSM8K. On
Qwen2.5-0.5B-Instruct it raised GSM8K test accuracy from **49.1% to 53.3%** (153 problems fixed,
98 broken, paired sign test p = 0.001). On Qwen2.5-1.5B-Instruct the same recipe left test accuracy
unchanged (75.8% → 75.7%), even though validation said +5 points. Working out why turned out to be
the most useful part of the project.

Code, configs and every result: https://github.com/Vansh8010-boop/grpo-reasoning

## The method in one paragraph

For each training problem the model writes 8 answers. A program checks each one: 1 point for the
correct final answer in `\boxed{}`, plus 0.2 for clean formatting. Each answer's advantage is its
reward minus its group's mean, divided by the group's standard deviation, so answers are judged
only against siblings for the same problem. The policy loss makes above-average answers more
likely and below-average ones less likely, with PPO-style clipping and a KL penalty that keeps the
model close to the original. No human labels, no learned reward model and no value network.

Implementation details that mattered:

- **Log-probabilities over answer tokens only.** Each training row is `[left-padded prompt | answer |
  right padding]`, with position ids rebuilt from the attention mask. Unit tests check that an
  answer's log-probs do not change with the padding around it and that each token's probability
  comes from the previous position. Masking bugs are the classic way GRPO "trains" without learning.
- **LoRA, with the reference model for free.** The KL reference is the same network with the
  adapter switched off, so it costs no extra memory.
- **Sampling that matches the loss.** Qwen's default generation config turns on top-k 20 and a
  repetition penalty. Sampling from a trimmed distribution while computing log-probs from the full
  one quietly biases training, so rollouts use plain temperature sampling.
- **vLLM on a second GPU.** For 1.5B, generation runs in vLLM on one T4 while training runs on the
  other; the LoRA weights are saved and loaded into vLLM under a new id every step.
- **One answer parser for everything.** The same code grades training rewards and evaluation, and
  is pinned down by 50 hand-checked test cases.

## Results

All numbers: greedy decoding, 1,024 new tokens, the same prompt and parser before and after.

| | GSM8K test | SVAMP | MATH-500 |
|---|---|---|---|
| Qwen2.5-0.5B-Instruct | 49.1% | 61.6% | |
| + GRPO, 250 steps | **53.3%** (p = 0.001) | 63.7% (p = 0.15) | |
| Qwen2.5-1.5B-Instruct | 75.8% | 83.4% | 56.4% |
| + GRPO, 500 steps (best on validation) | 75.7% (p = 1.0) | 85.3% (p = 0.11) | 56.8% |

The 0.5B result is the final checkpoint of the run, not chosen on any held-out set. Typical fixes
are procedural: in one test problem the base model works out pairs of snowshoes per dog and forgets
to multiply by the number of dogs; the trained model does not.

## Ablations

Six one-change experiments on 0.5B, 250 steps each, final checkpoints scored on GSM8K test:

| Change | GSM8K test | Note |
|---|---|---|
| baseline (8 answers, KL 0.04, format reward, std normalization) | 53.3% | |
| 4 answers per problem (x 32 problems) | 51.9% | 42% of groups were all right or all wrong: no signal |
| 16 answers per problem (x 8 problems) | 52.8% | most signal per problem, noisiest curve |
| no KL penalty | 53.2% | drifted 6x further, answers 13% shorter |
| KL 0.01 | 52.9% | |
| no format reward | 53.9% | the model learned to box answers anyway |
| mean-only advantages (no std division) | 51.9% | updates half as large: acts like a lower learning rate |
| learning rate 3e-5 | 51.4% | collapsed (below) |

Every variant beat the base model; none differed significantly from the baseline (all p ≥ 0.11).
At this scale GRPO is robust to these knobs. The rankings on my validation set were mostly noise:
"no format reward" looked second-worst on validation and was best on test.

## What didn't work

**1.5B did not improve on test.** Validation (500 held-out problems from GSM8K's *training*
split) went from 83.4% to 88.4% with p = 0.001, and test did not move. I checked three
explanations. Near-duplicates between validation and the training problems: no, the two splits are
equally far from the training data. The 512-token training cap: a small part, 5 of 40 validation
gains. Contamination: at equal difficulty, the *base* 1.5B model is about 8 points better on
training-split problems than on test problems, which is what you would expect if it had seen the
training split during its own training. RL on that split sharpened knowledge of that split. The
lesson: a validation set carved from a possibly memorised training split is an optimistic guide.

**Late-training collapse.** At lr 3e-5 on 0.5B (from step ~150), and on 1.5B at the default
1e-5 (from step ~330), sampled answers began dissolving into random multilingual tokens: up to 17%
of samples, with KL to the base model rising 10-15x. Greedy validation hid it completely, because the
most likely token stays sensible while the tail of the distribution, which training samples from, is
damaged. A per-step "garbage rate" metric caught it at once. It was not reward hacking: garbled
answers were correct 2 times out of 59 and got near-zero reward. The cause remains open; candidates
are the KL estimator on very unlikely tokens, fp16 numerics, and the small mismatch between vLLM's
sampling and the trainer's probabilities.

**No "aha moment".** Phrases like "wait" or "let me verify" stayed at 1-2% of answers in every run.
Self-verification has been reported for larger models trained much longer; at this scale it did
not appear.

## Reward hacking

I screened all 1,297 high-reward training answers for five suspicious patterns and read every one
of the 31 flagged. Two were questionable: one boxed the correct answer after reasoning that reached a
different number (plausibly a memorised answer), and one boxed the correct answer after its
reasoning turned to word salad. On GSM8K an exact-match reward is hard to game.

## Doing it on free GPUs

Everything ran on Kaggle's free T4s: 30 GPU-hours a week, at most two sessions at a time, 12 hours
per session, fp16 only. That shaped the project: LoRA instead of full fine-tuning, 250-step
ablations run two at a time, filtering out the 45% of training problems the 1.5B model already
solved 8/8, and resuming the 500-step run across two sessions through a private dataset.

## If I did it again

- Validate on data the model is unlikely to have seen, or at least check base-model accuracy
  on the validation split against the test split before trusting it.
- Log a degeneration metric from step one and stop or decay the learning rate when it rises.
- Spend the 1.5B budget on harder problems (for example MATH levels 1-3) rather than more GSM8K.
