import requests


def upload_audio(data, content_type = "audio/wav", url="http://localhost:5000/upload-audio"):
    response = requests.post(
        url,
        data=data,
        headers={
            "Content-Type": content_type
        }
    )

    response.raise_for_status()

    return response.json()