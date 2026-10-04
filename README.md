1. Fine-tune a model
2. TTS
3. Evaluation


### Setup:
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

### Huggingface Model setup
https://huggingface.co/PrimitivePenguin/brainrot-qwen3-4b-GGUF/tree/main

Download the model (Based off of Qwen3-4B with QLoRA setup)


1. Put the GGUF next to the Modelfile, with this exact name:

StormHack2026\models\
├── Modelfile          ← already in git
└── brainrot.gguf      ← your 2.3 GB file (not in git)

The name must match the Modelfile's first line, ```FROM ./brainrot.gguf```. If your file is called something else, like Qwen3-4B.Q4_K_M.gguf, rename it to match it.

2. Register it:
```
cd path\to\StormHack2026\models
ollama create brainrot -f Modelfile
```
Spelling is important

3. Check it's registered:
```
ollama list
```
If registered, brainrot:latest should be in the list.

4. Check it works:
```
cd ..
python front_end\brainrot\run_model.py I am going to the store.
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