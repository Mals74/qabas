"""Protects the free-tier quota.

The main model (3.8 Flash) allows about 20 requests a day on the free tier, and everyone who opens the live link
shares that allowance. This module counts the requests, remembers when Google says "daily limit reached", and
lets the provider switch to the light model instead of failing. The count lives in memory: after a restart it
starts again from zero, and Google's own answer ("daily limit reached") corrects it within one request.
"""
import datetime
import threading
import zoneinfo

from ..config import HEAVY_DAILY_LIMIT, MAX_LESSONS_PER_DAY

# Google's daily quotas reset at midnight Pacific time (10:00 in Saudi Arabia)
_PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")


class Quota:
    def __init__(self, limit: int):
        self.limit = limit
        self._lock = threading.Lock()
        self._day = self._today()
        self._used = 0
        self._exhausted = False

    @staticmethod
    def _today() -> datetime.date:
        return datetime.datetime.now(_PACIFIC).date()

    def _roll(self) -> None:
        if self._today() != self._day:                    # a new quota day has started
            self._day, self._used, self._exhausted = self._today(), 0, False

    def available(self, needed: int = 1) -> bool:
        """Can the main model take `needed` more requests today?"""
        with self._lock:
            self._roll()
            if self._exhausted:
                return False
            return self.limit == 0 or self._used + needed <= self.limit

    def record(self, n: int = 1) -> None:
        with self._lock:
            self._roll()
            self._used += n

    def mark_exhausted(self) -> None:
        """Google said the daily limit is used up: stop asking until the quota day changes."""
        with self._lock:
            self._roll()
            self._exhausted = True

    def status(self) -> dict:
        with self._lock:
            self._roll()
            left = 0 if self._exhausted else (None if self.limit == 0 else max(0, self.limit - self._used))
            return {"used": self._used, "limit": self.limit, "left": left, "exhausted": self._exhausted}


heavy = Quota(HEAVY_DAILY_LIMIT)          # the main (transcription) model
lessons = Quota(MAX_LESSONS_PER_DAY)    # new lessons per day on the live link (budget)
