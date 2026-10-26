"""GRPO training loop with LoRA.

  python -m grpo.train --config configs/grpo-0.5b.yaml
  python -m grpo.train --config configs/grpo-0.5b.yaml --set steps=20 run_name=smoke

One step:
  1. sample problems_per_step GSM8K train problems, generate group_size answers each
  2. score them (grpo/rewards.py) and turn rewards into group-relative advantages
  3. one optimizer step on the clipped policy loss + KL penalty, accumulated over micro-batches

The reference model is the base model: the same weights with the LoRA adapter
switched off, so it costs no extra memory. Re-running the same command resumes
from <out_dir>/<run_name>/ckpt-latest.

rollout_backend=vllm generates on a second GPU (grpo/vllm_worker.py) with the
adapter saved after the previous step; hf generates with the training model itself.
"""
import argparse
import dataclasses
import functools
import json
import math
import os
import random
import re
import time
from dataclasses import dataclass, field

import torch
import yaml

from eval.answer_parse import grade
from eval.data import load_gsm8k
from eval.prompt import build_prompt
from grpo.advantages import group_advantages
from grpo.loss import build_batch, grpo_loss, token_logprobs
from grpo.rewards import RewardConfig
from grpo.rollout import rollout, sample_groups, summarize

# Characters outside ASCII and common math symbols. A rising share of answers full of these is the
# early sign of the collapse seen at lr 3e-5 (docs/week3.md); greedy validation does not show it.
NON_MATH = re.compile(r"[^\x00-\x7F°×÷−–—’“”…√π∞≤≥≠·]")
SELF_CHECK = re.compile(r"\b(wait|let me (?:verify|check|double[- ]check|re-?check)|double[- ]check|verify)\b", re.I)


@dataclass
class TrainConfig:
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    run_name: str = "grpo-0.5b"
    out_dir: str = "checkpoints"
    dtype: str = "bfloat16"  # float16 on T4
    seed: int = 0
    steps: int = 300
    # rollouts
    problems_per_step: int = 16
    group_size: int = 8
    temperature: float = 0.9
    max_tokens: int = 512
    gen_batch_size: int = 16  # problems per generate call (hf backend)
    rollout_backend: str = "hf"  # "hf" or "vllm"
    vllm_gpu: int = 1
    vllm_gpu_mem: float = 0.85
    # training problems: optionally drop ones the base model already always solves
    train_filter: str = ""  # jsonl from grpo/solve_rates.py
    filter_max_solved: int = 8  # drop problems the base model solved >= this many times out of 8
    # optimization
    micro_batch_size: int = 4  # answers per forward/backward
    lr: float = 1e-5
    warmup_steps: int = 10
    max_grad_norm: float = 1.0
    clip_eps: float = 0.2
    kl_beta: float = 0.04
    normalize_std: bool = True
    skip_zero_std_groups: bool = False  # drop groups whose answers all got the same reward (zero advantage)
    gradient_checkpointing: bool = True
    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    lora_targets: list = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    # rewards
    correct_weight: float = 1.0
    format_weight: float = 0.2
    length_weight: float = 0.0
    # eval / saving
    eval_every: int = 50
    val_size: int = 500
    val_batch_size: int = 64
    save_every: int = 50
    samples_every: int = 50  # dump a step's rollouts for reading (reward hacking hunt)
    wandb_project: str = ""

    @property
    def run_dir(self):
        return os.path.join(self.out_dir, self.run_name)


def load_config(path, overrides):
    cfg = TrainConfig(**(yaml.safe_load(open(path)) if path else {}))
    for kv in overrides:
        k, v = kv.split("=", 1)
        t = type(getattr(cfg, k))  # AttributeError on a typo, which is what we want
        if t is bool:
            v = v.lower() in ("1", "true", "yes")
        elif t is list:
            v = v.split(",")
        else:
            v = t(v)
        setattr(cfg, k, v)
    return cfg


