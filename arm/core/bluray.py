"""Blu-ray structure helpers (disc title and UHD detection)."""
from __future__ import annotations

import re
from pathlib import Path


def disc_title(root: Path) -> str | None:
    """Read the human-friendly title from BDMV/META/DL/bdmt_*.xml if present."""
    meta = root / "BDMV" / "META" / "DL"
    if not meta.is_dir():
        return None
    files = sorted(meta.glob("bdmt_*.xml"), key=lambda p: (p.name != "bdmt_ita.xml",
                                                          p.name != "bdmt_eng.xml", p.name))
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"<di:name>(.*?)</di:name>", text, re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def is_uhd(root: Path) -> bool:
    try:
        with open(root / "BDMV" / "index.bdmv", "rb") as fh:
            header = fh.read(8)
    except OSError:
        return False
    return header[4:8] == b"0300"
