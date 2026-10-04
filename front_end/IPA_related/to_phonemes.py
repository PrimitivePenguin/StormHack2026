import re
import json
import requests

def text_to_phonemes(text, language = "a", url = "http://127.0.0.1:8880/dev/phonemize", filepath=None):
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
    }

    # 1. Split text safely into sentences using regex to respect Kokoro's token limits
    chunks = re.split(r'(?<=[.!?])\s+', text)
    chunks = [c.strip() for c in chunks if c.strip()]

    combined_phonemes = []
    combined_tokens = []

    # 2. Iterate through each chunk sequentially and send individual API requests
    for chunk in chunks:
        payload = {
            "text": chunk,
            "language": language
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # raise an error if the request failed
        
        # Parse the JSON response from Kokoro-FastAPI
        data = response.json()
        
        if "phonemes" in data:
            combined_phonemes.append(data["phonemes"])
        if "tokens" in data:
            combined_tokens.extend(data["tokens"])

    # 3. Stitch the parts back into the unified JSON schema structure
    final_data = {
        "phonemes": " ".join(combined_phonemes),
        "tokens": combined_tokens
    }
    
    # 4. Convert back to raw bytes to preserve your original file writing/return logic
    final_content = json.dumps(final_data, ensure_ascii=False).encode('utf-8')

    if filepath:
        with open(filepath, "wb") as f:
            f.write(final_content)

    return final_content
