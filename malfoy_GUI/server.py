import os
from flask import Flask, request, jsonify

app = Flask(__name__)

UPLOAD_FOLDER = "./malfoy_GUI/audio/"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20 MB

audio_buffer_available = True

def detect_audio_format(data):
    """Return the detected audio format, or None if invalid."""

    # MP3
    if data.startswith(b"ID3"):
        return "mp3"

    # MP3 without ID3 metadata
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"

    # WAV / RIFF
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"

    # OGG
    if data.startswith(b"OggS"):
        return "ogg"

    # FLAC
    if data.startswith(b"fLaC"):
        return "flac"

    # M4A / MP4
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "m4a"

    return None


@app.route('/upload-audio', methods=['POST'])
def upload_audio():

    # --------------------------------------------------
    # 1. Get raw bytes
    # --------------------------------------------------

    audio_data = request.get_data()

    if not audio_data:
        return jsonify({
            "error": "No audio data received"
        }), 400

    # --------------------------------------------------
    # 2. Check file size
    # --------------------------------------------------

    if len(audio_data) > MAX_AUDIO_SIZE:
        return jsonify({
            "error": "Audio file is too large",
            "max_size": MAX_AUDIO_SIZE
        }), 413

    # --------------------------------------------------
    # 3. Check Content-Type
    # --------------------------------------------------

    allowed_content_types = {
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/ogg": "ogg",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/flac": "flac",
    }

    content_type = request.content_type

    if content_type not in allowed_content_types:
        return jsonify({
            "error": "Unsupported Content-Type",
            "received": content_type
        }), 400

    # --------------------------------------------------
    # 4. Validate actual bytes
    # --------------------------------------------------

    detected_format = detect_audio_format(audio_data)

    if detected_format is None:
        return jsonify({
            "error": "Invalid or corrupted audio data"
        }), 400

    expected_format = allowed_content_types[content_type]

    if detected_format != expected_format:
        return jsonify({
            "error": "Content-Type does not match audio data",
            "content_type": content_type,
            "detected_format": detected_format
        }), 400

    # --------------------------------------------------
    # 5. Save file
    # --------------------------------------------------

    filename = request.headers.get("X-Filename")

    if not filename:
        filename = f"audio.{detected_format}"

    # Prevent directory traversal
    filename = os.path.basename(filename)

    file_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    with open(file_path, "wb") as f:
        f.write(audio_data)

    global audio_buffer_available
    audio_buffer_available = False

    # --------------------------------------------------
    # 6. Return result
    # --------------------------------------------------

    return jsonify({
        "message": "Audio file uploaded successfully!",
        "filename": filename,
        "format": detected_format,
        "size": len(audio_data),
        "saved_to": file_path
    }), 200

@app.route("/audio-finished-playing", methods=["POST"])
def audio_finished_playing():
    global audio_buffer_available
    audio_buffer_available = True

    return jsonify({
        "message": "Game finished reading the audio"
    }), 200

@app.route("/audio-buffer-status", methods=["GET"])
def audio_buffer_status():
    return jsonify({
        "status": int(audio_buffer_available)
    })

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )