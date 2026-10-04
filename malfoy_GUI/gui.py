import functools
import io
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pygame
import requests

pygame.init()
pygame.mixer.init()

FRAME_FOLDER = "./malfoy_GUI/resources/frames"
SERVER_URL = "http://127.0.0.1:5000"
NEXT_AUDIO_URL = f"{SERVER_URL}/next-audio"
FINISHED_URL = f"{SERVER_URL}/audio-finished-playing"

SCREEN_W, SCREEN_H = 1280, 720

FADE_DURATION_MS = 500      # how long the transition back to frame 0 takes
ANIMATION_EARLY_MS = 700    # animation stops this long before the audio ends
MAX_LOCAL_QUEUE = 2         # only pull from the server when we're running low
POLL_INTERVAL_S = 0.1

# --- chat bubbles -------------------------------------------------------
CAPTION_PORT = 5001               # the GUI listens here for text from Draco
BUBBLE_MAX_WIDTH = 560
BUBBLE_PADDING = 16
BUBBLE_GAP = 12                   # vertical space between bubbles
BUBBLE_MARGIN = 40                # distance from the screen edges
BUBBLE_MAX_LINES = 7              # longer replies scroll inside the bubble
MAX_VISIBLE_BUBBLES = 4
BUBBLE_FADE_IN_MS = 200
BUBBLE_FADE_OUT_MS = 800
USER_BUBBLE_LIFETIME_MS = 7000    # how long the user's bubble stays
AI_BUBBLE_LINGER_MS = 6000        # how long the AI's bubble stays after it finishes talking
TYPING_FINISH_RATIO = 0.85        # text is fully shown at this fraction of the audio
FALLBACK_CHARS_PER_SECOND = 15    # used if the clip length can't be read

AI_BUBBLE_COLOR = (45, 48, 66)
USER_BUBBLE_COLOR = (52, 120, 220)
BUBBLE_TEXT_COLOR = (245, 245, 250)

CONTENT_TYPE_TO_EXT = {
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
}

screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
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

# Bubble state
caption_events = deque()     # (role, text) posted by Draco, drained by the main loop
caption_queue = deque()      # AI texts waiting for their audio clip to start
bubbles = []                 # only touched by the main thread


# ------------------------------------------------------- caption receiver
class CaptionHandler(BaseHTTPRequestHandler):
    """Draco POSTs {"role": "user" | "ai", "text": "..."} to /caption."""

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            role = payload.get("role", "ai")
            text = str(payload.get("text", "")).strip()
            if text and role in ("ai", "user"):
                caption_events.append((role, text))
            self.send_response(204)
        except Exception:
            self.send_response(400)
        self.end_headers()

    def log_message(self, *args):
        pass  # keep the console quiet


def caption_server():
    try:
        ThreadingHTTPServer(("127.0.0.1", CAPTION_PORT), CaptionHandler).serve_forever()
    except OSError as e:
        print(f"Caption server could not start on port {CAPTION_PORT}: {e}")


threading.Thread(target=caption_server, daemon=True).start()


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


# ------------------------------------------- text rendering (emoji + Unicode)
# A single font only covers some scripts, so every character is drawn with the
# first installed font that actually has a glyph for it (Latin, Cyrillic, CJK,
# Korean, Thai, Arabic, symbols...). Emoji are drawn in full color when Pillow
# and a color emoji font are available, otherwise as monochrome glyphs.
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow is optional
    Image = None

BUBBLE_FONT_SIZE = 24

# Tried in order for each character. Missing fonts are simply skipped.
TEXT_FONT_NAMES = [
    "segoeui", "arial", "helveticaneue", "dejavusans", "notosans",
    "arialunicodems", "microsoftyahei", "msyh", "yugothic", "meiryo", "msgothic",
    "malgungothic", "applesdgothicneo", "hiraginosans", "pingfangsc",
    "notosanscjksc", "notosanscjkjp", "notosanscjkkr", "wenquanyimicrohei",
    "nirmala", "leelawadeeui", "tahoma", "segoeuisymbol", "symbola",
    "notosanssymbols", "notosanssymbols2", "notoemoji", "segoeuiemoji", "freesans",
    "unifont",
]

EMOJI_FONT_PATHS = [
    "C:/Windows/Fonts/seguiemj.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf",
    os.path.expanduser("~/.fonts/NotoColorEmoji.ttf"),
    os.path.expanduser("~/.local/share/fonts/NotoColorEmoji.ttf"),
]

