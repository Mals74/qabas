"""Picks the AI provider: Gemini when a key is configured, otherwise the mock."""
from functools import lru_cache

from ..config import AI_PROVIDER


@lru_cache(maxsize=1)
def get_provider():
    if AI_PROVIDER == "gemini":
        from .gemini import GeminiProvider   # imported lazily so mock mode needs no key
        return GeminiProvider()
    from .mock import MockProvider
    return MockProvider()
