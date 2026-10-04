"""Tests use their own throwaway database, never the app's data/qabas.db."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("AI_PROVIDER", "mock")
