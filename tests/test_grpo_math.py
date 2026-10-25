"""Advantages, the GRPO loss, and the log-prob batch layout (the most common silent bug)."""
import pytest
import torch

from grpo.advantages import group_advantages
from grpo.loss import build_batch, grpo_loss, token_logprobs


def test_advantages_basic():
    adv = group_advantages([[1.0, 0.0, 0.0, 1.0]])
    std = torch.tensor([1.0, 0.0, 0.0, 1.0]).std()
    assert torch.allclose(adv, torch.tensor([[0.5, -0.5, -0.5, 0.5]]) / (std + 1e-4))
    assert abs(adv.sum().item()) < 1e-6


def test_advantages_zero_std_group_is_zero():
    adv = group_advantages([[1.2, 1.2, 1.2], [0.0, 1.0, 0.0]])
    assert torch.all(adv[0] == 0)
    assert adv[1, 1] > 0 > adv[1, 0]


def test_advantages_mean_only():
    adv = group_advantages([[2.0, 0.0]], normalize_std=False)
    assert torch.allclose(adv, torch.tensor([[1.0, -1.0]]))


def test_loss_on_policy_no_kl():
    """At the start of a step (policy == old == reference) the loss is just -A, and KL is 0."""
    logp = torch.log(torch.tensor([[0.5, 0.5, 0.5], [0.2, 0.2, 0.2]]))
    mask = torch.tensor([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0]])
    adv = torch.tensor([1.0, -2.0])
    loss, stats = grpo_loss(logp, logp, logp, adv, mask)
    assert torch.allclose(loss, -adv)
    assert stats["kl_sum"] == pytest.approx(0.0)
    assert stats["clipped_tokens"] == 0 and stats["tokens"] == 5


def test_loss_gradient_direction():
    """Positive advantage -> gradient descent raises the answer's log-prob; negative lowers it."""
    for a, sign in [(1.0, -1), (-1.0, 1)]:
        logp = torch.log(torch.tensor([[0.3, 0.4]])).requires_grad_()
        loss, _ = grpo_loss(logp, logp.detach(), logp.detach(), torch.tensor([a]), torch.ones(1, 2))
        loss.sum().backward()
        assert torch.all(torch.sign(logp.grad) == sign)


def test_loss_clipping_stops_gradient():
    """Ratio above 1+eps with positive advantage: the clipped term is active and has zero gradient."""
    old = torch.log(torch.tensor([[0.1]]))
    logp = torch.log(torch.tensor([[0.2]])).requires_grad_()  # ratio 2.0
    loss, stats = grpo_loss(logp, old, logp.detach(), torch.tensor([1.0]), torch.ones(1, 1), beta=0.0)
    loss.sum().backward()
    assert logp.grad.abs().item() == 0.0
    assert stats["clipped_tokens"] == 1


def test_kl_positive_and_masked():
    logp = torch.log(torch.tensor([[0.5, 0.9]]))
    ref = torch.log(torch.tensor([[0.25, 0.1]]))
    mask = torch.tensor([[1.0, 0.0]])  # second token is padding
    _, stats = grpo_loss(logp, logp, ref, torch.tensor([0.0]), mask, beta=1.0)
    d = torch.log(torch.tensor(0.25 / 0.5))
    assert stats["kl_sum"] == pytest.approx((torch.exp(d) - d - 1).item(), rel=1e-5)


@pytest.fixture(scope="module")
def tiny_model():
    from transformers import Qwen2Config, Qwen2ForCausalLM

    torch.manual_seed(0)
    cfg = Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=128)
    return Qwen2ForCausalLM(cfg).eval()


def test_padded_batch_matches_single(tiny_model):
    """An answer's log-probs must not depend on how much padding its batch-mates force on it."""
    prompts = [[5, 6, 7], [8, 9, 10, 11, 12, 13]]
    responses = [[20, 21, 22, 23, 24], [30, 31]]
    with torch.no_grad():
        ids, attn, pos, mask = build_batch(prompts, responses, pad_id=0, device="cpu")
        batched = token_logprobs(tiny_model, ids, attn, pos, mask.shape[1])
        for i, (p, r) in enumerate(zip(prompts, responses)):
            ids1, attn1, pos1, _ = build_batch([p], [r], pad_id=0, device="cpu")
            single = token_logprobs(tiny_model, ids1, attn1, pos1, len(r))
            assert torch.allclose(batched[i, : len(r)], single[0], atol=1e-5)


def test_logprobs_match_manual(tiny_model):
    """Check the shift: the log-prob of response token t comes from the logit one position earlier."""
    p, r = [5, 6, 7], [20, 21]
    with torch.no_grad():
        ids, attn, pos, _ = build_batch([p], [r], pad_id=0, device="cpu")
        got = token_logprobs(tiny_model, ids, attn, pos, 2)[0]
        full = tiny_model(input_ids=torch.tensor([p + r])).logits[0].log_softmax(-1)
        want = torch.stack([full[2, 20], full[3, 21]])
    assert torch.allclose(got, want, atol=1e-5)