# Characters that are invisible glue / modifiers; dropped so they don't show as boxes
IGNORED_CODEPOINTS = {0xFE0E, 0xFE0F, 0x200B, 0x200C, 0x200D, 0x2060, 0x20E3}

EMOJI_RANGES = [
    (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2300, 0x23FF), (0x2B00, 0x2BFF),
    (0x25AA, 0x25FE), (0x2934, 0x2935), (0x00A9, 0x00A9), (0x00AE, 0x00AE),
    (0x203C, 0x203C), (0x2049, 0x2049), (0x2122, 0x2122), (0x2139, 0x2139),
    (0x24C2, 0x24C2), (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3299),
]


def load_text_fonts():
    fonts, seen = [], set()
    for name in TEXT_FONT_NAMES:
        path = pygame.font.match_font(name)
        if path and path not in seen:
            seen.add(path)
            try:
                fonts.append(pygame.font.Font(path, BUBBLE_FONT_SIZE))
            except (pygame.error, OSError):
                pass
    if not fonts:
        fonts.append(pygame.font.Font(None, BUBBLE_FONT_SIZE + 4))  # built-in fallback
    return fonts


def load_pil_emoji_font():
    if Image is None:
        print("Emoji: Pillow isn't installed, so emoji can't be drawn. Run: pip install pillow")
        return None

    layout = getattr(ImageFont, "Layout", None)
    basic = layout.BASIC if layout else getattr(ImageFont, "LAYOUT_BASIC", 0)

    candidates = [pygame.font.match_font(n) for n in ("segoeuiemoji", "notocoloremoji", "applecoloremoji")]
    candidates += EMOJI_FONT_PATHS
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        # bitmap color fonts only exist at fixed sizes (109 Noto, 160 Apple)
        for size in (109, 160, 128, 96, 64, 48):
            try:
                return ImageFont.truetype(path, size, layout_engine=basic)
            except (OSError, ValueError):
                continue
    print("Emoji: no color emoji font found (Segoe UI Emoji / Apple Color Emoji / Noto Color Emoji)")
    return None


text_fonts = load_text_fonts()
primary_font = text_fonts[0]
bubble_line_h = int(primary_font.get_linesize() * 1.2)
emoji_height = int(primary_font.get_height() * 0.95)
pil_emoji_font = load_pil_emoji_font()

# Plain-text stand-ins used only when an emoji can't be drawn at all
EMOTICONS = {
    "😀": ":D", "😃": ":D", "😄": ":D", "😁": ":D", "😊": ":)", "🙂": ":)", "☺": ":)",
    "😂": "XD", "🤣": "XD", "😢": ":'(", "😭": ":'(", "😍": "<3", "🥰": "<3", "❤": "<3",
    "👍": "(y)", "😎": "B)", "😉": ";)", "😮": ":O", "😅": "^^'", "😡": ">:(",
    "🔥": "*fire*", "🎉": "*party*", "💀": "x_x", "🤔": "hmm...", "😴": "zzz",
}


