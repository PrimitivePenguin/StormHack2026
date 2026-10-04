import requests

def to_phonemes(text, language = "a", url = "http://127.0.0.1:8880/dev/phonemize", filepath="./output.txt")
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "language": language
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # raise an error if the request failed

    with open(filepath, "wb") as f:
        f.write(response.content)

    print(f"Saved to {filepath}")