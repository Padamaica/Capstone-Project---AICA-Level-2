"""PII masking before anything reaches the LLM (DPDP Act hygiene), with local reversible pseudonyms.

Even with a self-hosted model, prompts can end up in logs. Mask by default.
"""
from __future__ import annotations

import re
from typing import Iterable

PATTERNS = [
    ("GSTIN", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("BANK_AC", re.compile(r"(?i)(?:a/c|acct|account)\s*(?:no\.?|number)?\s*[:#]?\s*\d{9,18}")),
]


class PIIMasker:
    def __init__(self, party_names: Iterable[str] = ()):
        self.forward: dict[str, str] = {}
        self.reverse: dict[str, str] = {}
        names = sorted({n for n in party_names if n and n.strip()}, key=len, reverse=True)
        for i, n in enumerate(names, 1):
            alias = f"Party_{i:03d}"
            self.forward[n] = alias
            self.reverse[alias] = n

    def mask(self, text: str) -> str:
        if not text:
            return text
        for name, alias in self.forward.items():
            text = text.replace(name, alias)
        for label, pat in PATTERNS:
            text = pat.sub(f"[{label}]", text)
        return text

    def unmask(self, text: str) -> str:
        if not text:
            return text
        for alias in sorted(self.reverse, key=len, reverse=True):
            text = text.replace(alias, self.reverse[alias])
        return text
