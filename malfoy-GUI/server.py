import os
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure the folder where audio files will be stored
UPLOAD_FOLDER = "./malfoy-GUI/resources/audio/"
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if the file extension is a supported audio format."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    # Check if the post request has the file part
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file part in the request"}), 400
    
    file = request.files['audio']
    
    # If the user does not select a file, the browser submits an empty file without a filename
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        # secure_filename prevents directory traversal vulnerabilities (e.g., ../../etc/passwd)
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file to the local folder
        file.save(file_path)
        
        return jsonify({
            "message": "Audio file uploaded successfully!",
            "filename": filename,
            "saved_to": file_path
        }), 200
        
    return jsonify({"error": "Invalid file type. Supported formats: MP3, WAV, OGG, M4A, FLAC"}), 400

if __name__ == '__main__':
    # Start the local development server on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
