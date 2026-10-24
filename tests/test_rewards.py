import pytest

from grpo.rewards import RewardConfig, compute_rewards, format_reward, length_penalty

CFG = RewardConfig()
REASONING = "Janet's ducks lay 16 eggs. She uses 3 + 4 = 7, so 16 - 7 = 9 remain. 9 * 2 = 18 dollars. "


@pytest.mark.parametrize(
    "response,expected",
    [
        (REASONING + "The answer is \\boxed{18}.", 1.0),
        ("\\boxed{18}", 0.0),  # no reasoning
        (REASONING + "The answer is 18.", 0.0),  # no box
        (REASONING + "\\boxed{}", 0.0),  # empty box
        (REASONING + "\\boxed{18", 0.0),  # unclosed (truncated)
        (REASONING + "\\boxed{17} or maybe \\boxed{18}", 0.0),  # more than one box
        (REASONING + "\\boxed{18}" + " Some rambling afterwards." * 20, 0.0),  # box not at the end
        (REASONING + "\\boxed{\\frac{1}{2}}", 1.0),  # nested braces
    ],
)
def test_format_reward(response, expected):
    assert format_reward(response, CFG) == expected


def test_length_penalty():
    assert length_penalty(100, False, CFG) == 0.0
    assert length_penalty(384, False, CFG) == 0.0  # 512 - 128: penalty starts after this
    assert length_penalty(448, False, CFG) == pytest.approx(-0.5)
    assert length_penalty(512, False, CFG) == -1.0
    assert length_penalty(300, True, CFG) == -1.0  # truncated is always -1


def test_compute_rewards_weights():
    r = compute_rewards(REASONING + "\\boxed{18}", "18", 50, False, CFG)
    assert (r["correct"], r["format"], r["length"]) == (1.0, 1.0, 0.0)
    assert r["total"] == pytest.approx(1.2)
    wrong = compute_rewards(REASONING + "\\boxed{17}", "18", 50, False, CFG)
    assert wrong["total"] == pytest.approx(0.2)  # format credit only
    no_fmt = compute_rewards(REASONING + "\\boxed{18}", "18", 50, False, RewardConfig(format_weight=0.0))
    assert no_fmt["total"] == 1.0
