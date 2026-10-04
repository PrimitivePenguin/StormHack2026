
from utilities.counter import Counter
from gemini.run_model import get_response
from IPA_related.IPA_to_speech import IPA_to_speech
from IPA_related.to_phonemes import text_to_phonemes
import sys
import queue
import time
import sounddevice as sd
from vosk import Model, KaldiRecognizer

class Draco():
    def __init__(self, model_path = None, lang = "en-us", samplerate = 16000, blocksize = 8000, channels = 1, callback=None, listening_timeout = 60 * 10):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.callback = callback
        self.audio_queue = queue.Queue()

        print("Loading offline Vosk model...")
        self.model = Model(model_path=model_path, lang=lang) 
        self.recognizer = KaldiRecognizer(self.model, self.samplerate)

        self.counter = Counter(listening_timeout)
        self.wakeup = False

    def mainloop(self):        
        try:
            # Open the microphone audio stream using sounddevice
            with sd.RawInputStream(samplerate=self.samplerate, blocksize=self.blocksize, dtype="int16",
                                channels=self.channels, callback=self.audio_callback):
                print("\nListening completely offline without PyAudio! Press Ctrl+C to stop.\n")
                
                while True:
                    data = self.audio_queue.get()
                    if not self.recognizer.AcceptWaveform(data):
                        # print(self.recognizer.PartialResult())
                        continue

                    command = self.recognizer.Result()
                    print(command)

                    if not self.wakeup and "fuck" in command:
                        self.wakeup = True

                    if self.wakeup:
                        response = get_response(command)
                        # IPA = text_to_phonemes(response)
                        print(response)


                    if self.counter.count():
                        self.wakeup = False

        except KeyboardInterrupt:
            print("\nStopping...")
        except Exception as e:
            print(f"\nAn error occurred: {e}")

    def audio_callback(self, indata, frames, time, status):
        """This function is called for every audio chunk captured by sounddevice."""
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(bytes(indata))

if __name__ == "__main__":
    a = Draco()
    a.mainloop()