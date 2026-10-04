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



Terminal 1:
```
docker run --rm -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

Terminal 2: Draco assistant
```
cd path\to\StormHack2026
.\.venv\Scripts\Activate.ps1
python front_end\draco_speech_recognition.py
```

Terminal 3: audio upload optional (need fix)

Terminal 4: Malfoy GUI (needs fix)


Finish: Ctrl + c in all