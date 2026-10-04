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

        # The callback writes recognized commands here.
        # No audio queue is needed.
        self.command = None
        self.command_lock = threading.Lock()

    def mainloop(self):
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

                    if not check_for_audio_buffer_availability():
                        time.sleep(0.1)
                        continue

                    # Only wait for a command, not audio.
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

                        phonemes = json.loads(text_to_phonemes("Hi how can I help you?").decode("utf-8"))["phonemes"]

                        speech = IPA_to_speech(
                            phonemes,
                            "bf_alice(1)+bf_emma(2)"
                        )
                        # Send generated speech to the game.
                        upload_audio(speech)
                        continue

                    if self.wakeup:
                        self.process_command(command)

        except KeyboardInterrupt:
            print("\nStopping...")

        except Exception as e:
            print(f"\nAn error occurred: {e}")

    def audio_callback(self, indata, frames, time_info, status):
        """
        Called directly by sounddevice for every audio block.

        Audio is sent directly to Vosk instead of being placed
        into a queue.
        """
        if status:
            print(status, file=sys.stderr)

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
        """
        Store the newest recognized command.

        There is only one command slot, so commands don't pile up.
        """
        with self.command_lock:
            self.command = command

    def get_command(self):
        """
        Retrieve the newest recognized command.
        """
        with self.command_lock:
            command = self.command
            self.command = None

        return command

    def process_command(self, command):
        """
        Process a completed voice command.
        """
        response = get_response(command)

        phonemes = json.loads(
            text_to_phonemes(response).decode("utf-8")
        )["phonemes"]

        speech = IPA_to_speech(
            phonemes,
            "bf_alice(1)+bf_emma(2)"
        )

        # Send generated speech to the game.
        upload_audio(speech)

        print("Command:", command, "\n")
        print("Response:", response, "\n")


def check_for_audio_buffer_availability(
    url="http://127.0.0.1:5000/audio-buffer-status"
):
    response = requests.get(url=url)
    response.raise_for_status()

    return response.json()["status"]


if __name__ == "__main__":
    draco = Draco()
    draco.mainloop()