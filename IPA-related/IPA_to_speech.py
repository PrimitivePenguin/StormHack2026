import requests

url = "http://127.0.0.1:8880/dev/generate_from_phonemes"

headers = {
    "accept": "*/*",
    "Content-Type": "application/json",
}

payload = {
    "phonemes": "fʌk ju ˈæləks",
    "voice": "bf_alice(1)+bf_emma(2)",
}

response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()  # raise an error if the request failed

with open("output.wav", "wb") as f:
    f.write(response.content)

print("Saved to output.wav")