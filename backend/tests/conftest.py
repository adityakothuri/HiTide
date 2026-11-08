"""Shared test setup."""

import os

os.environ.setdefault("HILL_COUNTRY_WARM", "0")  # region loads lazily in tests
os.environ.setdefault("DATA_MODE", "manual")  # no test/real preset; tests set what they need
# Never touch the developer's real SpacetimeDB from the suite: tests use SQLite/memory unless they opt in
# (the SpacetimeDB contract tests do, against a throwaway database).
os.environ.setdefault("FLOODWATCH_DB_BACKEND", "sqlite")
