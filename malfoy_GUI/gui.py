import pygame
import requests
import os
from collections import deque

pygame.init()
pygame.mixer.init()

FRAME_FOLDER = "./malfoy_GUI/resources/frames"
AUDIO_FOLDER = "./malfoy_GUI/audio"
AUDIO_EXTENSIONS = (".mp3", ".ogg", ".wav")
FADE_DURATION_MS = 500      # how long the transition back to frame 0 takes
ANIMATION_EARLY_MS = 700    # animation stops this long before the audio ends

CHECK_FOLDER_EVENT = pygame.USEREVENT + 1

screen = pygame.display.set_mode((1280, 720))
clock = pygame.time.Clock()
running = True

frames = [
    pygame.image.load(os.path.join(FRAME_FOLDER, filename)).convert()
    for filename in sorted(os.listdir(FRAME_FOLDER))
]
frame_len = len(frames)
frame_counter = 0      # next frame to show while animating
last_drawn = 0         # index of the frame shown most recently

# Transition state
was_animating = False
fading = False
fade_from = None       # frame index we're fading away from
fade_start = 0

# Files already in the folder at startup are ignored
ignored_files = set(os.listdir(AUDIO_FOLDER))
pending_sizes = {}        # filename -> last seen size (to make sure copying has finished)
audio_queue = deque()     # filepaths waiting to be played
current_audio = None      # filepath currently playing
current_duration_ms = 0   # length of the current track in milliseconds

pygame.time.set_timer(CHECK_FOLDER_EVENT, 1000)

def update_audio_buffer_available_flag(url = "http://127.0.0.1:5000/audio-finished-playing"):
    try:
        response = requests.post(
            url = url,
            json={
                "message": "Audio finished reading"
            },
            timeout=2
        )
        response.raise_for_status()
        print("Server notified: audio finished")
    except requests.RequestException as e:
        print("Failed to notify server: ", e)

def check_for_new_files():
    global ignored_files

    try:
        current_files = set(os.listdir(AUDIO_FOLDER))

        # Forget names that no longer exist so a file with the same name can be re-added later
        ignored_files &= current_files
        for name in list(pending_sizes):
            if name not in current_files:
                del pending_sizes[name]

        queued_names = {os.path.basename(p) for p in audio_queue}
        if current_audio:
            queued_names.add(os.path.basename(current_audio))

        for filename in current_files - ignored_files - queued_names:
            filepath = os.path.join(AUDIO_FOLDER, filename)

            if not os.path.isfile(filepath):
                continue

            if not filename.lower().endswith(AUDIO_EXTENSIONS):
                ignored_files.add(filename)  # not audio, leave it alone
                continue

            # Only queue once the size has stopped changing (file finished being written)
            size = os.path.getsize(filepath)
            if size > 0 and pending_sizes.get(filename) == size:
                print("New file detected:", filename)
                audio_queue.append(filepath)
                del pending_sizes[filename]
            else:
                pending_sizes[filename] = size
    except Exception as e:
        print("Error scanning the folder:", e)


def delete_file(filepath):
    try:
        os.remove(filepath)
        print("Deleted:", filepath)
    except OSError as e:
        print(f"Can't delete {filepath}:", e)


def get_duration_ms(filepath):
    """Length of an audio file in ms (0 if it can't be determined)."""
    try:
        sound = pygame.mixer.Sound(filepath)
        length = sound.get_length()
        del sound
        return int(length * 1000)
    except pygame.error:
        return 0


def update_audio():
    """Called every frame: deletes finished audio, then starts the next in the queue."""
    global current_audio, current_duration_ms

    if pygame.mixer.music.get_busy():
        return  # still playing, never interrupt

    if current_audio:
        pygame.mixer.music.unload()  # release the file so it can be deleted
        delete_file(current_audio)
        current_audio = None
        current_duration_ms = 0

        update_audio_buffer_available_flag()

    while audio_queue:
        filepath = audio_queue.popleft()
        try:
            print("Playing:", filepath)
            current_duration_ms = get_duration_ms(filepath)
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            current_audio = filepath
            break
        except pygame.error as e:
            print(f"Can't play {filepath}:", e)
            pygame.mixer.music.unload()
            delete_file(filepath)  # remove unplayable file so it isn't retried


def should_animate():
    """True while the animation should run: audio is active and not in its final stretch."""
    if current_audio is None:
        return False

    # If another track is waiting, keep animating straight through the handoff
    if audio_queue:
        return True

    if current_duration_ms <= 0:
        return True  # length unknown, fall back to animating until the audio ends

    # For very short clips, don't let the early cutoff eat the whole animation
    early_ms = min(ANIMATION_EARLY_MS, current_duration_ms * 0.3)
    elapsed_ms = max(0, pygame.mixer.music.get_pos())
    return elapsed_ms < current_duration_ms - early_ms


while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

        elif e.type == CHECK_FOLDER_EVENT:
            check_for_new_files()

    update_audio()

    animating = should_animate()

    screen.fill("black")

    if animating:
        fading = False  # new animation cancels any transition in progress
        screen.blit(frames[frame_counter], (0, 0))
        last_drawn = frame_counter
        frame_counter = (frame_counter + 1) % frame_len
        was_animating = True
    else:
        if was_animating:
            # Animation just ended: start fading from the last frame back to frame 0
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
                old_frame.set_alpha(255)  # restore for normal use

    pygame.display.flip()
    clock.tick(24)

pygame.mixer.music.stop()
pygame.mixer.music.unload()
pygame.quit()