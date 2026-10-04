#!/usr/bin/env bash
# One-time setup: venv + Python packages + brainrot model registered in Ollama.
# Usage (from anywhere):  ./setup.sh
# Works on Linux, macOS, and Windows via Git Bash / WSL.
set -euo pipefail

cd "$(dirname "$0")"

GGUF_PATH="models/brainrot.gguf"
HF_PAGE="https://huggingface.co/PrimitivePenguin/brainrot-qwen3-4b-GGUF/tree/main"

ok()   { printf '  [ok]   %s\n' "$1"; }
warn() { printf '  [warn] %s\n' "$1"; }
fail() { printf '  [fail] %s\n' "$1"; exit 1; }

echo "==> Checking required tools"
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
[ -n "$PYTHON" ] || fail "Python 3.10-3.12 not found (https://www.python.org/downloads/)"
ok "Python: $($PYTHON --version)"

command -v ollama >/dev/null 2>&1 && ok "Ollama found" \
    || fail "Ollama not found (https://ollama.com/download)"
command -v docker >/dev/null 2>&1 && ok "Docker found" \
    || warn "Docker not found - needed for the Kokoro TTS server (https://docs.docker.com/get-docker/)"

echo "==> Creating virtual environment (.venv)"
[ -d .venv ] || "$PYTHON" -m venv .venv
# Linux/macOS use bin/, Windows (Git Bash) uses Scripts/
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; else source .venv/Scripts/activate; fi
ok "venv active"

echo "==> Installing Python packages"
python -m pip install --upgrade pip
pip install -r requirements.txt
ok "packages installed"

echo "==> Checking the brainrot GGUF model"
if [ ! -f "$GGUF_PATH" ]; then
    # Accept a GGUF with a different name and rename it to what the Modelfile expects
    others=(models/*.gguf)
    if [ -e "${others[0]}" ] && [ "${#others[@]}" -eq 1 ]; then
        mv "${others[0]}" "$GGUF_PATH"
        ok "renamed ${others[0]} -> $GGUF_PATH"
    else
        fail "Missing $GGUF_PATH. Download the .gguf from $HF_PAGE, put it in models/, then rerun ./setup.sh"
    fi
fi
ok "found $GGUF_PATH"

echo "==> Registering the model with Ollama"
if ! ollama list >/dev/null 2>&1; then
    warn "Ollama is not running, starting 'ollama serve' in the background"
    ollama serve >/dev/null 2>&1 &
    sleep 3
fi
(cd models && ollama create brainrot -f Modelfile)
ollama list | grep -q '^brainrot' && ok "brainrot registered" || fail "brainrot missing from 'ollama list'"

if [ ! -f .env ]; then
    echo "GEMINI_API_KEY=paste-your-key-here" > .env
    warn "Created .env - put your Gemini API key in it (https://aistudio.google.com/apikey)"
fi

echo
echo "Setup done. Start everything with: ./run.sh"