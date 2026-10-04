import sys
import requests
from pathlib import Path

# SYSTEM_PROMPT must be identical to the one used in training
sys.path.append(str(Path(__file__).resolve().parents[2] / "src_brainrot"))
from shared import SYSTEM_PROMPT


def brainrotify(text, model = "brainrot", url = "http://127.0.0.1:11434/api/generate"):
    # Build exactly the string the model saw in training (Qwen3 chat format, thinking off)
    prompt = (f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
              f"<|im_start|>user\n{text}<|im_end|>\n"
              f"<|im_start|>assistant\n<think>\n\n</think>\n\n")

    try:
        response = requests.post(url, json = {
            "model": model,
            "prompt": prompt,
            "raw": True,             # send the prompt as is, don't let Ollama re-template it
            "stream": False,         # wait for the full answer
            "keep_alive": "60m",     # keep the model loaded on the GPU between requests
            "options": {"num_predict": 80, "stop": ["<|im_end|>"]},
        }, timeout = 60)
        response.raise_for_status()
        return response.json()["response"].strip()

    except requests.RequestException as e:
        # Ollama down or model missing: fall back to the plain text so the pipeline keeps talking
        print(f"brainrotify failed ({e}), using original text", file = sys.stderr)
        return text


if __name__ == "__main__":
    print(brainrotify(" ".join(sys.argv[1:]) or "I am going to the store."))