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



def compute_full_hash(file_path: Path, chunk_size: int = 8 * 1024 * 1024, algorithm: str = "blake2b", digest_size: int = 32) -> str:
    """Compute a streaming full-file cryptographic hash.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Chunk size for streaming reads.
        algorithm: Hash algorithm name ('blake2b' or 'sha256').
        digest_size: For blake2b, digest size in bytes (default 32 = 256-bit).

    Returns:
        Hex digest string.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found for hashing: {file_path}")

    if algorithm.lower() == "blake2b":
        hasher = hashlib.blake2b(digest_size=digest_size)
    elif algorithm.lower() == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

