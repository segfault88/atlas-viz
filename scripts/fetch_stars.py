#!/usr/bin/env python3
"""Fetch the Yale Bright Star Catalogue (BSC5, CDS V/50) and write data/stars.json.

Every naked-eye star (V <= 6.5) as [x, y, z, Vmag, B-V], where (x, y, z) is a unit vector
in the J2000 ecliptic frame, the same frame as the planet and comet positions.

The brightest NAMED_COUNT stars also get a name, designation, constellation and distance,
cross-matched by HR number with the HYG database (v4.1, CC BY-SA 4.0, astronexus.com).
"""
import csv
import gzip
import io
import json
import math
import urllib.request
from pathlib import Path

URL = "https://cdsarc.cds.unistra.fr/ftp/V/50/catalog.gz"
HYG_URL = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv"
NAMED_COUNT = 150
# BSC5 lists novae (e.g. T Coronae Borealis) at outburst brightness; drop stars HYG says are normally fainter
NORMALLY_INVISIBLE_MAG = 8.0
LY_PER_PC = 3.26156

GREEK = {"Alp": "α", "Bet": "β", "Gam": "γ", "Del": "δ", "Eps": "ε", "Zet": "ζ", "Eta": "η", "The": "θ",
         "Iot": "ι", "Kap": "κ", "Lam": "λ", "Mu": "μ", "Nu": "ν", "Xi": "ξ", "Omi": "ο", "Pi": "π",
         "Rho": "ρ", "Sig": "σ", "Tau": "τ", "Ups": "υ", "Phi": "φ", "Chi": "χ", "Psi": "ψ", "Ome": "ω"}
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

# IAU constellation abbreviation -> (name, genitive)
CONSTELLATIONS = {
    "And": ("Andromeda", "Andromedae"), "Ant": ("Antlia", "Antliae"), "Aps": ("Apus", "Apodis"),
    "Aqr": ("Aquarius", "Aquarii"), "Aql": ("Aquila", "Aquilae"), "Ara": ("Ara", "Arae"),
    "Ari": ("Aries", "Arietis"), "Aur": ("Auriga", "Aurigae"), "Boo": ("Boötes", "Boötis"),
    "Cae": ("Caelum", "Caeli"), "Cam": ("Camelopardalis", "Camelopardalis"), "Cnc": ("Cancer", "Cancri"),
    "CVn": ("Canes Venatici", "Canum Venaticorum"), "CMa": ("Canis Major", "Canis Majoris"),
    "CMi": ("Canis Minor", "Canis Minoris"), "Cap": ("Capricornus", "Capricorni"), "Car": ("Carina", "Carinae"),
    "Cas": ("Cassiopeia", "Cassiopeiae"), "Cen": ("Centaurus", "Centauri"), "Cep": ("Cepheus", "Cephei"),
    "Cet": ("Cetus", "Ceti"), "Cha": ("Chamaeleon", "Chamaeleontis"), "Cir": ("Circinus", "Circini"),
    "Col": ("Columba", "Columbae"), "Com": ("Coma Berenices", "Comae Berenices"),
    "CrA": ("Corona Australis", "Coronae Australis"), "CrB": ("Corona Borealis", "Coronae Borealis"),
    "Crv": ("Corvus", "Corvi"), "Crt": ("Crater", "Crateris"), "Cru": ("Crux", "Crucis"),
    "Cyg": ("Cygnus", "Cygni"), "Del": ("Delphinus", "Delphini"), "Dor": ("Dorado", "Doradus"),
    "Dra": ("Draco", "Draconis"), "Equ": ("Equuleus", "Equulei"), "Eri": ("Eridanus", "Eridani"),
    "For": ("Fornax", "Fornacis"), "Gem": ("Gemini", "Geminorum"), "Gru": ("Grus", "Gruis"),
    "Her": ("Hercules", "Herculis"), "Hor": ("Horologium", "Horologii"), "Hya": ("Hydra", "Hydrae"),
    "Hyi": ("Hydrus", "Hydri"), "Ind": ("Indus", "Indi"), "Lac": ("Lacerta", "Lacertae"),
    "Leo": ("Leo", "Leonis"), "LMi": ("Leo Minor", "Leonis Minoris"), "Lep": ("Lepus", "Leporis"),
    "Lib": ("Libra", "Librae"), "Lup": ("Lupus", "Lupi"), "Lyn": ("Lynx", "Lyncis"), "Lyr": ("Lyra", "Lyrae"),
    "Men": ("Mensa", "Mensae"), "Mic": ("Microscopium", "Microscopii"), "Mon": ("Monoceros", "Monocerotis"),
    "Mus": ("Musca", "Muscae"), "Nor": ("Norma", "Normae"), "Oct": ("Octans", "Octantis"),
    "Oph": ("Ophiuchus", "Ophiuchi"), "Ori": ("Orion", "Orionis"), "Pav": ("Pavo", "Pavonis"),
    "Peg": ("Pegasus", "Pegasi"), "Per": ("Perseus", "Persei"), "Phe": ("Phoenix", "Phoenicis"),
    "Pic": ("Pictor", "Pictoris"), "Psc": ("Pisces", "Piscium"), "PsA": ("Piscis Austrinus", "Piscis Austrini"),
    "Pup": ("Puppis", "Puppis"), "Pyx": ("Pyxis", "Pyxidis"), "Ret": ("Reticulum", "Reticuli"),
    "Sge": ("Sagitta", "Sagittae"), "Sgr": ("Sagittarius", "Sagittarii"), "Sco": ("Scorpius", "Scorpii"),
    "Scl": ("Sculptor", "Sculptoris"), "Sct": ("Scutum", "Scuti"), "Ser": ("Serpens", "Serpentis"),
    "Sex": ("Sextans", "Sextantis"), "Tau": ("Taurus", "Tauri"), "Tel": ("Telescopium", "Telescopii"),
    "Tri": ("Triangulum", "Trianguli"), "TrA": ("Triangulum Australe", "Trianguli Australis"),
    "Tuc": ("Tucana", "Tucanae"), "UMa": ("Ursa Major", "Ursae Majoris"), "UMi": ("Ursa Minor", "Ursae Minoris"),
    "Vel": ("Vela", "Velorum"), "Vir": ("Virgo", "Virginis"), "Vol": ("Volans", "Volantis"),
    "Vul": ("Vulpecula", "Vulpeculae"),
}
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


