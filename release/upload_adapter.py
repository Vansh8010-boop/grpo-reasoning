"""Upload the 0.5B GRPO adapter and its model card to the Hugging Face Hub.

  hf auth login                     # once, with a write token
  python release/upload_adapter.py --repo <your-hf-username>/qwen2.5-0.5b-grpo-gsm8k

The model card's usage example names the repo; it is rewritten to --repo before upload.
"""
import argparse
import os
import shutil
import tempfile

from huggingface_hub import HfApi


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--adapter", default="checkpoints/grpo-0.5b/ckpt-0250")
    p.add_argument("--private", action="store_true")
    a = p.parse_args()

    api = HfApi()
    api.create_repo(a.repo, repo_type="model", private=a.private, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        for f in ("adapter_config.json", "adapter_model.safetensors"):
            shutil.copy(os.path.join(a.adapter, f), d)
        card = open("release/model-card.md", encoding="utf-8").read()
        card = card.replace("Vansh8010/qwen2.5-0.5b-grpo-gsm8k", a.repo)
        open(os.path.join(d, "README.md"), "w", encoding="utf-8").write(card)
        api.upload_folder(folder_path=d, repo_id=a.repo, commit_message="GRPO LoRA adapter, step 250")
    print(f"https://huggingface.co/{a.repo}")


if __name__ == "__main__":
    main()
