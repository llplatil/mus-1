from pathlib import Path
import hashlib


def compute_sample_hash(file_path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """Compute a quick BLAKE2b hash from three sampled chunks of a file.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Size (bytes) of each chunk to sample from start/middle/end.

    Returns:
        32-character hex digest string.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found for hashing: {file_path}")

    file_size = file_path.stat().st_size
    hasher = hashlib.blake2b(digest_size=16)

    with open(file_path, "rb") as f:
        # First chunk
        hasher.update(f.read(min(chunk_size, file_size)))

        # Middle chunk
        if file_size > chunk_size * 2:
            middle_pos = file_size // 2
            f.seek(max(0, middle_pos - chunk_size // 2))
            hasher.update(f.read(chunk_size))

        # Last chunk
        if file_size > chunk_size:
            f.seek(max(0, file_size - chunk_size))
            hasher.update(f.read(chunk_size))

    return hasher.hexdigest()


# Full-file hashing (blake2b by default) and change detection helpers
def compute_full_hash(file_path: Path, *, algo: str = "blake2b", digest_size: int = 32, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Compute a full-file hash (default BLAKE2b) in streaming fashion.

    Args:
        file_path: Path to the file to hash.
        algo: Hash algorithm ("blake2b" or "sha256").
        digest_size: Digest size for blake2b (ignored for sha256).
        chunk_size: Read chunk size.

    Returns:
        Hex digest string.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found for hashing: {file_path}")

    if algo.lower() == "sha256":
        hasher = hashlib.sha256()
    else:
        hasher = hashlib.blake2b(digest_size=digest_size)

    with open(file_path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def file_identity_signature(file_path: Path) -> tuple[int, float]:
    """Return a quick-change signature (size, mtime) for detecting changes."""
    st = file_path.stat()
    return (st.st_size, st.st_mtime)

