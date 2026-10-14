"""Thread-safe, versioned PDF snapshot shared by retrieval and analytics."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from threading import RLock

from .config import DATA_DIR
from .ingest import load_documents


@dataclass(frozen=True)
class CorpusSnapshot:
    signature: tuple
    fingerprint: str
    pages: tuple


_snapshots = {}
_lock = RLock()


def get_corpus(data_dir=DATA_DIR):
    directory = Path(data_dir).resolve()
    with _lock:
        def signature_now():
            return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                         for p in sorted(directory.glob("*.pdf")))
        for _ in range(2):
            signature = signature_now()
            cached = _snapshots.get(directory)
            if cached and cached.signature == signature:
                return cached
            pages = tuple(load_documents(directory))
            if signature_now() != signature:
                continue
            fingerprint = hashlib.sha256("\n".join(
                f"{d.metadata}:{d.page_content}" for d in pages).encode()).hexdigest()
            snapshot = CorpusSnapshot(signature, fingerprint, pages)
            _snapshots[directory] = snapshot
            return snapshot
        raise RuntimeError("Transcript files changed during loading; retry after the update completes")
