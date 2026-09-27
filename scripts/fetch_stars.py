#!/usr/bin/env python3
"""Fetch the Yale Bright Star Catalogue (BSC5, CDS V/50) and write data/stars.json.

Every naked-eye star (V <= 6.5) as [x, y, z, Vmag, B-V], where (x, y, z) is a unit vector
in the J2000 ecliptic frame, the same frame as the planet and comet positions.
"""
import gzip
import json
import math
import urllib.request
from pathlib import Path

URL = "https://cdsarc.cds.unistra.fr/ftp/V/50/catalog.gz"
OUT = Path(__file__).resolve().parent.parent / "data" / "stars.json"
OBLIQUITY = math.radians(23.4392911)  # J2000 mean obliquity of the ecliptic
MAG_LIMIT = 6.5


def parse(line: str):
    """Fixed-width BSC5 record → (hr, ra_deg, dec_deg, vmag, bv) or None if no position."""
    ra_h, ra_m, ra_s = line[75:77], line[77:79], line[79:83]
    de_sign, de_d, de_m, de_s = line[83], line[84:86], line[86:88], line[88:90]
    vmag, bv = line[102:107], line[109:114]
    if not ra_h.strip() or not vmag.strip():
        return None  # a few entries (novae, non-stellar objects) have no J2000 position
    ra = 15 * (int(ra_h) + int(ra_m) / 60 + float(ra_s) / 3600)
    dec = int(de_d) + int(de_m) / 60 + int(de_s) / 3600
    if de_sign == "-":
        dec = -dec
    return int(line[0:4]), ra, dec, float(vmag), float(bv) if bv.strip() else 0.6


def to_ecliptic(ra_deg: float, dec_deg: float):
    a, d, e = math.radians(ra_deg), math.radians(dec_deg), OBLIQUITY
    x = math.cos(d) * math.cos(a)
    y = math.cos(d) * math.sin(a) * math.cos(e) + math.sin(d) * math.sin(e)
    z = -math.cos(d) * math.sin(a) * math.sin(e) + math.sin(d) * math.cos(e)
    return x, y, z


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        text = gzip.decompress(r.read()).decode("latin-1")
    stars = []
    for line in text.splitlines():
        rec = parse(line.ljust(197))
        if rec is None or rec[3] > MAG_LIMIT:
            continue
        hr, ra, dec, vmag, bv = rec
        x, y, z = to_ecliptic(ra, dec)
        stars.append([round(x, 4), round(y, 4), round(z, 4), round(vmag, 2), round(bv, 2)])
    stars.sort(key=lambda s: s[3])  # brightest first
    OUT.write_text(json.dumps({
        "source": "Yale Bright Star Catalogue, 5th ed. (Hoffleit & Warren 1991), CDS V/50",
        "frame": "J2000 ecliptic unit vectors",
        "stars": stars,
    }, separators=(",", ":")))
    print(f"Wrote {OUT} ({len(stars)} stars, {OUT.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