def designation(bayer_flamsteed: str, con: str) -> str:
    """HYG 'bf' field (e.g. '9Alp CMa', 'Alp1Cen', '58 Ori') -> 'α Canis Majoris', 'α¹ Centauri', '58 Orionis'."""
    genitive = CONSTELLATIONS[con][1]
    body = bayer_flamsteed[: -len(con)].strip() if bayer_flamsteed.endswith(con) else bayer_flamsteed.strip()
    flam = ""
    while body and body[0].isdigit():
        flam, body = flam + body[0], body[1:]
    if body[:3] in GREEK:
        return f"{GREEK[body[:3]]}{body[3:].strip().translate(SUPERSCRIPT)} {genitive}"
    return f"{flam} {genitive}" if flam else ""


def load_hyg():
    with urllib.request.urlopen(HYG_URL, timeout=120) as r:
        return list(csv.DictReader(io.TextIOWrapper(r, encoding="utf-8")))


def nearest_hyg(rows, ra_deg, dec_deg, max_sep_deg=0.05):
    """Positional fallback for doubles that HYG files under the companion's HR number (e.g. Acrux, Izar)."""
    best, best_sep = None, max_sep_deg
    for row in rows:
        if not row["mag"] or float(row["mag"]) > 4.5:
            continue
        ra, dec = float(row["ra"]) * 15, float(row["dec"])
        sep = math.hypot((ra - ra_deg) * math.cos(math.radians(dec_deg)), dec - dec_deg)
        if sep < best_sep:
            best, best_sep = row, sep
    return best


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        text = gzip.decompress(r.read()).decode("latin-1")
    hyg_rows = load_hyg()
    hyg = {int(row["hr"]): row for row in hyg_rows if row["hr"]}
    stars, dropped = [], []
    for line in text.splitlines():
        rec = parse(line.ljust(197))
        if rec is None or rec[3] > MAG_LIMIT:
            continue
        hr, ra, dec, vmag, bv = rec
        h = hyg.get(hr)
        if h and h["mag"] and float(h["mag"]) > NORMALLY_INVISIBLE_MAG:
            dropped.append(hr)
            continue
        x, y, z = to_ecliptic(ra, dec)
        stars.append((hr, ra, dec, [round(x, 4), round(y, 4), round(z, 4), round(vmag, 2), round(bv, 2)]))
    stars.sort(key=lambda s: s[3][3])  # brightest first
    print(f"Dropped {len(dropped)} novae / stars normally fainter than mag {NORMALLY_INVISIBLE_MAG}: HR {dropped}")

    named, used = [], set()
    for i, (hr, ra, dec, s) in enumerate(stars[:NAMED_COUNT]):
        h = hyg.get(hr) or nearest_hyg(hyg_rows, ra, dec)
        if not h or h["con"] not in CONSTELLATIONS or h["id"] in used:
            continue  # unmatched, or the fainter half of a close double already listed (e.g. Acrux)
        used.add(h["id"])
        dist_pc = float(h["dist"]) if h["dist"] else 0
        desig = designation(h["bf"], h["con"]) if h["bf"] else ""
        named.append({
            "i": i,
            "name": h["proper"] or desig or f"HR {hr}",
            "designation": desig if h["proper"] else "",
            "constellation": CONSTELLATIONS[h["con"]][0],
            "mag": s[3],
            # HYG uses 100000 pc for "unknown"
            "distLy": round(dist_pc * LY_PER_PC, 1 if dist_pc * LY_PER_PC < 100 else 0) if 0 < dist_pc < 100000 else None,
        })

    OUT.write_text(json.dumps({
        "source": "Yale Bright Star Catalogue, 5th ed. (Hoffleit & Warren 1991), CDS V/50; names and distances "
                  "from the HYG database v4.1 (astronexus.com, CC BY-SA 4.0)",
        "frame": "J2000 ecliptic unit vectors",
        "stars": [s for *_, s in stars],
        "named": named,
    }, separators=(",", ":"), ensure_ascii=False))
    print(f"Wrote {OUT} ({len(stars)} stars, {len(named)} named, {OUT.stat().st_size / 1e3:.0f} kB)")
    for n in named[:12]:
        print(f"  {n['name']:<18} {n['designation']:<22} {n['constellation']:<14} {n['mag']:5.2f}  {n['distLy']} ly")


if __name__ == "__main__":
    main()
