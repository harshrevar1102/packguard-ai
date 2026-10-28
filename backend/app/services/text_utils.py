"""Deterministic text helpers shared by the extractors and the comparison engine."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_QUOTES = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u2009": " ", "\u200b": ""}
)


def clean(s: str) -> str:
    return unicodedata.normalize("NFKC", s).translate(_QUOTES)


def collapse(s: str) -> str:
    return " ".join(s.split())


def norm(s: str) -> str:
    """Comparison normal form: case-folded, whitespace collapsed, harmless spacing around punctuation removed."""
    s = " ".join(clean(s).lower().split())
    s = re.sub(r"\s+([,.;:!?%)\]])", r"\1", s)
    s = re.sub(r"([(\[])\s+", r"\1", s)
    return s


def _norm_map(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        ch = ch.translate(_QUOTES)
        if ch == "":
            continue
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
            continue
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
        idx.append(i)
        prev_space = False
    return "".join(out), idx


def find_phrase(text: str, phrase: str) -> tuple[int, int] | None:
    """Find `phrase` in `text` ignoring case and whitespace differences.
    Returns (start, end) offsets in the ORIGINAL text, or None."""
    n_text, idx = _norm_map(text)
    n_phrase = " ".join(phrase.translate(_QUOTES).lower().split())
    if not n_phrase or not n_text:
        return None
    m = re.search(r"(?<!\w)" + re.escape(n_phrase) + r"(?!\w)", n_text)
    if not m:
        return None
    return idx[m.start()], idx[m.end() - 1] + 1


def snippet(text: str, start: int, end: int, ctx: int = 40, max_len: int = 420) -> str:
    s = max(0, start - ctx)
    e = min(len(text), end + ctx)
    out = collapse(text[s:e])
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return ("…" if s > 0 else "") + out + ("…" if e < len(text) else "")


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def word_diff(ref: str, art: str, limit: int = 8) -> list[str]:
    """Human-readable word-level differences between two texts (case-insensitive)."""
    r = clean(ref).split()
    a = clean(art).split()
    sm = SequenceMatcher(None, [w.lower() for w in r], [w.lower() for w in a], autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rs, as_ = " ".join(r[i1:i2]), " ".join(a[j1:j2])
        if tag == "replace":
            out.append(f"reference “{rs}” vs artwork “{as_}”")
        elif tag == "delete":
            out.append(f"“{rs}” is in the reference but not on the artwork")
        else:
            out.append(f"“{as_}” is on the artwork but not in the reference")
    if len(out) > limit:
        out = out[:limit] + [f"…and {len(out) - limit} more difference(s)"]
    return out


def split_top_level(s: str) -> list[str]:
    """Split a list on commas / sentence periods that are outside parentheses."""
    items: list[str] = []
    depth = 0
    cur: list[str] = []
    n = len(s)
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and (ch == "," or (ch == "." and (i + 1 == n or s[i + 1].isspace()))):
            item = collapse("".join(cur))
            if item:
                items.append(item)
            cur = []
            continue
        cur.append(ch)
    tail = collapse("".join(cur))
    if tail:
        items.append(tail)
    return items


def list_diff(ref_items: list[str], art_items: list[str], limit: int = 10) -> tuple[list[str], bool]:
    """Item-level diff of two ordered lists. Returns (differences, same_items_different_order)."""
    rk = [norm(x) for x in ref_items]
    ak = [norm(x) for x in art_items]
    sm = SequenceMatcher(None, rk, ak, autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rs, as_ = ", ".join(ref_items[i1:i2]), ", ".join(art_items[j1:j2])
        if tag == "replace":
            out.append(f"reference “{rs}” vs artwork “{as_}”")
        elif tag == "delete":
            out.append(f"“{rs}” is in the reference but not on the artwork")
        else:
            out.append(f"“{as_}” is on the artwork but not in the reference")
    order_only = bool(out) and sorted(rk) == sorted(ak)
    if len(out) > limit:
        out = out[:limit] + [f"…and {len(out) - limit} more difference(s)"]
    return out, order_only


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
