import re

# Matched case-insensitively ("ASAP", "asap", "Asap" all work).
ABBREVIATIONS = {
    # general
    "asap": "as soon as possible",
    "tl;dr": "too long; didn't read",
    "diy": "do-it-yourself",
    "ai": "Artificial Intelligence",
    "faq": "frequently asked questions",
    "eta": "estimated time of arrival",
    "fyi": "for your information",
    "btw": "by the way",
    "imo": "in my opinion",
    "imho": "in my humble opinion",
    "iirc": "if I recall correctly",
    "tbh": "to be honest",
    "tbf": "to be fair",
    "aka": "also known as",
    "approx": "approximately",
    "info": "information",
    "vs": "versus",
    "etc": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
    "tv": "television",
    "pov": "point of view",
    "dm": "direct message",
    "irl": "in real life",
    # titles
    "dr": "Doctor",
    "mr": "Mister",
    "mrs": "Missus",
    "prof": "Professor",
    # chat / slang
    "lol": "laugh out loud",
    "lmao": "laughing my ass off",
    "rofl": "rolling on the floor laughing",
    "omg": "oh my god",
    "idk": "I don't know",
    "idc": "I don't care",
    "ngl": "not gonna lie",
    "smh": "shaking my head",
    "fr": "for real",
    "rn": "right now",
    "lmk": "let me know",
    "omw": "on my way",
    "brb": "be right back",
    "gtg": "got to go",
    "nvm": "never mind",
    "np": "no problem",
    "thx": "thanks",
    "ty": "thank you",
    "pls": "please",
    "plz": "please",
    "ppl": "people",
    "bc": "because",
    "cuz": "because",
    "tho": "though",
    "u": "you",
    "gg": "good game",
    "ez": "easy",
    "fomo": "fear of missing out",
    "yolo": "you only live once",
    "pic": "picture",
    "pics": "pictures",
}

# Only matched in exactly this case, because the lowercase form is a real word
# ("id" as in Freud, "rip" as in "rip it off").
CASE_SENSITIVE_ABBREVIATIONS = {
    "ID": "identification",
    "RIP": "rest in peace",
}

# Abbreviations that are normally written with a trailing period ("Dr.", "Mr.").
# The period is swallowed so it isn't read out or left dangling after expansion.
# (Not "etc", so a sentence-ending "etc." keeps its period.)
CONSUME_PERIOD = {"dr", "mr", "mrs", "prof", "vs", "approx"}


def _build_pattern(keys, case_sensitive=False):
    # Longest first, so "w/o"-style or longer entries win over shorter prefixes
    parts = []
    for key in sorted(keys, key=len, reverse=True):
        part = re.escape(key)
        if key.lower() in CONSUME_PERIOD:
            part += r"\.?"
        parts.append(part)

    # (?<![\w']) and (?!\w) replace \b. \b breaks on entries that start or end
    # with punctuation ("e.g.", "tl;dr"), so those were never being expanded.
    return re.compile(
        r"(?<![\w'])(?:" + "|".join(parts) + r")(?!\w)",
        0 if case_sensitive else re.IGNORECASE,
    )


_PATTERN = _build_pattern(ABBREVIATIONS.keys())
_CASE_SENSITIVE_PATTERN = _build_pattern(CASE_SENSITIVE_ABBREVIATIONS.keys(), True)


def _lookup(word, table):
    if word in table:
        return table[word]
    return table.get(word.rstrip("."))


def expand_abbreviations(text: str) -> str:
    """
    Expands common abbreviations (and chat slang) so text-to-speech reads
    them as words instead of spelling them out or skipping them.
    """
    if not text:
        return text

    def replace_insensitive(match):
        word = match.group(0)
        replacement = _lookup(word.lower(), ABBREVIATIONS)
        return replacement if replacement is not None else word

    def replace_sensitive(match):
        word = match.group(0)
        replacement = _lookup(word, CASE_SENSITIVE_ABBREVIATIONS)
        return replacement if replacement is not None else word

    text = _PATTERN.sub(replace_insensitive, text)
    text = _CASE_SENSITIVE_PATTERN.sub(replace_sensitive, text)
    return text


if __name__ == "__main__":
    tests = [
        "Dr. Smith will be there ASAP, e.g. at noon.",
        "AI's great, ngl. Idk tho, fr fr.",
        "Check your ID, bring snacks, pens, etc.",
        "lol u should see the pics, tl;dr: it was wild",
        "The id and the ego. Rip it off.",
    ]
    for t in tests:
        print(t, "->", expand_abbreviations(t))