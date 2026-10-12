"""Pure lead-handling logic: normalization, de-duplication and scoring.

Kept free of web-framework imports so it is trivial to unit-test and for agents to extend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count

KNOWN_SOURCES = {"web", "email", "whatsapp", "telegram", "phone", "referral", "other"}
_HIGH_INTENT_WORDS = ("price", "quote", "buy", "order", "demo", "urgent", "today")


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    return email or None


def normalize_phone(phone: str | None) -> str | None:
    """Keep digits and a leading '+'. Returns None when fewer than 7 digits remain."""
    if not phone:
        return None
    phone = phone.strip()
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return None
    return ("+" if phone.startswith("+") else "") + digits


def score_lead(source: str, message: str | None, has_email: bool, has_phone: bool) -> int:
    """Rule-based 0-100 score. Deterministic so tests and agents can reason about it."""
    score = 20
    if has_email:
        score += 15
    if has_phone:
        score += 20
    if source in {"referral", "whatsapp", "phone"}:
        score += 15
    text = (message or "").lower()
    score += 10 * sum(1 for word in _HIGH_INTENT_WORDS if word in text)
    return max(0, min(100, score))


@dataclass
class Lead:
    id: int
    name: str
    source: str
    email: str | None = None
    phone: str | None = None
    message: str | None = None
    score: int = 0
    duplicates: int = 0
    extra: dict = field(default_factory=dict)  # SkinCart: skin_profile, basket, channel ids
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class LeadStore:
    """In-memory store. Swappable for a database later without touching the API layer."""

    def __init__(self) -> None:
        self._leads: dict[int, Lead] = {}
        self._ids = count(1)

    def find_duplicate(self, email: str | None, phone: str | None) -> Lead | None:
        for lead in self._leads.values():
            if (email and lead.email == email) or (phone and lead.phone == phone):
                return lead
        return None

    def add(
        self,
        name: str,
        source: str,
        email: str | None = None,
        phone: str | None = None,
        message: str | None = None,
        extra: dict | None = None,
    ) -> tuple[Lead, bool]:
        """Add a lead. Returns (lead, created). Duplicates bump a counter instead of a new row."""
        source = source.lower().strip()
        if source not in KNOWN_SOURCES:
            source = "other"
        email = normalize_email(email)
        phone = normalize_phone(phone)
        if email is None and phone is None:
            raise ValueError("a lead needs a valid email or phone")
        existing = self.find_duplicate(email, phone)
        if existing:
            existing.duplicates += 1
            if extra:
                existing.extra.update(extra)
            return existing, False
        lead = Lead(
            id=next(self._ids),
            name=name.strip(),
            source=source,
            email=email,
            phone=phone,
            message=message,
            score=score_lead(source, message, email is not None, phone is not None),
            extra=dict(extra or {}),
        )
        self._leads[lead.id] = lead
        return lead, True

    def get(self, lead_id: int) -> Lead | None:
        return self._leads.get(lead_id)

    def list(self, min_score: int = 0) -> list[Lead]:
        return sorted(
            (lead for lead in self._leads.values() if lead.score >= min_score),
            key=lambda lead: (-lead.score, lead.id),
        )
