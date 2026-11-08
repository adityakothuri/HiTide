"""Select an explicit database backend; never silently fall back on connection failure."""

import os

from evidence.store import Store


def open_store():
    backend = (os.environ.get("HITIDE_DB_BACKEND") or os.environ.get("FLOODWATCH_DB_BACKEND", "sqlite")).lower()
    if backend == "sqlite":
        return Store()
    if backend != "mongodb":
        raise ValueError("HITIDE_DB_BACKEND must be mongodb or sqlite")
    from evidence.mongo_store import MongoStore

    return MongoStore(
        os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?replicaSet=floodwatch"),
        os.environ.get("MONGODB_DATABASE", "floodwatch"),
    )
