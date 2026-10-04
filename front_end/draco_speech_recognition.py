from utilities.counter import Counter
from utilities.send_audio_to_game import upload_audio
from gemini.run_model import get_response
from IPA_related.IPA_to_speech import IPA_to_speech
from IPA_related.to_phonemes import text_to_phonemes

import sys
import time
import json
import threading
import requests
import sounddevice as sd

from vosk import Model, KaldiRecognizer
from dotenv import load_dotenv

load_dotenv()

AUDIO_STATUS_URL = "http://127.0.0.1:5000/audio-buffer-status"


class Draco:
    def __init__(
        self,
        model_path=None,
        lang="en-us",
        samplerate=16000,
        blocksize=8000,
        channels=1,
        callback=None,
        listening_timeout=60 * 10,
        status_url=AUDIO_STATUS_URL,
        status_poll_interval=0.05,
        unmute_delay=0.4,  # seconds to stay deaf after playback ends
    ):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback

        print("Loading offline Vosk model...")

        self.model = Model(model_path=model_path, lang=lang)
        self.recognizer = KaldiRecognizer(self.model, self.samplerate)

        self.counter = Counter(listening_timeout)

        self.wakeup = False

        self.command = None
        self.command_lock = threading.Lock()

        # --- mute-while-playing state ---
        self.status_url = status_url
        self.status_poll_interval = status_poll_interval
        self.unmute_delay = unmute_delay

        self.audio_playing = False     # True while the game's audio buffer is busy
        self.mute_until = 0.0          # monotonic time before which we stay muted
        self._was_muted = False        # only touched by the audio callback thread
        self._stop_polling = threading.Event()

    # ------------------------------------------------------------------
    # Audio status polling
    # ------------------------------------------------------------------
    def _poll_audio_status(self):
        """Background thread: keeps self.audio_playing in sync with the server."""
        while not self._stop_polling.is_set():
            try:
                response = requests.get(self.status_url, timeout=1)
                response.raise_for_status()
                available = bool(response.json()["status"])

                if self.audio_playing and available:
                    # Playback just finished: stay muted a little longer
                    self.mute_until = time.monotonic() + self.unmute_delay

                self.audio_playing = not available

            except (requests.RequestException, KeyError, ValueError):
                # Server unreachable or bad reply: keep the last known state
                pass

            self._stop_polling.wait(self.status_poll_interval)

    def is_muted(self):
        return self.audio_playing or time.monotonic() < self.mute_until

    # ------------------------------------------------------------------
    def mainloop(self):
        poller = threading.Thread(target=self._poll_audio_status, daemon=True)
        poller.start()

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

                    # Ignore anything heard while the game is speaking
                    if self.is_muted():
                        self.get_command()  # discard any leftover command
                        time.sleep(0.05)
                        continue

                    command = self.get_command()

                    if command is None:
                        time.sleep(0.01)
                        continue

                    if command == "":
                        continue

                    # Wake word
                    if not self.wakeup and "hey siri" in command:
                        self.wakeup = True
                        print("WOKEN UP".center(40, "-"))

                        phonemes = json.loads(
                            text_to_phonemes("Hi how can I help you?").decode("utf-8")
                        )["phonemes"]

                        speech = IPA_to_speech(
                            phonemes,
                            "bf_alice(1)+bf_emma(2)"
                        )
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
            self._stop_polling.set()

    def audio_callback(self, indata, frames, time_info, status):
        """
        Called directly by sounddevice for every audio block.
        While the game is playing audio, the block is dropped.
        """
        if status:
            print(status, file=sys.stderr)

        # --- muted: throw the audio away ---
        if self.is_muted():
            self._was_muted = True
            return

        # --- just got unmuted: drop partial audio and any stale command ---
        if self._was_muted:
            self._was_muted = False
            self.recognizer.Reset()
            self.get_command()

        data = bytes(indata)

        try:
            if self.recognizer.AcceptWaveform(data):
                result = json.loads(self.recognizer.Result())
                command = result.get("text", "").strip()

                if command:
                    self.set_command(command)

        except Exception as e:
            print(f"Vosk error: {e}", file=sys.stderr)

    def set_command(self, command):
        with self.command_lock:
            self.command = command

    def get_command(self):
        with self.command_lock:
            command = self.command
            self.command = None

        return command

    def process_command(self, command):
        response = get_response(command)

        phonemes = json.loads(
            text_to_phonemes(response).decode("utf-8")
        )["phonemes"]

        speech = IPA_to_speech(
            phonemes,
            "bf_alice(1)+bf_emma(2)"
        )

        # Send generated speech to the game (this flips the server flag to False)
        upload_audio(speech)

        print("Command:", command, "\n")
        print("Response:", response, "\n")


if __name__ == "__main__":
    draco = Draco()
    draco.mainloop()