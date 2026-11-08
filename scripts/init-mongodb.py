"""Initialize only the local Flood Watch replica set, required for atomic missions."""

import time

from pymongo import MongoClient
from pymongo.errors import OperationFailure


def main():
    with MongoClient("mongodb://127.0.0.1:27017/?directConnection=true", serverSelectionTimeoutMS=3000) as client:
        for attempt in range(30):
            try:
                client.admin.command("ping")
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(0.5)
        try:
            status = client.admin.command("replSetGetStatus")
            if status.get("set") != "floodwatch":
                raise RuntimeError("Port 27017 belongs to a different replica set; configure MONGODB_URI instead")
        except OperationFailure as exc:
            if exc.code != 94:
                raise
            client.admin.command("replSetInitiate", {"_id": "floodwatch", "members": [{"_id": 0, "host": "127.0.0.1:27017"}]})
        for _ in range(60):
            if client.admin.command("hello").get("isWritablePrimary"):
                print("Local Flood Watch MongoDB replica set is writable at 127.0.0.1:27017")
                return
            time.sleep(0.5)
        raise RuntimeError("MongoDB did not become writable within 30 seconds")


if __name__ == "__main__":
    main()
