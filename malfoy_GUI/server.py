import threading
from flask import Flask, request, jsonify, Response
from queue import Queue

app = Flask(__name__)

MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20 MB

audio_queue = Queue()          # holds (bytes, content_type)
pending_count = 0              # clips uploaded but not yet finished playing
pending_lock = threading.Lock()


def detect_audio_format(data):
    """Return the detected audio format, or None if invalid."""
    if data.startswith(b"ID3"):
        return "mp3"
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"fLaC"):
        return "flac"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "m4a"
    return None


ALLOWED_CONTENT_TYPES = {
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/flac": "flac",
}


@app.route("/upload-audio", methods=["POST"])
def upload_audio():
    global pending_count

    audio_data = request.get_data()
    if not audio_data:
        return jsonify({"error": "No audio data received"}), 400

    if len(audio_data) > MAX_AUDIO_SIZE:
        return jsonify({"error": "Audio file is too large",
                        "max_size": MAX_AUDIO_SIZE}), 413

    content_type = request.mimetype  # ignores "; charset=..." etc.
    if content_type not in ALLOWED_CONTENT_TYPES:
        return jsonify({"error": "Unsupported Content-Type",
                        "received": content_type}), 400

    detected_format = detect_audio_format(audio_data)
    if detected_format is None:
        return jsonify({"error": "Invalid or corrupted audio data"}), 400

    if detected_format != ALLOWED_CONTENT_TYPES[content_type]:
        return jsonify({"error": "Content-Type does not match audio data",
                        "content_type": content_type,
                        "detected_format": detected_format}), 400

    with pending_lock:
        pending_count += 1
    audio_queue.put((audio_data, content_type))

    return jsonify({"message": "Audio received"}), 200


@app.route("/next-audio", methods=["GET"])
def next_audio():
    if audio_queue.empty():
        return "", 204

    audio_data, content_type = audio_queue.get()
    return Response(audio_data, status=200, content_type=content_type)


@app.route("/audio-finished-playing", methods=["POST"])
def audio_finished_playing():
    global pending_count
    with pending_lock:
        pending_count = max(0, pending_count - 1)

    return jsonify({"message": "Game finished reading the audio"}), 200


@app.route("/audio-buffer-status", methods=["GET"])
def audio_buffer_status():
    with pending_lock:
        available = pending_count == 0
    return jsonify({"status": int(available)})


if __name__ == "__main__":
    # use_reloader=False: the reloader would start two processes with separate in-memory queues
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)