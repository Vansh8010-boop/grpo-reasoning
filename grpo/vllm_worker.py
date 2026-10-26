"""vLLM generation in a separate process on its own GPU.

The trainer (GPU 0) saves the current LoRA adapter to disk before each rollout;
the worker (GPU 1) loads it as a new LoRA request (a fresh id each step, so vLLM
never reuses a stale copy) and samples with it. Prompts are sent as token ids so
both processes see exactly the same tokens.

Sampling settings match grpo/rollout.py: plain temperature sampling, no top-k,
top-p or repetition penalty, and the model's own generation_config ignored.
"""
import multiprocessing as mp
import os
import traceback


def _serve(conn, gpu, model, dtype, gpu_mem, max_model_len, max_lora_rank, seed):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)  # before vLLM touches CUDA
    try:
        from vllm import LLM, SamplingParams
        from vllm.inputs import TokensPrompt
        from vllm.lora.request import LoRARequest

        llm = LLM(model=model, dtype=dtype, gpu_memory_utilization=gpu_mem, max_model_len=max_model_len,
                  enable_lora=True, max_lora_rank=max_lora_rank, max_loras=1, seed=seed,
                  generation_config="vllm", enable_prefix_caching=True)
        conn.send(("ready", None))
    except Exception:
        conn.send(("error", traceback.format_exc()))
        return
    while True:
        msg = conn.recv()
        if msg is None:
            break
        prompt_ids, n, temperature, max_tokens, adapter, lora_id = msg
        try:
            sp = SamplingParams(n=n, temperature=temperature, max_tokens=max_tokens)
            lora = LoRARequest(f"adapter-{lora_id}", lora_id, adapter) if adapter else None
            outs = llm.generate([TokensPrompt(prompt_token_ids=p) for p in prompt_ids], sp,
                                lora_request=lora, use_tqdm=False)
            conn.send(("ok", [[(c.text, list(c.token_ids), c.finish_reason == "length") for c in o.outputs]
                              for o in outs]))
        except Exception:
            conn.send(("error", traceback.format_exc()))


class VLLMWorker:
    def __init__(self, model, gpu=1, dtype="float16", gpu_mem=0.85, max_model_len=2048, max_lora_rank=16, seed=0):
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        # Not a daemon: vLLM starts its own engine process, which daemons may not do.
        self.proc = ctx.Process(target=_serve, args=(child, gpu, model, dtype, gpu_mem, max_model_len, max_lora_rank, seed))
        self.proc.start()
        self._check(self.conn.recv())

    @staticmethod
    def _check(reply):
        status, payload = reply
        if status == "error":
            raise RuntimeError("vLLM worker failed:\n" + payload)
        return payload

    def generate(self, prompt_ids, n, temperature, max_tokens, adapter=None, lora_id=0):
        """Returns, per prompt, n tuples of (text, token_ids, truncated)."""
        self.conn.send((prompt_ids, n, temperature, max_tokens, adapter, lora_id))
        return self._check(self.conn.recv())

    def close(self):
        if self.proc.is_alive():
            self.conn.send(None)
            self.proc.join(timeout=60)
            if self.proc.is_alive():
                self.proc.terminate()
