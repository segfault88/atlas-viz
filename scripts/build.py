#!/usr/bin/env python3
"""Embed data/ephemeris.json into src/template.html -> index.html (single self-contained page)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tpl = (ROOT / "src" / "template.html").read_text()
data = (ROOT / "data" / "ephemeris.json").read_text()
marker = "/*__EPHEMERIS__*/null"
assert marker in tpl, "data placeholder missing from template"
out = ROOT / "index.html"
out.write_text(tpl.replace(marker, data.replace("</", "<\\/")))
print(f"Wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
