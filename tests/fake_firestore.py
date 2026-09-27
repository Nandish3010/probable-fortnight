"""An in-memory stand-in for `google.cloud.firestore.Client`: just the doc get/set/batch surface
agents/gate/firestore_cache.py uses. Unit tests never touch real GCP credentials or network."""
from __future__ import annotations


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class FakeDocRef:
    def __init__(self, client, path):
        self._client, self._path = client, path

    def set(self, data):
        self._client.docs[self._path] = dict(data)
        self._client.writes += 1

    def get(self, timeout=None):
        self._client.reads += 1
        if self._client.fail_reads:
            raise RuntimeError("firestore unavailable (fake)")
        return FakeSnapshot(self._client.docs.get(self._path))

    def collection(self, name):
        return FakeCollectionRef(self._client, self._path + (name,))


class FakeCollectionRef:
    def __init__(self, client, path):
        self._client, self._path = client, path

    def document(self, doc_id):
        return FakeDocRef(self._client, self._path + (doc_id,))


class FakeBatch:
    def __init__(self):
        self._ops = []

    def set(self, ref, data):
        self._ops.append((ref, data))

    def commit(self):
        for ref, data in self._ops:
            ref.set(data)


class FakeClient:
    def __init__(self):
        self.docs: dict[tuple, dict] = {}
        self.reads = 0
        self.writes = 0
        self.fail_reads = False

    def collection(self, name):
        return FakeCollectionRef(self, (name,))

    def batch(self):
        return FakeBatch()
