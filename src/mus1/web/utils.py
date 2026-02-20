from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Tuple


def tail_text(path: Path, *, max_lines: int = 200) -> str:
    """
    Efficient-ish tail for log files (best effort).
    """
    try:
        if max_lines <= 0:
            return ""
        # Read from the end in chunks until we have enough newlines.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= max_lines:
                step = block if pos >= block else pos
                pos -= step
                f.seek(pos, os.SEEK_SET)
                data = f.read(step) + data
            txt = data.decode(errors="replace")
            lines = txt.splitlines()[-max_lines:]
            return "\n".join(lines)
    except Exception:
        return ""


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return int(r.returncode), (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)

