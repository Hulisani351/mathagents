"""Robust final-answer extraction shared by all solver pipelines."""

from __future__ import annotations

import re


_FINAL_MARKER = re.compile(
    r"(?:\*{0,2}|_{0,2})\s*final\s+answer\s*(?:\*{0,2}|_{0,2})\s*:\s*",
    flags=re.IGNORECASE,
)


def _boxed_content(text: str) -> str | None:
    match = re.search(r"\\boxed\s*\{", text)
    if not match:
        return None
    depth = 1
    start = match.end()
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index].strip()
    return None


def extract_final_answer(text: str) -> str:
    value = str(text or "").strip()
    matches = list(_FINAL_MARKER.finditer(value))
    if matches:
        value = value[matches[-1].end() :].strip()

    boxed = _boxed_content(value)
    if boxed is not None:
        return boxed

    nonempty_lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not matches and nonempty_lines:
        value = nonempty_lines[-1]

    value = value.strip()
    for opening, closing in ((r"\[", r"\]"), ("$$", "$$"), ("$", "$")):
        if value.startswith(opening) and value.endswith(closing) and len(value) >= len(opening) + len(closing):
            value = value[len(opening) : len(value) - len(closing)].strip()

    boxed = _boxed_content(value)
    if boxed is not None:
        return boxed

    value = value.strip().strip("*_").strip()
    if value.startswith("[") and value.endswith("]") and value.count(",") == 0:
        value = value[1:-1].strip()
    return value
