"""Backend selection: SpacetimeDB primary, loud SQLite fallback, explicit choices, bad values."""

import logging

import pytest

from db.factory import open_database, requested_backend
from db.spacetime import SpacetimeError


def test_spacetime_unreachable_falls_back_to_sqlite_loudly(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("SPACETIME_URL", "http://127.0.0.1:9")   # nothing listens on the discard port
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    monkeypatch.setenv("SAFETY_REGISTRY_PATH", str(tmp_path / "reg.json"))
    with caplog.at_level(logging.ERROR, logger="db.factory"):
        db = open_database("spacetime")
    try:
        assert db.backend == "sqlite" and db.requested == "spacetime"
        assert "unreachable" in db.fallback_reason and db.describe().startswith("sqlite (fallback:")
        assert any("FALLING BACK TO SQLITE" in r.message for r in caplog.records)
        assert db.public()["fallback_reason"] == db.fallback_reason
    finally:
        db.close()


def test_explicit_sqlite_and_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    for name in ("sqlite", "memory"):
        db = open_database(name)
        try:
            assert db.backend == name and db.fallback_reason is None
            assert db.evidence.list_sources()  # the evidence store works
        finally:
            db.close()


def test_default_is_spacetime_and_bad_value_fails_fast(monkeypatch):
    monkeypatch.delenv("HITIDE_DB_BACKEND", raising=False)
    assert requested_backend() == "spacetime"
    monkeypatch.setenv("HITIDE_DB_BACKEND", "postgres")
    with pytest.raises(ValueError):
        requested_backend()


def test_write_behind_never_raises_and_counts_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    db = open_database("memory")
    try:
        def bad():
            raise RuntimeError("database down")
        db.writer.submit(bad)
        db.writer.submit(lambda: db.data.kv_set("k", "v"))
        assert db.writer.flush()
        assert db.writer.stats()["failed"] == 1 and "database down" in db.writer.stats()["last_error"]
        assert db.data.kv_get("k") == "v"   # later writes still run, in order
    finally:
        db.close()


def test_write_failure_runs_fallback_and_pauses_remote_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    db = open_database("memory")
    fell_back = []
    try:
        def down():
            raise SpacetimeError("SpacetimeDB unreachable at http://127.0.0.1:3000: ConnectError")
        db.writer.submit(down, on_fail=lambda: fell_back.append("first"))
        db.writer.submit(lambda: fell_back.append("should not run while paused"), on_fail=lambda: fell_back.append("second"))
        assert db.writer.flush()
        assert fell_back == ["first", "second"] and db.writer.stats()["paused"] is True
    finally:
        db.close()
