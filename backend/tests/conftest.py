"""Shared test setup."""

import os

os.environ.setdefault("HILL_COUNTRY_WARM", "0")  # region loads lazily in tests
os.environ.setdefault("DATA_MODE", "manual")  # no test/real preset; tests set what they need
# Forced (not setdefault): a HITIDE_LIVE_USERS line in .env would otherwise make the suite text and call the demo
# phone, since those users bypass PHOTON_MODE=mock. load_dotenv never overrides a variable that is already set.
os.environ["HITIDE_LIVE_USERS"] = ""
# Never touch the developer's real SpacetimeDB from the suite: tests use SQLite/memory unless they opt in
# (the SpacetimeDB contract tests do, against a throwaway database).
os.environ.setdefault("HITIDE_DB_BACKEND", "sqlite")
