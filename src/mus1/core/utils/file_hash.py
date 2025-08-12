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


