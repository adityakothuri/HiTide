"""Shared test setup."""

import os

os.environ.setdefault("HILL_COUNTRY_WARM", "0")  # region loads lazily in tests
