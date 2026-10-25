"""Group-relative advantages: each answer is scored against the other answers to the same problem.

  A_i = (R_i - mean(R_1..R_G)) / (std(R_1..R_G) + eps)

A group whose rewards are all equal gets A = 0 for every answer: no policy signal.
"""
import torch


def group_advantages(rewards, normalize_std=True, eps=1e-4):
    """rewards: [n_groups, G] -> advantages of the same shape.

    std is the unbiased sample std (torch default), matching TRL's GRPOTrainer
    so the two implementations can be compared on equal settings.
    """
    rewards = torch.as_tensor(rewards, dtype=torch.float32)
    adv = rewards - rewards.mean(dim=1, keepdim=True)
    if normalize_std:
        adv = adv / (rewards.std(dim=1, keepdim=True) + eps)
    return adv
