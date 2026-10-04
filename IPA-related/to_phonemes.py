import requests

url = "http://127.0.0.1:8880/dev/phonemize"

headers = {
    "accept": "*/*",
    "Content-Type": "application/json",
}

payload = {
    "text": "fr",
    "language":"a"
}

response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()  # raise an error if the request failed

with open("output.txt", "wb") as f:
    f.write(response.content)

print("Saved to output.txt")