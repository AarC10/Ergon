from __future__ import annotations

import re

from slugify import slugify as _slugify


def slugify(text: str, max_length: int = 60) -> str:
    return _slugify(text, max_length=max_length, word_boundary=True, save_order=True)


_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify_identifier(text: str, max_length: int = 80) -> str:
    """Slug-like form for identifiers used in filesystem paths and git refs.

    Compared to `slugify`, this preserves case (so `NightRaid` stays
    `NightRaid`), keeps `.` `_` `-` for filenames, and replaces anything
    else with `-`. Leading/trailing dashes and dots are trimmed because
    git refs and many filesystems dislike them.
    """
    if not text:
        return ""
    cleaned = _IDENTIFIER_RE.sub("-", text)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-.")
    return cleaned[:max_length]
