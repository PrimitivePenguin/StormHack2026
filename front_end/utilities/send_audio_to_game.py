import requests

def upload_audio(audio_bytes, url="http://127.0.0.1:5000/upload-audio", content_type="audio/wav"):
    response = requests.post(
        url,
        data=audio_bytes,
        headers={"Content-Type": content_type},
        timeout=10,
    )
    response.raise_for_status()