def load_policy(cfg):
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(cfg.model)
    model = AutoModelForCausalLM.from_pretrained(cfg.model, dtype=getattr(torch, cfg.dtype), device_map="cuda")
    if cfg.gradient_checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    lora = LoraConfig(r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout,
                      target_modules=cfg.lora_targets, task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)  # adapters are kept in fp32 even on an fp16/bf16 base
    return model, tok


def make_generator(cfg, model, tok):
    """Returns (generate, close). generate has sample_groups' signature minus model and tokenizer."""
    if cfg.rollout_backend == "hf":
        return functools.partial(sample_groups, model, tok), lambda: None
    from grpo.vllm_worker import VLLMWorker

    worker = VLLMWorker(cfg.model, gpu=cfg.vllm_gpu, dtype=cfg.dtype, gpu_mem=cfg.vllm_gpu_mem,
                        max_lora_rank=cfg.lora_r, seed=cfg.seed)
    adapter_dir = os.path.join(cfg.run_dir, "rollout-adapter")
    eos = model.generation_config.eos_token_id
    eos = eos if isinstance(eos, list) else [eos]
    calls = [0]

    def generate(prompts, n, temperature, max_tokens, batch_size=None):
        model.save_pretrained(adapter_dir)  # current weights -> vLLM, under a new LoRA id
        calls[0] += 1
        prompt_ids = [tok(p, add_special_tokens=False)["input_ids"] for p in prompts]
        out = worker.generate(prompt_ids, n, temperature, max_tokens, adapter_dir, calls[0])
        fixed = []
        for group in out:
            # The training loss must see the EOS token the model stopped on; add it if vLLM left it out.
            fixed.append([(t, ids if trunc or (ids and ids[-1] in eos) else ids + [eos[0]], trunc)
                          for t, ids, trunc in group])
        return list(zip(prompt_ids, fixed))

    return generate, worker.close


def validate(generate, tok, problems, cfg, step):
    """Greedy accuracy on held-out GSM8K train problems (for picking checkpoints, never the test set).

    Per-problem results go to val-<step>.jsonl so checkpoints can be compared problem by problem.
    """
    prompts = [build_prompt(tok, p["question"]) for p in problems]
    outs = generate(prompts, 1, 0.0, cfg.max_tokens, cfg.val_batch_size)
    gens = [g[0] for _, g in outs]
    correct = [grade(t, p["gold"])["correct"] for p, (t, _, _) in zip(problems, gens)]
    with open(os.path.join(cfg.run_dir, f"val-{step:04d}.jsonl"), "w", encoding="utf-8") as f:
        for p, (t, ids, tr), c in zip(problems, gens, correct):
            f.write(json.dumps({"id": p["id"], "gold": p["gold"], "correct": c, "n_tokens": len(ids),
                                "truncated": tr, "response": t}, ensure_ascii=False) + "\n")
    return {
        "val_accuracy": sum(correct) / len(problems),
        "val_avg_tokens": sum(len(ids) for _, ids, _ in gens) / len(gens),
        "val_truncated": sum(tr for _, _, tr in gens) / len(gens),
    }


