import io
import threading
import time
from collections import deque

import pygame
import requests

pygame.init()
pygame.mixer.init()

FRAME_FOLDER = "./malfoy_GUI/resources/frames"
SERVER_URL = "http://127.0.0.1:5000"
NEXT_AUDIO_URL = f"{SERVER_URL}/next-audio"
FINISHED_URL = f"{SERVER_URL}/audio-finished-playing"

FADE_DURATION_MS = 500      # how long the transition back to frame 0 takes
ANIMATION_EARLY_MS = 700    # animation stops this long before the audio ends
MAX_LOCAL_QUEUE = 2         # only pull from the server when we're running low
POLL_INTERVAL_S = 0.1

CONTENT_TYPE_TO_EXT = {
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
}

import os
screen = pygame.display.set_mode((1280, 720))
clock = pygame.time.Clock()
running = True

frames = [
    pygame.image.load(os.path.join(FRAME_FOLDER, filename)).convert()
    for filename in sorted(os.listdir(FRAME_FOLDER))
]
frame_len = len(frames)
frame_counter = 0
last_drawn = 0

# Transition state
was_animating = False
fading = False
fade_from = None
fade_start = 0

# Audio state (everything lives in memory)
audio_queue = deque()        # (bytes, extension) fetched from the server
current_stream = None        # BytesIO currently playing (keep a reference alive!)
current_duration_ms = 0


# ---------------------------------------------------------------- networking
def notify_audio_finished():
    try:
        requests.post(FINISHED_URL, json={"message": "Audio finished reading"}, timeout=2)
        print("Server notified: audio finished")
    except requests.RequestException as e:
        print("Failed to notify server:", e)


def fetch_loop():
    """Background thread: gradually pulls audio bytes from the server."""
    while running:
        if len(audio_queue) >= MAX_LOCAL_QUEUE:
            time.sleep(POLL_INTERVAL_S)
            continue

        try:
            response = requests.get(NEXT_AUDIO_URL, timeout=2)
            if response.status_code == 200:
                mimetype = response.headers.get("Content-Type", "audio/wav").split(";")[0].strip()
                ext = CONTENT_TYPE_TO_EXT.get(mimetype, "wav")
                audio_queue.append((response.content, ext))
                print(f"Received {len(response.content)} bytes ({ext})")
            else:  # 204: nothing waiting
                time.sleep(POLL_INTERVAL_S)
        except requests.RequestException:
            time.sleep(1)  # server unreachable, retry later


threading.Thread(target=fetch_loop, daemon=True).start()


# --------------------------------------------------------------------- audio
def get_duration_ms(data):
    """Length of an audio clip in ms (0 if it can't be determined)."""
    try:
        return int(pygame.mixer.Sound(io.BytesIO(data)).get_length() * 1000)
    except pygame.error:
        return 0


def update_audio():
    """Called every frame: cleans up finished audio, then starts the next in the queue."""
    global current_stream, current_duration_ms

    if pygame.mixer.music.get_busy():
        return  # still playing, never interrupt

    if current_stream is not None:
        pygame.mixer.music.unload()
        current_stream = None
        current_duration_ms = 0
        threading.Thread(target=notify_audio_finished, daemon=True).start()

    while audio_queue:
        data, ext = audio_queue.popleft()
        try:
            stream = io.BytesIO(data)
            current_duration_ms = get_duration_ms(data)
            pygame.mixer.music.load(stream, ext)
            pygame.mixer.music.play()
            current_stream = stream
            print("Playing clip from memory")
            break
        except pygame.error as e:
            print("Can't play audio:", e)
            pygame.mixer.music.unload()
            # still tell the server so its pending counter doesn't get stuck
            threading.Thread(target=notify_audio_finished, daemon=True).start()


def should_animate():
    """True while the animation should run: audio is active and not in its final stretch."""
    if current_stream is None:
        return False

    if audio_queue:
        return True

    if current_duration_ms <= 0:
        return True

    early_ms = min(ANIMATION_EARLY_MS, current_duration_ms * 0.3)
    elapsed_ms = max(0, pygame.mixer.music.get_pos())
    return elapsed_ms < current_duration_ms - early_ms


# ----------------------------------------------------------------- main loop
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    update_audio()

    animating = should_animate()

    screen.fill("black")

    if animating:
        fading = False
        screen.blit(frames[frame_counter], (0, 0))
        last_drawn = frame_counter
        frame_counter = (frame_counter + 1) % frame_len
        was_animating = True
    else:
        if was_animating:
            was_animating = False
            fade_from = last_drawn
            fade_start = pygame.time.get_ticks()
            fading = fade_from != 0
            frame_counter = 0

        screen.blit(frames[0], (0, 0))
        last_drawn = 0

        if fading:
            progress = (pygame.time.get_ticks() - fade_start) / FADE_DURATION_MS
            if progress >= 1:
                fading = False
            else:
                old_frame = frames[fade_from]
                old_frame.set_alpha(int(255 * (1 - progress)))
                screen.blit(old_frame, (0, 0))
                old_frame.set_alpha(255)

    pygame.display.flip()
    clock.tick(24)

pygame.mixer.music.stop()
pygame.mixer.music.unload()
pygame.quit()