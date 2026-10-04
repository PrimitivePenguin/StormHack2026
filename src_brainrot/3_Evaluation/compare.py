import requests
# do this later i guess

SYSTEM = "Rewrite the user's text in Gen-Z brainrot slang. Keep the meaning."

def ask(model, text):
    prompt = (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
              f"<|im_start|>user\n{text}<|im_end|>\n"
              f"<|im_start|>assistant\n<think>\n\n</think>\n\n")
    r = requests.post("http://127.0.0.1:11434/api/generate", json={
        "model": model, "prompt": prompt, "raw": True, "stream": False,
        "options": {"num_predict": 80, "stop": ["<|im_end|>"]},
    })
    return r.json()["response"].strip()

for text in ["I need to finish my homework before dinner.",
             "The weather is really nice today."]:
    print("INPUT:      ", text)
    print("qwen3:4b:   ", ask("qwen3:4b", text))
    print("brainrot:   ", ask("brainrot", text))
    print()