def train_step(model, tok, groups, cfg, optimizer, scaler):
    """One optimizer step over all answers in groups. Returns loss/KL/clip stats."""
    rewards = [[s.rewards["total"] for s in g.samples] for g in groups]
    adv = group_advantages(rewards, normalize_std=cfg.normalize_std)
    keep = [i for i, r in enumerate(rewards) if not (cfg.skip_zero_std_groups and len(set(r)) == 1)]
    items = [(groups[i].prompt_ids, s.response_ids, adv[i, j].item())
             for i in keep for j, s in enumerate(groups[i].samples)]
    if not items:  # every group had zero spread: nothing to learn from this batch
        return {"loss": 0.0, "kl": 0.0, "clip_frac": 0.0, "grad_norm": 0.0, "adv_abs_mean": 0.0, "groups_trained": 0}
    items.sort(key=lambda x: len(x[0]) + len(x[1]))  # similar lengths per micro-batch -> less padding

    model.train()
    optimizer.zero_grad(set_to_none=True)
    totals = {"loss": 0.0, "kl_sum": 0.0, "clipped_tokens": 0.0, "tokens": 0.0}
    n = len(items)
    for k in range(0, n, cfg.micro_batch_size):
        mb = items[k : k + cfg.micro_batch_size]
        ids, attn, pos, mask = build_batch([m[0] for m in mb], [m[1] for m in mb], tok.pad_token_id, "cuda")
        a = torch.tensor([m[2] for m in mb], device="cuda")
        R = mask.shape[1]
        with torch.no_grad(), model.disable_adapter():
            ref = token_logprobs(model, ids, attn, pos, R)
        logp = token_logprobs(model, ids, attn, pos, R)
        # One optimizer step per batch of rollouts, so the "old" policy is the current one:
        # the ratio is exactly 1 with gradient d(ratio) = d(logp), as in GRPO with mu = 1.
        loss, st = grpo_loss(logp, logp.detach(), ref, a, mask, cfg.clip_eps, cfg.kl_beta)
        scaler.scale(loss.sum() / n).backward()
        totals["loss"] += loss.sum().item()
        for key in ("kl_sum", "clipped_tokens", "tokens"):
            totals[key] += st[key]
    scaler.unscale_(optimizer)
    params = [p for p in model.parameters() if p.requires_grad]
    grad_norm = torch.nn.utils.clip_grad_norm_(params, cfg.max_grad_norm).item()
    scaler.step(optimizer)
    scaler.update()
    return {
        "loss": totals["loss"] / n,
        "kl": totals["kl_sum"] / n,
        "clip_frac": totals["clipped_tokens"] / max(totals["tokens"], 1),
        "grad_norm": grad_norm,
        "adv_abs_mean": adv.abs().mean().item(),
        "groups_trained": len(keep),
    }


