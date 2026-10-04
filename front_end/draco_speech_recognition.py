from utilities.counter import Counter
from utilities.send_audio_to_game import upload_audio
from utilities.text_filer import expand_abbreviations
from gemini.run_model import get_response
from IPA_related.IPA_to_speech import IPA_to_speech
from IPA_related.to_phonemes import text_to_phonemes

import sys
import time
import json
import math
import array
import threading
import requests
import sounddevice as sd

from vosk import Model, KaldiRecognizer
from dotenv import load_dotenv
from brainrot.run_model import brainrotify

load_dotenv()

AUDIO_STATUS_URL = "http://127.0.0.1:5000/audio-buffer-status"


class Draco:
    def __init__(
        self,
        model_name="vosk-model-en-us-0.22-lgraph",
        model_path=None,  # folder containing the model
        lang="en-us",
        samplerate=16000,
        blocksize=1600,  # 100 ms of audio -> partial results update 10x/second
        channels=1,
        callback=None,
        listening_timeout=60 * 30,
        status_url=AUDIO_STATUS_URL,
        status_poll_interval=0.05,
        unmute_delay=0.4,
        mic_threshold=700,  # RMS level (0-32767). Higher = picks up less sound
        min_loud_blocks=2,  # sound must stay loud this many blocks in a row (~0.2 s) to count
        hangover_blocks=10,  # keep passing audio this many blocks after the last loud one (~1 s)
        show_levels=False,  # True prints the live mic level so you can tune mic_threshold
        finalize_after=2.0,  # seconds of unchanged partial before the text is finalized and sent
    ):
        self.finalize_after = finalize_after
        self.min_loud_blocks = min_loud_blocks
        self._loud_run = 0
        self._pending = b""
        self._gate_open = False  # True while we consider the user to be "recording"
        self._heard_words = False  # any partial text seen during this recording
        self._last_hint = 0.0
        # Results made up only of these are treated as noise, not speech
        self.noise_words = {
            "the", "a", "uh", "um", "huh", "hmm", "mm", "oh", "ah", "eh",
            "it", "i", "and", "in", "on", "of", "to", "that", "he", "she",
        }
        self._partial_text = ""
        self._partial_changed_at = 0.0
        self.mic_threshold = mic_threshold
        self.hangover_blocks = hangover_blocks
        self.show_levels = show_levels
        self._hangover = 0

        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback

        print("Loading offline Vosk model (the large one takes a while)...")

        self.model = Model(model_name=model_name)
        self.recognizer = KaldiRecognizer(self.model, self.samplerate)

        # Shorten Vosk's own "end of sentence" silence wait (newer vosk versions only)
        if hasattr(self.recognizer, "SetEndpointerDelays"):
            try:
                self.recognizer.SetEndpointerDelays(
                    5.0, max(0.3, self.finalize_after), 30.0
                )
            except Exception:
                pass

        self.counter = Counter(listening_timeout)
        self.wakeup = False

        # --- mute-while-playing state ---
        self.status_url = status_url
        self.status_poll_interval = status_poll_interval
        self.unmute_delay = unmute_delay
        self.audio_playing = False
        self.mute_until = 0.0
        self._stop = threading.Event()

        # --- partial display state ---
        self._last_partial = ""
        self._was_muted = False

    # ------------------------------------------------------------------
    # Audio status polling (runs in the background, only sets flags)
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
    # Noise gate
    # ------------------------------------------------------------------
    @staticmethod
    def _rms(data):
        samples = array.array("h", data)
        if not samples:
            return 0.0
        return math.sqrt(sum(s * s for s in samples) / len(samples))

    def _gate(self, data):
        """
        Blocks quieter than mic_threshold are replaced with silence, so Vosk
        ignores background noise and quiet voices. A short hangover keeps the
        ends of words from being clipped.
        """
        level = self._rms(data)

        if self.show_levels:
            sys.stdout.write(f"\rmic level: {level:7.0f} / threshold {self.mic_threshold}   ")
            sys.stdout.flush()

        if level >= self.mic_threshold:
            self._loud_run += 1

            # Gate already open (we're mid-speech): pass audio straight through
            if self._hangover > 0:
                self._hangover = self.hangover_blocks
                self._pending = b""
                return data

            # Gate closed: only open after several loud blocks in a row, so
            # short clicks, pops and bumps never reach Vosk.
            if self._loud_run >= self.min_loud_blocks:
                self._hangover = self.hangover_blocks
                out = self._pending + data  # include the blocks that led up to it
                self._pending = b""
                self._gate_open = True
                self._heard_words = False
                self._log(f"[REC]  Recording started  (level {level:.0f})")
                return out

            self._pending += data
            return bytes(len(data))

        # Quiet block
        self._loud_run = 0
        self._pending = b""

        if self._hangover > 0:
            self._hangover -= 1
            if self._hangover == 0 and self._gate_open:
                self._gate_open = False
                if self._heard_words:
                    self._log("[STOP] Recording stopped, finishing up...")
                else:
                    self._log("[STOP] Recording stopped (no words recognized)")
            return data

        # Gate closed. If there's noticeable sound that's just under the
        # threshold, say so (at most every 2 s) so the threshold is easy to tune.
        now = time.monotonic()
        if level >= self.mic_threshold * 0.4 and now - self._last_hint > 2.0:
            self._last_hint = now
            self._log(
                f"[....] Heard sound below threshold (level {level:.0f} < {self.mic_threshold})"
            )

        return bytes(len(data))  # silence of the same length

    # ------------------------------------------------------------------
    # Live display helpers
    # ------------------------------------------------------------------
    def _log(self, message):
        """Print a status line without leaving a half-drawn partial on screen."""
        if self._last_partial:
            sys.stdout.write("\r" + " " * 100 + "\r")
        self._last_partial = ""
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    def _show_partial(self, text):
        self._heard_words = True
        if text == self._last_partial:
            return
        self._last_partial = text
        # \r + padding overwrites the previous partial on the same line
        sys.stdout.write("\r" + f"Partial: {text}".ljust(100)[:100])
        sys.stdout.flush()

    def _clear_partial(self):
        if self._last_partial:
            sys.stdout.write("\r" + " " * 100 + "\r")
            sys.stdout.flush()
        self._last_partial = ""

    def _show_final(self, text):
        self._last_partial = ""
        sys.stdout.write("\r" + f"Final:   {text}".ljust(100) + "\n")
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Recognition: feed one block, return finished text (or None)
    # ------------------------------------------------------------------
    def _finish(self, text):
        self._partial_text = ""
        if text and set(text.lower().split()) <= self.noise_words:
            self._log(f"[NOISE] Ignored: \"{text}\" (filler words only)")
            text = ""  # Vosk "heard" only filler words: almost certainly noise
        if text:
            self._show_final(text)
            return text
        self._clear_partial()
        return None

    def _recognize(self, data):
        if self.recognizer.AcceptWaveform(data):
            return self._finish(
                json.loads(self.recognizer.Result()).get("text", "").strip()
            )

        partial = json.loads(self.recognizer.PartialResult()).get("partial", "").strip()
        if not partial:
            self._partial_text = ""
            return None

        self._show_partial(partial)
        now = time.monotonic()

        if partial != self._partial_text:
            self._partial_text = partial
            self._partial_changed_at = now
        elif now - self._partial_changed_at >= self.finalize_after:
            # Text has stopped changing: finalize now instead of waiting for
            # Vosk's silence detection, and hand it straight to the next step.
            return self._finish(
                json.loads(self.recognizer.FinalResult()).get("text", "").strip()
            )

        return None

    def _flush_input(self, stream):
        """Throw away audio that piled up while we were busy (e.g. generating a reply)."""
        try:
            available = stream.read_available
            if available > 0:
                stream.read(available)
        except Exception:
            pass
        self.recognizer.Reset()
        self._clear_partial()

    # ------------------------------------------------------------------
    def mainloop(self):
        threading.Thread(target=self._poll_audio_status, daemon=True).start()

        try:
            # No callback and no queue: we read straight from the stream and
            # run Vosk on every block right here.
            with sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype="int16",
                channels=self.channels,
            ) as stream:
                print(
                    "\nListening completely offline without PyAudio! "
                    "Press Ctrl+C to stop.\n"
                )

                while True:
                    data, overflowed = stream.read(self.blocksize)
                    if overflowed:
                        print("\nWarning: audio input overflowed", file=sys.stderr)

                    if self.counter.count():
                        self.wakeup = False
                        self._clear_partial()
                        print("Sleeping now".center(40, "-"))

                    # Ignore our own voice while audio is playing
                    if self.is_muted():
                        if not self._was_muted:
                            self._was_muted = True
                            self.recognizer.Reset()
                            self._clear_partial()
                            self._gate_open = False
                            self._hangover = 0
                            self._loud_run = 0
                            self._pending = b""
                            self._partial_text = ""
                        continue
                    self._was_muted = False

                    command = self._recognize(self._gate(bytes(data)))

                    if not command:
                        continue

                    if not self.wakeup and "hey siri" in command:
                        self.wakeup = True
                        self.counter.reset()
                        print("WOKEN UP".center(40, "-"))

                        phonemes = json.loads(
                            text_to_phonemes("Hi how can I help you?").decode("utf-8")
                        )["phonemes"]

                        speech = IPA_to_speech(phonemes, "bf_alice(1)+bf_emma(2)")
                        upload_audio(speech)
                        self._flush_input(stream)
                        continue

                    if self.wakeup:
                        self._log(f"[SEND] Sending to assistant: \"{command}\"")
                        self.process_command(command)
                        self.counter.reset()
                        self._flush_input(stream)
                    else:
                        self._log("[SKIP] Not awake, say \"hey siri\" first")

        except KeyboardInterrupt:
            print("\nStopping...")

        except Exception as e:
            print(f"\nAn error occurred: {e}")

        finally:
            self._stop.set()

    def process_command(self, command):
        # normal ver
        answer = get_response(command)
        # gemini answer -> brainrot
        response = brainrotify(answer)

        # expand abbreviations
        response = expand_abbreviations(response)

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