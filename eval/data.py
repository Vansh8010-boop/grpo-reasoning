"""Dataset loaders. Every problem becomes {id, question, gold, meta}.

GSM8K train is split once with a fixed seed: 500 problems become the
validation set (checkpoint selection), the rest are for training. Test sets
are only for final reports.
"""
import random

from eval.answer_parse import format_number, gsm8k_gold

GSM8K_VAL_SIZE = 500
GSM8K_VAL_SEED = 0


def _gsm8k_rows(split):
    from datasets import load_dataset

    return load_dataset("openai/gsm8k", "main", split=split)


def _gsm8k_item(prefix, i, row):
    steps = [l for l in row["answer"].split("\n") if l.strip() and not l.startswith("####")]
    return {
        "id": f"{prefix}-{i}",
        "question": row["question"],
        "gold": gsm8k_gold(row["answer"]),
        "meta": {"n_steps": len(steps), "solution": row["answer"]},
    }


def gsm8k_val_indices(n_train):
    return set(random.Random(GSM8K_VAL_SEED).sample(range(n_train), GSM8K_VAL_SIZE))


def load_gsm8k(split):
    """split: 'train' (train minus val), 'val' (500 held-out train problems) or 'test'."""
    if split == "test":
        return [_gsm8k_item("gsm8k-test", i, r) for i, r in enumerate(_gsm8k_rows("test"))]
    rows = _gsm8k_rows("train")
    val = gsm8k_val_indices(len(rows))
    keep = (lambda i: i in val) if split == "val" else (lambda i: i not in val)
    return [_gsm8k_item("gsm8k-train", i, r) for i, r in enumerate(rows) if keep(i)]


def load_math500():
    from datasets import load_dataset

    return [
        {
            "id": r["unique_id"],
            "question": r["problem"],
            "gold": r["answer"],
            "meta": {"level": int(r["level"]), "subject": r["subject"]},
        }
        for r in load_dataset("HuggingFaceH4/MATH-500", split="test")
    ]


def load_svamp():
    """All 1,000 SVAMP problems (the HF copy splits them 700/300; we use both)."""
    from datasets import load_dataset

    ds = load_dataset("ChilleD/SVAMP")
    return [
        {
            "id": f"svamp-{r['ID']}",
            "question": f"{r['Body'].strip()} {r['Question'].strip()}",
            "gold": format_number(r["Answer"]),
            "meta": {"type": r["Type"]},
        }
        for split in ("train", "test")
        for r in ds[split]
    ]


LOADERS = {
    "gsm8k": lambda: load_gsm8k("test"),
    "gsm8k_val": lambda: load_gsm8k("val"),
    "math500": load_math500,
    "svamp": load_svamp,
}