def save_checkpoint(model, optimizer, scaler, scheduler, step, cfg, keep_adapter):
    latest = os.path.join(cfg.run_dir, "ckpt-latest")
    model.save_pretrained(latest)
    torch.save({"step": step, "optimizer": optimizer.state_dict(), "scaler": scaler.state_dict(),
                "scheduler": scheduler.state_dict(), "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state()}, os.path.join(latest, "trainer_state.pt"))
    if keep_adapter:
        model.save_pretrained(os.path.join(cfg.run_dir, f"ckpt-{step:04d}"))


def maybe_resume(model, optimizer, scaler, scheduler, cfg):
    latest = os.path.join(cfg.run_dir, "ckpt-latest")
    state_path = os.path.join(latest, "trainer_state.pt")
    if not os.path.exists(state_path):
        return 0
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    set_peft_model_state_dict(model, load_file(os.path.join(latest, "adapter_model.safetensors")))
    st = torch.load(state_path, weights_only=False)
    optimizer.load_state_dict(st["optimizer"])
    scaler.load_state_dict(st["scaler"])
    scheduler.load_state_dict(st["scheduler"])
    torch.set_rng_state(st["torch_rng"])
    torch.cuda.set_rng_state(st["cuda_rng"])
    print(f"resumed from step {st['step']}", flush=True)
    return st["step"]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--set", nargs="*", default=[], help="override config fields, e.g. steps=20 lr=2e-5")
    args = p.parse_args(argv)
    cfg = load_config(args.config, args.set)
    os.makedirs(cfg.run_dir, exist_ok=True)
    with open(os.path.join(cfg.run_dir, "config.yaml"), "w") as f:
        yaml.safe_dump(dataclasses.asdict(cfg), f, sort_keys=False)

    random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)
    model, tok = load_policy(cfg)
    model.print_trainable_parameters()
    reward_cfg = RewardConfig(cfg.correct_weight, cfg.format_weight, cfg.length_weight, cfg.max_tokens)

    train = load_gsm8k("train")
    if cfg.train_filter:
        solved = {r["id"]: r["n_correct"] for r in map(json.loads, open(cfg.train_filter))}
        before = len(train)
        train = [p for p in train if solved[p["id"]] < cfg.filter_max_solved]
        print(f"train filter: kept {len(train)} of {before} problems", flush=True)
    order = list(range(len(train)))
    random.Random(cfg.seed).shuffle(order)  # step k always gets the same problems, so resuming needs no data state
    val = load_gsm8k("val")[: cfg.val_size]

    params = [q for q in model.parameters() if q.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=cfg.lr, weight_decay=0.0)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda s: min(1.0, (s + 1) / max(cfg.warmup_steps, 1)))
    scaler = torch.amp.GradScaler("cuda", enabled=cfg.dtype == "float16")
    start = maybe_resume(model, optimizer, scaler, scheduler, cfg)

    wandb = None
    if cfg.wandb_project:
        import wandb

        wandb.init(project=cfg.wandb_project, name=cfg.run_name, id=cfg.run_name, resume="allow",
                   config=dataclasses.asdict(cfg))
    metrics_path = os.path.join(cfg.run_dir, "metrics.jsonl")
    generate, close_generator = make_generator(cfg, model, tok)

    def log(row):
        with open(metrics_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        if wandb:
            wandb.log(row, step=row["step"])

    if start == 0 and cfg.eval_every:
        t = time.time()
        log({"step": 0, **validate(generate, tok, val, cfg, 0), "val_seconds": round(time.time() - t, 1)})

    for step in range(start + 1, cfg.steps + 1):
        idx = [order[(i) % len(order)] for i in range((step - 1) * cfg.problems_per_step, step * cfg.problems_per_step)]
        problems = [train[i] for i in idx]

        t0 = time.time()
        model.eval()
        groups = rollout(generate, tok, problems, reward_cfg, cfg.group_size, cfg.temperature, cfg.gen_batch_size)
        t1 = time.time()
        stats = train_step(model, tok, groups, cfg, optimizer, scaler)
        scheduler.step()
        t2 = time.time()

        roll = summarize(groups)
        flat = [s for g in groups for s in g.samples]
        row = {
            "step": step,
            "reward": roll["reward_mean"],
            "accuracy": roll["accuracy"],
            "format_rate": roll["format_rate"],
            "groups_mixed": roll["groups_mixed"],
            "groups_zero_std": roll["groups_zero_reward_std"],
            "truncated": roll["truncated_rate"],
            "avg_tokens": roll["avg_tokens"],
            "self_check_rate": sum(bool(SELF_CHECK.search(s.response)) for s in flat) / len(flat),
            "garbage_rate": sum(len(NON_MATH.findall(s.response)) > 5 for s in flat) / len(flat),
            **stats,
            "lr": scheduler.get_last_lr()[0],
            "gen_seconds": round(t1 - t0, 1),
            "train_seconds": round(t2 - t1, 1),
        }
        if not all(math.isfinite(v) for v in (row["loss"], row["kl"], row["grad_norm"])):
            print(f"non-finite values at step {step}: {row}", flush=True)
        if cfg.samples_every and step % cfg.samples_every == 0:
            with open(os.path.join(cfg.run_dir, f"samples-{step:04d}.jsonl"), "w", encoding="utf-8") as f:
                for g in groups:
                    for s in g.samples:
                        f.write(json.dumps({"id": g.problem["id"], "gold": g.problem["gold"], "response": s.response,
                                            "rewards": s.rewards, "n_tokens": s.n_tokens}, ensure_ascii=False) + "\n")
        if cfg.eval_every and step % cfg.eval_every == 0:
            t = time.time()
            model.eval()
            row.update(validate(generate, tok, val, cfg, step), val_seconds=round(time.time() - t, 1))
        log(row)
        print(f"step {step:4d} reward {row['reward']:.3f} acc {row['accuracy']:.3f} kl {row['kl']:.4f} "
              f"len {row['avg_tokens']:.0f} mixed {row['groups_mixed']:.2f} gnorm {row['grad_norm']:.3f} "
              f"gen {row['gen_seconds']}s train {row['train_seconds']}s"
              + (f" | val {row['val_accuracy']:.3f}" if "val_accuracy" in row else ""), flush=True)
        if step % cfg.save_every == 0 or step == cfg.steps:
            save_checkpoint(model, optimizer, scaler, scheduler, step, cfg, keep_adapter=True)

    close_generator()
    if wandb:
        wandb.finish()


if __name__ == "__main__":
    main()
