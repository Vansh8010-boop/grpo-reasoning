"""Score a model on GSM8K / MATH-500 / SVAMP with one fixed prompt, parser and decoding setup.

  python -m eval.harness --model Qwen/Qwen2.5-0.5B-Instruct --out results/base-0.5b
  python -m eval.harness --model Qwen/Qwen2.5-1.5B-Instruct --adapter ckpt/step-500 --out results/grpo-1.5b
  python -m eval.harness --model ... --n-samples 4 --temperature 0.6   # pass@1 averaged over 4 samples

Writes <out>/summary.json and one <out>/<dataset>.jsonl with every response.
Use --backend hf where vLLM is unavailable (Windows); it is much slower.
"""
import argparse
import json
import os
import time

from eval.answer_parse import grade
from eval.data import LOADERS
from eval.prompt import build_prompt


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--adapter", default=None, help="LoRA adapter directory")
    p.add_argument("--datasets", default="gsm8k,math500,svamp")
    p.add_argument("--backend", choices=["vllm", "hf"], default="vllm")
    p.add_argument("--limit", type=int, default=None, help="first N problems per dataset (smoke tests)")
    p.add_argument("--n-samples", type=int, default=1)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--dtype", default="auto", help="float16 on T4 (no fast bf16)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=16, help="hf backend only")
    p.add_argument("--gpu-mem", type=float, default=0.85, help="vllm gpu_memory_utilization")
    p.add_argument("--max-model-len", type=int, default=2048)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


class VLLMBackend:
    def __init__(self, args):
        from vllm import LLM

        self.args = args
        # generation_config="vllm": ignore the model's own sampling defaults
        # (Qwen ships repetition_penalty etc.) so both backends decode identically.
        self.llm = LLM(
            model=args.model,
            dtype=args.dtype,
            seed=args.seed,
            gpu_memory_utilization=args.gpu_mem,
            max_model_len=args.max_model_len,
            enable_lora=bool(args.adapter),
            max_lora_rank=64,
            generation_config="vllm",
        )
        self.tokenizer = self.llm.get_tokenizer()

    def generate(self, prompts):
        from vllm import SamplingParams
        from vllm.lora.request import LoRARequest

        a = self.args
        sp = SamplingParams(n=a.n_samples, temperature=a.temperature, top_p=a.top_p, max_tokens=a.max_tokens, seed=a.seed)
        lora = LoRARequest("adapter", 1, a.adapter) if a.adapter else None
        outs = self.llm.generate(prompts, sp, lora_request=lora)
        return [[(c.text, len(c.token_ids), c.finish_reason == "length") for c in o.outputs] for o in outs]


class HFBackend:
    def __init__(self, args):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.args, self.torch = args, torch
        self.tokenizer = AutoTokenizer.from_pretrained(args.model)
        self.tokenizer.padding_side = "left"
        dtype = "auto" if args.dtype == "auto" else getattr(torch, args.dtype)
        model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype, device_map="cuda")
        if args.adapter:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, args.adapter)
        self.model = model.eval()
        eos = model.generation_config.eos_token_id
        self.eos = set(eos if isinstance(eos, list) else [eos])
        torch.manual_seed(args.seed)

    def generate(self, prompts):
        a, tok = self.args, self.tokenizer
        sample = a.temperature > 0
        results = []
        for start in range(0, len(prompts), a.batch_size):
            batch = prompts[start : start + a.batch_size]
            enc = tok(batch, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
            with self.torch.no_grad():
                out = self.model.generate(
                    **enc,
                    max_new_tokens=a.max_tokens,
                    do_sample=sample,
                    temperature=a.temperature if sample else None,
                    top_p=a.top_p if sample else None,
                    top_k=None,
                    repetition_penalty=1.0,
                    num_return_sequences=a.n_samples,
                    pad_token_id=tok.pad_token_id,
                )
            new = out[:, enc["input_ids"].shape[1] :].tolist()
            for p in range(len(batch)):
                group = []
                for ids in new[p * a.n_samples : (p + 1) * a.n_samples]:
                    end = next((k for k, t in enumerate(ids) if t in self.eos), None)
                    kept = ids if end is None else ids[:end]
                    group.append((tok.decode(kept, skip_special_tokens=True), len(kept), end is None))
                results.append(group)
            print(f"  {min(start + a.batch_size, len(prompts))}/{len(prompts)}", flush=True)
        return results


def score(problems, generations):
    records = []
    for prob, gens in zip(problems, generations):
        samples = []
        for text, n_tokens, truncated in gens:
            g = grade(text, prob["gold"])
            samples.append({"response": text, "n_tokens": n_tokens, "truncated": truncated, **g})
        records.append({**prob, "samples": samples, "correct": sum(s["correct"] for s in samples) / len(samples)})
    flat = [s for r in records for s in r["samples"]]
    summary = {
        "n": len(records),
        "accuracy": sum(r["correct"] for r in records) / len(records),
        "boxed_rate": sum(s["source"] == "boxed" for s in flat) / len(flat),
        "truncated_rate": sum(s["truncated"] for s in flat) / len(flat),
        "avg_tokens": sum(s["n_tokens"] for s in flat) / len(flat),
    }
    return records, summary


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    backend = (VLLMBackend if args.backend == "vllm" else HFBackend)(args)
    summary = {"config": vars(args), "datasets": {}}
    for name in args.datasets.split(","):
        problems = LOADERS[name]()[: args.limit]
        prompts = [build_prompt(backend.tokenizer, p["question"]) for p in problems]
        t = time.time()
        print(f"[{name}] generating {len(prompts)} x {args.n_samples}", flush=True)
        records, s = score(problems, backend.generate(prompts))
        s["seconds"] = round(time.time() - t, 1)
        summary["datasets"][name] = s
        with open(os.path.join(args.out, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{name}] accuracy {s['accuracy']:.4f}  boxed {s['boxed_rate']:.3f}  "
              f"truncated {s['truncated_rate']:.3f}  avg_tokens {s['avg_tokens']:.0f}  ({s['seconds']}s)", flush=True)
    summary["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
