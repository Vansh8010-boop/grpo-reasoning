"""Token log-probabilities and the GRPO loss.

Batch layout, one row per answer:

  [pad pad | prompt tokens | response tokens | pad pad]
   left-padded prompt        right-padded response

Only response tokens are scored (response_mask is 1 exactly on the generated
tokens, including the final EOS). position_ids are computed from the attention
mask so a left-padded prompt gets the same positions it had during generation.
"""
import torch


def build_batch(prompts, responses, pad_id, device):
    """prompts, responses: lists of token-id lists. Returns ids, attention_mask, position_ids, response_mask."""
    P = max(len(p) for p in prompts)
    R = max(len(r) for r in responses)
    ids, attn, rmask = [], [], []
    for p, r in zip(prompts, responses):
        ids.append([pad_id] * (P - len(p)) + p + r + [pad_id] * (R - len(r)))
        attn.append([0] * (P - len(p)) + [1] * (len(p) + len(r)) + [0] * (R - len(r)))
        rmask.append([1.0] * len(r) + [0.0] * (R - len(r)))
    ids = torch.tensor(ids, device=device)
    attn = torch.tensor(attn, device=device)
    pos = (attn.cumsum(-1) - 1).clamp(min=0)
    return ids, attn, pos, torch.tensor(rmask, device=device)


def token_logprobs(model, ids, attn, pos, n_response):
    """log p(token | everything before it) for the last n_response positions: shape [B, n_response]."""
    out = model(input_ids=ids, attention_mask=attn, position_ids=pos, logits_to_keep=n_response + 1, use_cache=False)
    logits = out.logits[:, :-1]  # the logit at position k predicts token k+1
    targets = ids[:, -n_response:]
    # One row at a time: the fp32 log-softmax over a 152k vocabulary is the memory peak.
    rows = [l.float().log_softmax(-1).gather(-1, t[:, None]).squeeze(-1) for l, t in zip(logits, targets)]
    return torch.stack(rows)


def grpo_loss(logp, old_logp, ref_logp, adv, mask, clip_eps=0.2, beta=0.04):
    """Clipped policy loss plus KL penalty, averaged over each answer's tokens.

    logp, old_logp, ref_logp, mask: [B, T]; adv: [B].
    Returns (loss per answer [B], stats dict of detached per-batch sums).

    KL uses the k3 estimator from DeepSeekMath: exp(ref - logp) - (ref - logp) - 1,
    which is >= 0 per token and unbiased for KL(policy || reference).
    """
    ratio = torch.exp(logp - old_logp)
    a = adv[:, None]
    pg = -torch.min(ratio * a, ratio.clamp(1 - clip_eps, 1 + clip_eps) * a)
    d = ref_logp - logp
    kl = torch.exp(d) - d - 1
    n_tok = mask.sum(1).clamp(min=1)
    loss = ((pg + beta * kl) * mask).sum(1) / n_tok
    with torch.no_grad():
        stats = {
            "kl_sum": ((kl * mask).sum(1) / n_tok).sum().item(),
            "clipped_tokens": (((ratio - 1).abs() > clip_eps).float() * mask).sum().item(),
            "tokens": mask.sum().item(),
        }
    return loss, stats
