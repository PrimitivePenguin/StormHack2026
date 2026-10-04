import queue
import sys
import sounddevice as sd
from vosk import Model, KaldiRecognizer

def speech_to_text(model_path = "", lang = "en-us", samplerate = 16000, blocksize = 8000, channels = 1)

    # Use a thread-safe queue to pass audio blocks from the input stream to processing
    audio_queue = queue.Queue()

    def audio_callback(indata, frames, time, status):
        """This function is called for every audio chunk captured by sounddevice."""
        if status:
            print(status, file=sys.stderr)
        audio_queue.put(bytes(indata))

    try:
        print("Loading offline Vosk model...")
        # This automatically downloads a small English model on the first run
        model = Model(model_path=model_path, lang=lang)
        recognizer = KaldiRecognizer(model, samplerate)

        # Open the microphone audio stream using sounddevice
        with sd.RawInputStream(samplerate=samplerate, blocksize=blocksize, dtype="int16",
                            channels=channels, callback=audio_callback):
            print("\nListening completely offline without PyAudio! Press Ctrl+C to stop.\n")
            
            while True:
                data = audio_queue.get()
                if recognizer.AcceptWaveform(data):
                    print(recognizer.Result())
                else:
                    print(recognizer.PartialResult())

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"\nAn error occurred: {e}")