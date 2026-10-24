"""50 hand-checked grading cases: (model response, gold answer, should it count as correct).

Each case was written and checked by hand. If a case fails, decide whether the
parser or the expectation is wrong before changing either.
"""
import pytest

from eval.answer_parse import extract_answer, grade, gsm8k_gold, last_boxed

CASES = [
    # --- GSM8K-style numeric answers ---
    ("She makes 9 * 2 = 18 dollars.\n\\boxed{18}", "18", True),
    ("\\boxed{\\$18}", "18", True),
    ("\\boxed{18.00}", "18", True),
    ("\\boxed{1,200}", "1200", True),
    ("\\boxed{18 \\text{ dollars}}", "18", True),
    ("\\boxed{\\text{18}}", "18", True),
    ("\\boxed{1{,}000{,}000}", "1000000", True),
    ("\\boxed{-5}", "-5", True),
    ("\\boxed{50\\%}", "50", True),
    ("\\boxed{x = 12}", "12", True),
    ("\\boxed{3/4}", "0.75", True),
    ("\\boxed{\\frac{3}{4}}", "0.75", True),
    ("\\boxed 7", "7", True),
    ("So the total is \\boxed{18}.", "18", True),
    ("\\boxed{17}", "18", False),
    ("\\boxed{18.5}", "18", False),
    ("\\boxed{0.18}", "18", False),
    ("\\boxed{180}", "18", False),
    # --- last \boxed wins (self-correction) ---
    ("First guess \\boxed{10}. Wait, let me recheck... \\boxed{12}", "12", True),
    ("First guess \\boxed{10}. Wait, let me recheck... \\boxed{12}", "10", False),
    # --- fallbacks when there is no \boxed ---
    ("The answer is 42.", "42", True),
    ("The final answer is: $1,000$", "1000", True),
    ("**Final Answer:** 25", "25", True),
    ("The answer is 18 eggs per day.", "18", True),
    ("The answer is 18, because 9 * 2 = 18.", "18", True),
    ("Janet sells 9 eggs at $2 each.\n#### 18", "18", True),
    ("She had 5 apples, bought 3 more, so 8 apples.", "8", True),
    ("She had 5 apples, bought 3 more, so 8 apples.", "5", False),
    ("", "5", False),
    ("I am not able to solve this problem.", "5", False),
    # --- MATH-500-style LaTeX answers ---
    ("\\boxed{\\frac{1}{2}}", "\\frac{1}{2}", True),
    ("\\boxed{\\dfrac{1}{2}}", "\\frac{1}{2}", True),
    ("\\boxed{\\frac12}", "\\frac{1}{2}", True),
    ("\\boxed{0.5}", "\\frac{1}{2}", True),
    ("\\boxed{1.5}", "\\frac{3}{2}", True),
    ("\\boxed{\\frac{2}{3}}", "\\frac{1}{2}", False),
    ("\\boxed{\\left( 3, \\frac{\\pi}{2} \\right)}", "\\left( 3, \\frac{\\pi}{2} \\right)", True),
    ("\\boxed{(3, \\frac{\\pi}{2})}", "\\left( 3, \\frac{\\pi}{2} \\right)", True),
    ("\\boxed{(3, \\pi)}", "\\left( 3, \\frac{\\pi}{2} \\right)", False),
    ("\\boxed{p - q}", "p - q", True),
    ("\\boxed{q - p}", "p - q", False),
    ("\\boxed{2\\sqrt3}", "2\\sqrt{3}", True),
    ("\\boxed{\\sqrt{12}}", "2\\sqrt{3}", True),
    ("\\boxed{\\frac{\\sqrt{2}}{2}}", "\\frac{\\sqrt2}{2}", True),
    ("\\boxed{x^2+2x+1}", "x^2 + 2x + 1", True),
    ("\\boxed{30^\\circ}", "30", True),
    ("\\boxed{(B)}", "\\text{(B)}", True),
    ("\\boxed{[-2, 5)}", "[-2,5)", True),
    ("\\boxed{[-2, 5]}", "[-2,5)", False),
    ("The answer is $\\frac{3}{5}$.", "\\frac{3}{5}", True),
]


def test_case_count():
    assert len(CASES) == 50


@pytest.mark.parametrize("response,gold,correct", CASES)
def test_grade(response, gold, correct):
    assert grade(response, gold)["correct"] is correct


def test_last_boxed_nested_braces():
    assert last_boxed("\\boxed{\\frac{1}{\\sqrt{2}}}") == "\\frac{1}{\\sqrt{2}}"


def test_last_boxed_truncated():
    assert last_boxed("so the answer is \\boxed{\\frac{1}{2") is None


def test_extract_sources():
    assert extract_answer("\\boxed{5}")[1] == "boxed"
    assert extract_answer("The answer is 5")[1] == "phrase"
    assert extract_answer("#### 5")[1] == "hash"
    assert extract_answer("it is 5")[1] == "last_number"
    assert extract_answer("no digits here") == (None, None)


def test_gsm8k_gold():
    assert gsm8k_gold("Step one <<2+2=4>>4\n#### 1,000") == "1000"
    assert gsm8k_gold("...\n#### 18") == "18"
