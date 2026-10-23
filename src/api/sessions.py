"""Bounded, expiring demo sessions. No CV files or profiles are written to disk."""

from dataclasses import dataclass, field
from secrets import token_urlsafe
from threading import RLock
from time import monotonic

from fastapi import HTTPException

from src.schemas.profile import SkillsProfile


@dataclass
class ProfileSession:
    profile: SkillsProfile
    revision: int = 0
    reviewed: bool = False
    expires_at: float = field(default_factory=lambda: monotonic() + 3600)
    lock: RLock = field(default_factory=RLock)


class SessionStore:
    def __init__(self):
        self._items = {}
        self._lock = RLock()

    def create(self, profile):
        with self._lock:
            self._items = {key: value for key, value in self._items.items()
                           if value.expires_at > monotonic()}
            if len(self._items) >= 256:
                raise HTTPException(503, "The demo is busy. Please try again later.")
            token = token_urlsafe(32)
            self._items[token] = ProfileSession(profile)
            return token

    def get(self, token):
        with self._lock:
            session = self._items.get(token)
            if session is None or session.expires_at <= monotonic():
                self._items.pop(token, None)
                raise HTTPException(401, "Your demo session expired. Upload your CV again.")
            return session

    def delete(self, token):
        with self._lock:
            self._items.pop(token, None)

    def clear(self):
        with self._lock:
            self._items.clear()
