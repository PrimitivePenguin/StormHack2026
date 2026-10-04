1. Fine-tune a model
2. TTS
3. Evaluation


Setup:
```
cd path\to\StormHack2026

# create the venv (use 3.12 if you have several Pythons)
py -3.12 -m venv .venv

# allow activation scripts (only needed once per PC)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# activate: your prompt should now start with (.venv)
.\.venv\Scripts\Activate.ps1

# install packages
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install sounddevice vosk python-dotenv

# save the updated list as UTF-8 so teammates get the same packages
pip freeze | Out-File -Encoding utf8 requirements.txt
```

Running venv:
```
cd path\to\StormHack2026
.\.venv\Scripts\Activate.ps1
```

Terminal 1:
```
docker run --rm -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

Terminal 2: Malfoy GUI - open GUI the frontend
```
python malfoy_GUI/gui.py
```

Terminal 3: Server.py - Receive audio
```
python malfoy_GUI/server.py
```

Terminal 4: Draco speech recognitionassistant
```
python front_end\draco_speech_recognition.py
```

Terminal 5: Ollama

Closing: Terminal 4 -> 3 -> 2 -> 1



Finish: Ctrl + c in all