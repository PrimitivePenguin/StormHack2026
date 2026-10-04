from utilities.counter import Counter
from utilities.send_audio_to_game import upload_audio
from gemini.run_model import get_response
from IPA_related.IPA_to_speech import IPA_to_speech
from IPA_related.to_phonemes import text_to_phonemes

import sys
import time
import json
import queue
import threading
import requests
import sounddevice as sd

from vosk import Model, KaldiRecognizer
from dotenv import load_dotenv
from gemini.run_model import get_response
from brainrot.run_model import brainrotify

load_dotenv()

AUDIO_STATUS_URL = "http://127.0.0.1:5000/audio-buffer-status"
RESET = object()  # marker pushed into the audio queue when muting starts


class Draco:
    def __init__(
        self,
        model_name = "vosk-model-en-us-0.22-lgraph", #-lgraph
        model_path = None,  # folder containing the model
        lang="en-us",
        samplerate=16000,
        blocksize=4000,
        channels=1,
        callback=None,
        listening_timeout=60 * 30,
        status_url=AUDIO_STATUS_URL,
        status_poll_interval=0.05,
        unmute_delay=0.4,
        max_backlog_blocks=40,  # ~10 s of audio at blocksize=4000
    ):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback

        print("Loading offline Vosk model (the large one takes a while)...")

        self.model = Model(model_name=model_name)
        self.recognizer = KaldiRecognizer(self.model, self.samplerate)

        self.counter = Counter(listening_timeout)
        self.wakeup = False

        self.command = None
        self.command_lock = threading.Lock()

        # --- audio hand-off between the callback and the recognizer thread ---
        self.audio_queue = queue.Queue(maxsize=max_backlog_blocks)
        self._stop = threading.Event()

        # --- mute-while-playing state ---
        self.status_url = status_url
        self.status_poll_interval = status_poll_interval
        self.unmute_delay = unmute_delay
        self.audio_playing = False
        self.mute_until = 0.0
        self._was_muted = False  # only touched by the audio callback

    # ------------------------------------------------------------------
    # Audio status polling
    # ------------------------------------------------------------------
    def _poll_audio_status(self):
        while not self._stop.is_set():
            try:
                response = requests.get(self.status_url, timeout=1)
                response.raise_for_status()
                available = bool(response.json()["status"])

                if self.audio_playing and available:
                    self.mute_until = time.monotonic() + self.unmute_delay

                self.audio_playing = not available

            except (requests.RequestException, KeyError, ValueError):
                pass

            self._stop.wait(self.status_poll_interval)

    def is_muted(self):
        return self.audio_playing or time.monotonic() < self.mute_until

    # ------------------------------------------------------------------
    # Recognizer thread (the ONLY thread that touches self.recognizer)
    # ------------------------------------------------------------------
    def _recognizer_loop(self):
        while not self._stop.is_set():
            try:
                item = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is RESET:
                # Drop half-heard audio, any backlog, and any stale command
                self.recognizer.Reset()
                self._drain_queue()
                self.get_command()
                continue

            try:
                if self.recognizer.AcceptWaveform(item):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        self.set_command(text)
            except Exception as e:
                print(f"Vosk error: {e}", file=sys.stderr)

    def _drain_queue(self):
        try:
            while True:
                item = self.audio_queue.get_nowait()
                if item is RESET:  # keep the marker semantics simple: already handled
                    continue
        except queue.Empty:
            pass

    # ------------------------------------------------------------------
    def mainloop(self):
        threading.Thread(target=self._poll_audio_status, daemon=True).start()
        threading.Thread(target=self._recognizer_loop, daemon=True).start()

        try:
            with sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype="int16",
                channels=self.channels,
                callback=self.audio_callback,
            ):
                print(
                    "\nListening completely offline without PyAudio! "
                    "Press Ctrl+C to stop.\n"
                )

                while True:
                    if self.counter.count():
                        self.wakeup = False
                        print("Sleeping now".center(40, "-"))

                    if self.is_muted():
                        self.get_command()
                        time.sleep(0.05)
                        continue

                    command = self.get_command()

                    if command is None:
                        time.sleep(0.01)
                        continue

                    if command == "":
                        continue

                    if not self.wakeup and "hey siri" in command:
                        self.wakeup = True
                        self.counter.count()
                        print("WOKEN UP".center(40, "-"))


                    if self.wakeup:
                        print("DEBUG: Wakeup")
                        self.process_command(command)
                        self.counter.reset()

                    if self.is_muted():
                        self.get_command()
                        time.sleep(0.05)
                        continue

                    command = self.get_command()

                    if command is None:
                        time.sleep(0.01)
                        continue

                    if command == "":
                        continue

                    if not self.wakeup and "hey siri" in command:
                        self.wakeup = True
                        print("WOKEN UP".center(40, "-"))

                        phonemes = json.loads(
                            text_to_phonemes("Hi how can I help you?").decode("utf-8")
                        )["phonemes"]

                        speech = IPA_to_speech(phonemes, "bf_alice(1)+bf_emma(2)")
                        upload_audio(speech)
                        continue

                    if self.wakeup:
                        self.process_command(command)
                        self.counter.reset()

        except KeyboardInterrupt:
            print("\nStopping...")

        except Exception as e:
            print(f"\nAn error occurred: {e}")

        finally:
            self._stop.set()

    def audio_callback(self, indata, frames, time_info, status):
        """
        Runs on sounddevice's audio thread, so it must return fast:
        no Vosk, no HTTP, no locks held for long. It only enqueues.
        """
        if status:
            print(status, file=sys.stderr)

        if self.is_muted():
            if not self._was_muted:
                self._was_muted = True
                self._put(RESET)
            return

        self._was_muted = False
        self._put(bytes(indata))

        if self.audio_queue.qsize() > self.audio_queue.maxsize * 0.75:
            print("Warning: speech recognition is falling behind real time",
                  file=sys.stderr)

    def _put(self, item):
        try:
            self.audio_queue.put_nowait(item)
        except queue.Full:
            # Recognizer can't keep up: drop this block rather than block the callback
            pass

    def set_command(self, command):
        with self.command_lock:
            self.command = command

    def get_command(self):
        with self.command_lock:
            command = self.command
            self.command = None
        return command

    def process_command(self, command):
        # normal ver
        answer = get_response(command)
        # gemini answer -> brainrot
        response = brainrotify(answer)

        phonemes = json.loads(
            text_to_phonemes(response).decode("utf-8")
        )["phonemes"]

        speech = IPA_to_speech(phonemes, "bf_alice(1)+bf_emma(2)")
        upload_audio(speech)

        print("Command:", command, "\n")
        print("Answer:", answer, "\n")
        print("Response:", response, "\n")


if __name__ == "__main__":
    draco = Draco(model_path="vosk-model-en-us-0.22")
    draco.mainloop()