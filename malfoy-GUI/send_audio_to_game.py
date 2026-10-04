import requests

# The URL matching the Flask server configuration
url = "http://localhost:5000/upload-audio"

# Path to the local audio file you want to send
file_path = "output.wav"

try:
    with open(file_path, "rb") as audio_file:
        # The key name 'audio' must match what request.files['audio'] looks for
        files = {"audio": (file_path, audio_file, "audio/wav")}
        
        response = requests.post(url, files=files)
        
    print(f"Status Code: {response.status_code}")
    print("Response Data:", response.json())

except Exception as e:
    print(f"An error occurred: {e}")