def is_emoji(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


def _render_signature(font, ch):
    """(pixel bytes, surface) of a glyph, or (None, None) if it can't be rendered."""
    try:
        surface = font.render(ch, True, (255, 255, 255))
    except (pygame.error, ValueError, TypeError):
        return None, None
    return pygame.image.tostring(surface, "RGBA"), surface


@functools.lru_cache(maxsize=None)
def notdef_signatures(font):
    """What this font draws for characters it doesn't have (usually a square)."""
    signatures = set()
    for reference in ("\uFFFF", "\uFFFE", "\U0010FFFF"):
        signature, _ = _render_signature(font, reference)
        if signature is not None:
            signatures.add(signature)
    return frozenset(signatures)


def has_glyph(font, ch):
    """True only if the font really draws `ch` (font.metrics() isn't reliable for emoji)."""
    if ch.isspace():
        return True
    signature, surface = _render_signature(font, ch)
    if signature is None or surface.get_bounding_rect().width == 0:
        return False
    return signature not in notdef_signatures(font)


@functools.lru_cache(maxsize=None)
def font_for(ch):
    """First font that has this character, or None if no installed font does."""
    for font in text_fonts:
        if has_glyph(font, ch):
            return font
    return None


def _pil_render(ch):
    ascent, descent = pil_emoji_font.getmetrics()
    width = max(1, int(pil_emoji_font.getlength(ch)))
    image = Image.new("RGBA", (width, ascent + descent), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((0, 0), ch, font=pil_emoji_font, embedded_color=True)
    return image


@functools.lru_cache(maxsize=None)
def pil_notdef_signatures():
    signatures = set()
    for reference in ("\U0010FFFD", "\uFFFF"):
        try:
            image = _pil_render(reference)
            signatures.add((image.size, image.tobytes()))
        except Exception:
            pass
    return frozenset(signatures)


@functools.lru_cache(maxsize=512)
def color_emoji_surface(ch):
    """Full-color emoji image scaled to the text height, or None if unavailable."""
    if pil_emoji_font is None:
        return None
    try:
        image = _pil_render(ch)
        if image.getbbox() is None or (image.size, image.tobytes()) in pil_notdef_signatures():
            return None  # the emoji font has no glyph for this character

        scale = emoji_height / image.height
        size = (max(1, int(image.width * scale)), emoji_height)
        surface = pygame.image.frombuffer(image.tobytes(), image.size, "RGBA").convert_alpha()
        return pygame.transform.smoothscale(surface, size)
    except Exception:
        return None


def can_draw(ch):
    return color_emoji_surface(ch) is not None or font_for(ch) is not None


def clean_text(text):
    """
    Drop invisible joiners/modifiers and control characters. Anything that no
    installed font can draw is replaced with a plain-text stand-in (or removed)
    instead of showing up as an empty square.
    """
    out = []
    for ch in text:
        cp = ord(ch)
        if cp in IGNORED_CODEPOINTS or 0x1F3FB <= cp <= 0x1F3FF:  # joiners, skin tones
            continue
        if not (ch.isprintable() or ch.isspace()):
            continue
        if ch.isspace() or can_draw(ch):
            out.append(ch)
        else:
            out.append(EMOTICONS.get(ch, ""))
    return "".join(out)


# Startup report, so it's obvious why emoji look the way they do
if pil_emoji_font is not None and color_emoji_surface("\U0001F600") is None:
    print("Emoji: found an emoji font but couldn't render with it. Try: pip install -U pillow")
    pil_emoji_font = None
print(
    f"Bubble text: {len(text_fonts)} font(s); color emoji: {'yes' if pil_emoji_font else 'no'}; "
    f"mono emoji font: {'yes' if font_for(chr(0x1F600)) else 'no'}"
)


def segment(text):
    """Split text into drawable runs: ["emoji", ch, None] or ["text", str, font]."""
    runs = []
    for ch in text:
        if is_emoji(ch) and color_emoji_surface(ch) is not None:
            runs.append(["emoji", ch, None])
            continue

        font = font_for(ch)
        if font is None:
            continue  # nothing can draw it: skip rather than draw a square
        if runs and runs[-1][0] == "text" and runs[-1][2] is font:
            runs[-1][1] += ch
        else:
            runs.append(["text", ch, font])
    return runs


@functools.lru_cache(maxsize=4096)
def text_width(text):
    width = 0
    for kind, value, font in segment(text):
        if kind == "emoji":
            width += color_emoji_surface(value).get_width()
        else:
            width += font.size(value)[0]
    return width


@functools.lru_cache(maxsize=1024)
def render_line(text, color):
    """One line of text as a transparent surface, mixing fonts and emoji."""
    surface = pygame.Surface((max(1, text_width(text)), bubble_line_h), pygame.SRCALPHA)
    baseline = primary_font.get_ascent() + (bubble_line_h - primary_font.get_height()) // 2

    x = 0
    for kind, value, font in segment(text):
        if kind == "emoji":
            image = color_emoji_surface(value)
            surface.blit(image, (x, (bubble_line_h - image.get_height()) // 2))
        else:
            image = font.render(value, True, color)
            surface.blit(image, (x, baseline - font.get_ascent()))
        x += image.get_width()
    return surface


# -------------------------------------------------------------- chat bubbles
def wrap_text(text, max_width):
    lines, current = [], ""
    for word in text.split():
        test = f"{current} {word}".strip()
        if text_width(test) <= max_width:
            current = test
            continue

        if current:
            lines.append(current)

        # a single word wider than the bubble (or unspaced CJK text) gets split
        while text_width(word) > max_width:
            cut = len(word)
            while cut > 1 and text_width(word[:cut]) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word

    if current:
        lines.append(current)
    return lines or [""]


class Bubble:
    def __init__(self, role, text, speaking=False):
        self.role = role
        self.speaking = speaking  # True while its audio clip is playing
        self.born = pygame.time.get_ticks()
        self.done_at = None if speaking else self.born

        self.lines = wrap_text(clean_text(text), BUBBLE_MAX_WIDTH - 2 * BUBBLE_PADDING)
        self.total_chars = max(1, sum(len(line) + 1 for line in self.lines) - 1)
        self.width = max(text_width(line) for line in self.lines) + 2 * BUBBLE_PADDING
        shown = min(len(self.lines), BUBBLE_MAX_LINES)
        self.height = shown * bubble_line_h + 2 * BUBBLE_PADDING

    def finish(self):
        self.speaking = False
        self.done_at = pygame.time.get_ticks()

    def lifetime_ms(self):
        return USER_BUBBLE_LIFETIME_MS if self.role == "user" else AI_BUBBLE_LINGER_MS

    def expired(self, now):
        return self.done_at is not None and now - self.done_at > self.lifetime_ms() + BUBBLE_FADE_OUT_MS

    def alpha(self, now):
        fade_in = min(1.0, (now - self.born) / BUBBLE_FADE_IN_MS)
        fade_out = 1.0
        if self.done_at is not None:
            over = now - self.done_at - self.lifetime_ms()
            if over > 0:
                fade_out = max(0.0, 1.0 - over / BUBBLE_FADE_OUT_MS)
        return int(255 * fade_in * fade_out)

    def reveal_fraction(self):
        """How much of the text is shown: types out in time with the speech."""
        if not self.speaking:
            return 1.0

        elapsed_ms = max(0, pygame.mixer.music.get_pos())
        if current_duration_ms > 0:
            span_ms = current_duration_ms * TYPING_FINISH_RATIO
        else:
            span_ms = self.total_chars / FALLBACK_CHARS_PER_SECOND * 1000
        return min(1.0, elapsed_ms / max(span_ms, 1))

    def draw(self, now, bottom):
        """Draw with its bottom edge at `bottom`. Returns the height used."""
        alpha = self.alpha(now)
        if alpha <= 0:
            return 0

        visible = int(self.total_chars * self.reveal_fraction())

        parts, consumed, last_idx = [], 0, 0
        for i, line in enumerate(self.lines):
            n = max(0, min(len(line), visible - consumed))
            parts.append(line[:n])
            if n > 0:
                last_idx = i
            consumed += len(line) + 1

        # long replies: keep the line currently being "typed" in view
        start = max(0, last_idx - BUBBLE_MAX_LINES + 1)
        window = parts[start:start + BUBBLE_MAX_LINES]

        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        color = USER_BUBBLE_COLOR if self.role == "user" else AI_BUBBLE_COLOR
        pygame.draw.rect(surface, color, surface.get_rect(), border_radius=18)

        y = BUBBLE_PADDING
        for text in window:
            if text:
                surface.blit(render_line(text, BUBBLE_TEXT_COLOR), (BUBBLE_PADDING, y))
            y += bubble_line_h

        surface.set_alpha(alpha)

        if self.role == "user":
            x = SCREEN_W - BUBBLE_MARGIN - self.width
        else:
            x = BUBBLE_MARGIN
        screen.blit(surface, (x, bottom - self.height))
        return self.height


def drain_captions():
    while caption_events:
        role, text = caption_events.popleft()
        if role == "user":
            bubbles.append(Bubble("user", text))
        else:
            caption_queue.append(text)  # shown when its audio actually starts


def start_ai_bubble(speaking):
    """Called when an audio clip starts (or fails): pairs it with its caption."""
    if caption_queue:
        bubbles.append(Bubble("ai", caption_queue.popleft(), speaking=speaking))


def finish_speaking_bubbles():
    for bubble in bubbles:
        if bubble.speaking:
            bubble.finish()


def draw_bubbles():
    now = pygame.time.get_ticks()
    bubbles[:] = [b for b in bubbles if not b.expired(now)]

    bottom = SCREEN_H - BUBBLE_MARGIN
    for bubble in reversed(bubbles[-MAX_VISIBLE_BUBBLES:]):
        height = bubble.draw(now, bottom)
        if height:
            bottom -= height + BUBBLE_GAP


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
        finish_speaking_bubbles()
        threading.Thread(target=notify_audio_finished, daemon=True).start()

    while audio_queue:
        data, ext = audio_queue.popleft()
        try:
            stream = io.BytesIO(data)
            current_duration_ms = get_duration_ms(data)
            pygame.mixer.music.load(stream, ext)
            pygame.mixer.music.play()
            current_stream = stream
            start_ai_bubble(speaking=True)
            print("Playing clip from memory")
            break
        except pygame.error as e:
            print("Can't play audio:", e)
            pygame.mixer.music.unload()
            start_ai_bubble(speaking=False)  # still show the text
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

    drain_captions()
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

    draw_bubbles()

    pygame.display.flip()
    clock.tick(24)

pygame.mixer.music.stop()
pygame.mixer.music.unload()
pygame.quit()