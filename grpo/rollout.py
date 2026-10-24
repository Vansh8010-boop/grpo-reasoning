"""Sample G answers per problem and score them (HF generate; vLLM comes in week 4).

  python -m grpo.rollout --model D:/mini-infer/models/Qwen2.5-0.5B-Instruct --n-problems 16 --out results/rollouts/base-0.5b

Sampling is plain temperature sampling: top_k and top_p are off and there is no
repetition penalty, so the tokens come from exactly the distribution whose
log-probabilities the GRPO loss will compute. (Qwen's generation_config turns
top_k=20 and a repetition penalty on by default; we override all of it.)
"""
import argparse
import json
import os
import random
import statistics
import time
from dataclasses import dataclass, field

from eval.data import load_gsm8k
from eval.prompt import build_prompt
from grpo.rewards import RewardConfig, compute_rewards


@dataclass
class Sample:
    response: str
    response_ids: list  # includes the final EOS token when the model stopped on its own
    truncated: bool
    rewards: dict = field(default_factory=dict)

    @property
    def n_tokens(self):
        return len(self.response_ids)


@dataclass
class Group:
    problem: dict
    prompt_ids: list
    samples: list


def sample_groups(model, tokenizer, prompts, group_size, temperature, max_new_tokens, batch_size):
    """For each prompt, return (prompt_ids, [(text, response_ids, truncated)] * group_size)."""
    import torch
    from transformers import GenerationConfig

    eos = model.generation_config.eos_token_id
    eos = set(eos if isinstance(eos, list) else [eos])
    gen_cfg = GenerationConfig(
        do_sample=True,
        temperature=temperature,
        top_k=0,
        top_p=1.0,
        repetition_penalty=1.0,
        max_new_tokens=max_new_tokens,
        num_return_sequences=group_size,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=sorted(eos),
    )
    tokenizer.padding_side = "left"
    out = []
    for start in range(0, len(prompts), batch_size):
        batch = prompts[start : start + batch_size]
        enc = tokenizer(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            seqs = model.generate(**enc, generation_config=gen_cfg)
        new = seqs[:, enc["input_ids"].shape[1] :].tolist()
        for p in range(len(batch)):
            prompt_ids = [t for t, m in zip(enc["input_ids"][p].tolist(), enc["attention_mask"][p].tolist()) if m]
            group = []
            for ids in new[p * group_size : (p + 1) * group_size]:
                end = next((k for k, t in enumerate(ids) if t in eos), None)
                kept = ids if end is None else ids[: end + 1]
                group.append((tokenizer.decode(kept, skip_special_tokens=True), kept, end is None))
            out.append((prompt_ids, group))
    return out


def rollout(model, tokenizer, problems, reward_cfg, group_size=8, temperature=0.9, batch_size=4):
    prompts = [build_prompt(tokenizer, p["question"]) for p in problems]
    raw = sample_groups(model, tokenizer, prompts, group_size, temperature, reward_cfg.max_tokens, batch_size)
    groups = []
    for prob, (prompt_ids, gens) in zip(problems, raw):
        samples = []
        for text, ids, truncated in gens:
            s = Sample(text, ids, truncated)
            s.rewards = compute_rewards(text, prob["gold"], s.n_tokens, truncated, reward_cfg)
            samples.append(s)
        groups.append(Group(prob, prompt_ids, samples))
    return groups


def summarize(groups):
    """Reward statistics. A group whose rewards are all equal has zero advantage everywhere: no learning signal."""
    correct = [[s.rewards["correct"] for s in g.samples] for g in groups]
    totals = [[s.rewards["total"] for s in g.samples] for g in groups]
    flat = [s for g in groups for s in g.samples]
    n = len(groups)
    return {
        "groups": n,
        "samples": len(flat),
        "accuracy": sum(map(sum, correct)) / len(flat),
        "format_rate": sum(s.rewards["format"] for s in flat) / len(flat),
        "reward_mean": statistics.mean(r for t in totals for r in t),
        "groups_all_correct": sum(all(c) for c in correct) / n,
        "groups_all_wrong": sum(not any(c) for c in correct) / n,
        "groups_mixed": sum(0 < sum(c) < len(c) for c in correct) / n,
        "groups_zero_reward_std": sum(len(set(t)) == 1 for t in totals) / n,
        "truncated_rate": sum(s.truncated for s in flat) / len(flat),
        "avg_tokens": sum(s.n_tokens for s in flat) / len(flat),
    }


def format_table(groups):
    """One row per group: per-sample correctness (1/0) and format (f/.) marks, plus total-reward mean and std."""
    lines = [
        "| problem | gold | correct per sample | format per sample | reward mean | reward std | tokens (mean) |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in groups:
        c = " ".join(str(int(s.rewards["correct"])) for s in g.samples)
        f = " ".join("f" if s.rewards["format"] else "." for s in g.samples)
        t = [s.rewards["total"] for s in g.samples]
        toks = statistics.mean(s.n_tokens for s in g.samples)
        lines.append(f"| {g.problem['id']} | {g.problem['gold']} | `{c}` | `{f}` | {statistics.mean(t):.2f} "
                     f"| {statistics.pstdev(t):.2f} | {toks:.0f} |")
    return "\n".join(lines)


def save(groups, summary, config, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "rollouts.jsonl"), "w", encoding="utf-8") as f:
        for g in groups:
            f.write(json.dumps({
                "id": g.problem["id"], "question": g.problem["question"], "gold": g.problem["gold"],
                "samples": [{"response": s.response, "n_tokens": s.n_tokens, "truncated": s.truncated,
                             "rewards": s.rewards} for s in g.samples],
            }, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"config": config, "summary": summary}, f, indent=2)
    with open(os.path.join(out_dir, "table.md"), "w", encoding="utf-8") as f:
        f.write(format_table(groups) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--n-problems", type=int, default=16)
    p.add_argument("--group-size", type=int, default=8)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--batch-size", type=int, default=4, help="problems per generate call (x group size sequences)")
    p.add_argument("--dtype", default="bfloat16")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(a.seed)
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=getattr(torch, a.dtype), device_map="cuda").eval()
    problems = random.Random(a.seed).sample(load_gsm8k("train"), a.n_problems)

    t = time.time()
    groups = rollout(model, tok, problems, RewardConfig(max_tokens=a.max_tokens), a.group_size, a.temperature, a.batch_size)
    summary = summarize(groups)
    summary["seconds"] = round(time.time() - t, 1)
    save(groups, summary, vars(a), a.out)
    print(format_table(groups))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
