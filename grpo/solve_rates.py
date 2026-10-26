"""How often the base model solves each GSM8K training problem (8 samples, training settings).

  python -m grpo.solve_rates --model Qwen/Qwen2.5-1.5B-Instruct --shard 0 --num-shards 2 --out solve.0.jsonl

Problems solved 8/8 give zero advantage to every answer, so training on them only
spends compute; train.py can drop them with train_filter / filter_max_solved.
Sampling matches training: temperature 0.9, 512 tokens, same prompt and grader.
"""
import argparse
import json

from eval.answer_parse import grade
from eval.data import load_gsm8k
from eval.prompt import build_prompt


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--n", type=int, default=8)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--dtype", default="float16")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--num-shards", type=int, default=1)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    from vllm import LLM, SamplingParams

    problems = load_gsm8k("train")[a.shard :: a.num_shards][: a.limit]
    llm = LLM(model=a.model, dtype=a.dtype, gpu_memory_utilization=0.85, max_model_len=2048, seed=a.shard,
              generation_config="vllm", enable_prefix_caching=True)
    tok = llm.get_tokenizer()
    outs = llm.generate([build_prompt(tok, q["question"]) for q in problems],
                        SamplingParams(n=a.n, temperature=a.temperature, max_tokens=a.max_tokens), use_tqdm=False)
    with open(a.out, "w", encoding="utf-8") as f:
        for prob, o in zip(problems, outs):
            correct = [grade(c.text, prob["gold"])["correct"] for c in o.outputs]
            f.write(json.dumps({"id": prob["id"], "n_correct": sum(correct), "n": len(correct),
                                "avg_tokens": sum(len(c.token_ids) for c in o.outputs) / len(o.outputs),
                                "n_steps": prob["meta"]["n_steps"]}) + "\n")
    print(f"wrote {len(problems)} problems to {a.out}")


if __name__ == "__main__":
    main()
