import requests

def IPA_to_speech(phonemes, voice, url = "http://127.0.0.1:8880/dev/generate_from_phonemes", filepath = "./output.wav"):
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
    }

    payload = {
        "phonemes": phonemes,
        "voice": voice,
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # raise an error if the request failed

    with open(filepath, "wb") as f:
        f.write(response.content)

    print(f"Saved to {filepath}")