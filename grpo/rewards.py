"""Rewards for GRPO. Each component is a float; compute_rewards combines them with config weights.

  correct  1 if the final answer matches the gold answer, else 0
  format   1 if the response reasons first and ends with exactly one \\boxed{} answer, else 0
  length   0 normally, sliding to -1 as the response nears the token limit, -1 if truncated (off by default)
"""
import re
from dataclasses import dataclass

from eval.answer_parse import grade, last_boxed


@dataclass
class RewardConfig:
    correct_weight: float = 1.0
    format_weight: float = 0.2
    length_weight: float = 0.0
    max_tokens: int = 512
    length_buffer: int = 128  # soft length penalty starts this many tokens before max_tokens
    min_reasoning_chars: int = 50  # text required before the \boxed{}
    max_chars_after_box: int = 200  # the box must be at the end, not mid-response


def correctness_reward(response, gold):
    return 1.0 if grade(response, gold)["correct"] else 0.0


def format_reward(response, cfg):
    if len(re.findall(r"\\boxed", response)) != 1:
        return 0.0
    box = last_boxed(response)
    if not box or not box.strip():
        return 0.0
    start = response.rfind("\\boxed")
    end = response.find(box, start) + len(box) + 1
    if start < cfg.min_reasoning_chars or len(response) - end > cfg.max_chars_after_box:
        return 0.0
    return 1.0


def length_penalty(n_tokens, truncated, cfg):
    if truncated:
        return -1.0
    start = cfg.max_tokens - cfg.length_buffer
    if n_tokens <= start:
        return 0.0
    return -min(1.0, (n_tokens - start) / cfg.length_buffer)


def compute_rewards(response, gold, n_tokens, truncated, cfg):
    r = {
        "correct": correctness_reward(response, gold),
        "format": format_reward(response, cfg),
        "length": length_penalty(n_tokens, truncated, cfg),
    }
    r["total"] = cfg.correct_weight * r["correct"] + cfg.format_weight * r["format"] + cfg.length_weight * r["length"]
    return r
