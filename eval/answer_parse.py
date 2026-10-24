"""Answer extraction and normalization.

Used by both the evaluation harness and the GRPO reward, so a bug here
silently corrupts both. Keep tests/test_answer_parse.py passing.

Extraction order (first hit wins):
  1. last \\boxed{...}           -> source "boxed"
  2. "the answer is X" phrases  -> source "phrase"
  3. "#### X" (GSM8K style)     -> source "hash"
  4. last number in the text    -> source "last_number"
"""
import logging
import re
import sys

logging.getLogger("math_verify").setLevel(logging.ERROR)

# math_verify's timeouts use signals on Linux and break under Windows
# multiprocessing, so on Windows we run it without a timeout.
_MV_KW = {"parsing_timeout": None} if sys.platform == "win32" else {}
_MV_VERIFY_KW = {"timeout_seconds": None} if sys.platform == "win32" else {}

_NUM = r"-?\d[\d,]*(?:\.\d+)?"


def last_boxed(text):
    """Content of the last \\boxed{...} or \\fbox{...}; None if absent or unclosed."""
    idx = max(text.rfind("\\boxed"), text.rfind("\\fbox"))
    if idx < 0:
        return None
    i = idx + (6 if text.startswith("\\boxed", idx) else 5)
    if i < len(text) and text[i] == " ":  # "\boxed 5"
        m = re.match(r" +([^\s$]+)", text[i:])
        return m.group(1) if m else None
    if i >= len(text) or text[i] != "{":
        return None
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j]
    return None  # unclosed, e.g. the response was truncated


def _leading_number(s):
    m = re.match(rf"\s*\$?\s*({_NUM})", s)
    return m.group(1).rstrip(",") if m else None


def extract_answer(text):
    """Return (answer_string, source); (None, None) if nothing is found."""
    if not text:
        return None, None
    boxed = last_boxed(text)
    if boxed is not None and boxed.strip():
        return boxed.strip(), "boxed"

    phrases = re.findall(r"(?:final answer|the answer)\s*(?:is|:)\s*:?\s*(.+)", text, re.I)
    if phrases:
        ans = _clean(phrases[-1])
        if to_number(ans) is None and _leading_number(ans) is not None:
            ans = _leading_number(ans)  # "18, because ..." -> "18"
        if ans:
            return ans, "phrase"

    hashes = re.findall(r"####\s*(.+)", text)
    if hashes and hashes[-1].strip():
        return hashes[-1].strip(), "hash"

    nums = re.findall(_NUM, text)
    if nums:
        return nums[-1].rstrip(","), "last_number"
    return None, None


def gsm8k_gold(solution):
    """GSM8K solutions end with '#### <answer>'."""
    return solution.split("####")[-1].strip().replace(",", "")


def format_number(x):
    x = float(x)
    return str(int(x)) if x.is_integer() else repr(x)


def _clean(s):
    """Strip formatting that never changes the value: $, \\text{}, %, degrees, bold, trailing period."""
    s = s.strip()
    s = re.sub(r"\\(?:text|textbf|mbox|mathrm)\{([^{}]*)\}", r"\1", s)
    s = s.replace("\\$", "").replace("$", "")
    s = s.replace("\\%", "").replace("%", "")
    s = re.sub(r"\^\s*\{?\\circ\}?", "", s)
    s = s.replace("{,}", ",").replace("\\!", "").replace("\\,", "").replace("\\;", "")
    s = s.replace("**", "")
    s = s.strip().rstrip(".").strip()
    return s


def to_number(s):
    """Parse s as a single number (handles 1,200 / $18 / 3/4 / \\frac{3}{4} / '18 eggs'); else None."""
    if s is None:
        return None
    s = _clean(s)
    m = re.fullmatch(r"[a-zA-Z]\s*=\s*(.+)", s)  # "x = 5"
    if m:
        s = m.group(1).strip()
    m = re.fullmatch(rf"({_NUM})\s+[a-zA-Z][a-zA-Z\s]*", s)  # "18 eggs per day"
    if m:
        s = m.group(1)
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    m = re.fullmatch(r"(-?)\\[dt]?frac\{(-?\d+)\}\{(-?\d+)\}", s) or re.fullmatch(r"(-?)(-?\d+)\s*/\s*(-?\d+)", s)
    if m:
        num, den = int(m.group(2)), int(m.group(3))
        if den == 0:
            return None
        return (-1 if m.group(1) else 1) * num / den
    try:
        return float(s)
    except ValueError:
        return None


def normalize_latex(s):
    """Canonical string form for symbolic answers (MATH-style LaTeX)."""
    s = _clean(s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = re.sub(r"^[a-zA-Z]\s*=\s*", "", s)
    s = re.sub(r"\\sqrt(\w)", r"\\sqrt{\1}", s)
    s = re.sub(r"\\frac(\d)(\d)", r"\\frac{\1}{\2}", s)
    s = s.replace(" ", "")
    s = re.sub(r"(?<!\d)\.(\d)", r"0.\1", s)
    return s


def _math_verify(pred, gold):
    try:
        from math_verify import parse, verify
    except ImportError:
        return False
    try:
        g = parse(f"${gold}$", **_MV_KW)
        p = parse(f"${pred}$", **_MV_KW)
        return bool(g and p and verify(g, p, **_MV_VERIFY_KW))
    except Exception:
        return False


def is_equiv(pred, gold, use_math_verify=True):
    if pred is None or gold is None or not str(pred).strip():
        return False
    a, b = to_number(pred), to_number(gold)
    if a is not None and b is not None:
        return abs(a - b) <= 1e-6 * max(1.0, abs(b))
    if normalize_latex(pred) == normalize_latex(gold):
        return True
    return use_math_verify and _math_verify(pred, gold)


def grade(response, gold):
    pred, source = extract_answer(response)
    return {"pred": pred, "source": source, "correct": is_equiv(pred, gold)}
