"""The one prompt template, shared by evaluation and training.

Changing it invalidates every result produced with the old one.
"""
INSTRUCTION = "Please reason step by step, and put your final answer within \\boxed{}."


def build_messages(question):
    return [{"role": "user", "content": f"{question.strip()}\n{INSTRUCTION}"}]


def build_prompt(tokenizer, question):
    return tokenizer.apply_chat_template(build_messages(question), tokenize=False, add_generation_prompt=True)
