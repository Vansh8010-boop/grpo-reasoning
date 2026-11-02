---
base_model: Qwen/Qwen2.5-0.5B-Instruct
library_name: peft
license: apache-2.0
datasets:
- openai/gsm8k
language:
- en
tags:
- grpo
- reinforcement-learning
- lora
- math
- gsm8k
---

# Qwen2.5-0.5B-Instruct + GRPO (LoRA) for grade-school math

A LoRA adapter for [Qwen/Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct),
trained with GRPO (Group Relative Policy Optimization) implemented from scratch in PyTorch.
Code, data and full write-up: https://github.com/Vansh8010-boop/grpo-reasoning

## Results

Greedy decoding, 1,024 new tokens, vLLM fp16, the same prompt and answer parser for both models:

| | GSM8K test (1,319) | SVAMP (1,000) |
|---|---|---|
| Qwen2.5-0.5B-Instruct | 49.1% | 61.6% |
| **+ this adapter** | **53.3%** | 63.7% |
| problems fixed / broken | 153 / 98 (sign test p = 0.001) | 107 / 86 (p = 0.15) |

This is the final checkpoint of a single run (step 250), not selected on any test set.
The same recipe did **not** improve Qwen2.5-1.5B-Instruct on GSM8K test (75.8% → 75.7%);
the repository explains why (most likely contamination of the GSM8K training split).

## Training

- Algorithm: GRPO, 8 sampled answers per problem, group-normalized advantages, clipped policy loss,
  KL penalty (k3 estimator, beta 0.04) against the base model (the adapter switched off)
- Reward: 1 for a correct final answer (`\boxed{}`, exact numeric match) + 0.2 for format
- Data: GSM8K train split minus 500 held-out problems; 16 problems x 8 answers per step, 250 steps
- LoRA r=16, alpha=32 on all attention and MLP projections (8.8M parameters), lr 1e-5, fp16 on one T4

## Usage

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = "Qwen/Qwen2.5-0.5B-Instruct"
tok = AutoTokenizer.from_pretrained(base)
model = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base), "ArmedHipster/qwen2.5-0.5b-grpo-gsm8k")

question = "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?"
messages = [{"role": "user", "content": question + "\nPlease reason step by step, and put your final answer within \\boxed{}."}]
inputs = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
print(tok.decode(model.generate(inputs, max_new_tokens=512, do_sample=False)[0][inputs.shape[1]:], skip_special_tokens=True))
```

The adapter was trained and evaluated with exactly this prompt suffix; other prompts may score differently.

## Limitations

- Small gains on a small model; MATH-style problems were not trained on.
- Training at a higher learning rate (3e-5), and the 1.5B run after ~330 steps, degenerated into
  garbage tokens in sampled (not greedy) outputs; this checkpoint is from a stable run, but sampled
  outputs at high temperature are less reliable than greedy ones.
