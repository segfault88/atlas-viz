#!/usr/bin/env python3
"""Fetch heliocentric ephemerides for 3I/ATLAS and the major planets from
NASA/JPL Horizons, compute notable events, and write:

  data/ephemeris.json      12 h samples, 2024-07 .. 2028-01 (main viewer range)
  data/ephemeris-far.json  5 d samples, 2028-01 .. 2090-01 (long-range missions)

Frame: ICRF/J2000 ecliptic, heliocentric (Sun centre), units AU and AU/day.
"""
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://ssd.jpl.nasa.gov/api/horizons.api"
START = "2024-07-01"
STOP = "2028-01-01"
STEP = "12h"
FAR_START = STOP
FAR_STOP = "2090-01-01"
FAR_STEP = "5d"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "ephemeris.json"
OUT_FAR = DATA_DIR / "ephemeris-far.json"

COMET = {"id": "atlas", "name": "3I/ATLAS", "cmd": "C/2025 N1", "color": "#7cf7c8"}
PLANETS = [
    {"id": "mercury", "name": "Mercury", "cmd": "199", "color": "#b1a9a0", "radius_km": 2440},
    {"id": "venus", "name": "Venus", "cmd": "299", "color": "#e8c98a", "radius_km": 6052},
    {"id": "earth", "name": "Earth", "cmd": "399", "color": "#4f9dff", "radius_km": 6371},
    {"id": "mars", "name": "Mars", "cmd": "499", "color": "#e0623a", "radius_km": 3390},
    {"id": "jupiter", "name": "Jupiter", "cmd": "599", "color": "#d9a877", "radius_km": 69911},
    {"id": "saturn", "name": "Saturn", "cmd": "699", "color": "#e6d49a", "radius_km": 58232},
    {"id": "uranus", "name": "Uranus", "cmd": "799", "color": "#9fe3ea", "radius_km": 25362},
    {"id": "neptune", "name": "Neptune", "cmd": "899", "color": "#5b7cff", "radius_km": 24622},
]
AU_KM = 149597870.7


def horizons(params):
    base = {"format": "json", "MAKE_EPHEM": "YES", "OBJ_DATA": "YES", "CENTER": "'500@10'"}
    base.update(params)
    q = urllib.parse.urlencode({k: v for k, v in base.items()}, quote_via=urllib.parse.quote)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=120) as r:
                data = json.load(r)
            if "error" in data:
                raise RuntimeError(data["error"])
            return data["result"]
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"  retry ({e})", file=sys.stderr)
            time.sleep(2 + attempt * 3)


def fetch_vectors(cmd, start=START, stop=STOP, step=STEP):
    res = horizons({
        "COMMAND": f"'{cmd}'", "EPHEM_TYPE": "VECTORS", "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'", "STEP_SIZE": f"'{step}'", "VEC_TABLE": "2",
        "REF_PLANE": "ECLIPTIC", "REF_SYSTEM": "ICRF", "OUT_UNITS": "AU-D",
        "CSV_FORMAT": "YES", "VEC_LABELS": "NO",
    })
    body = res.split("$$SOE")[1].split("$$EOE")[0]
    jd, pv = [], []
    for line in body.strip().splitlines():
        f = [s.strip() for s in line.split(",")]
        jd.append(float(f[0]))
        pv.append([float(x) for x in f[2:8]])
    return jd, pv, res


def fetch_elements(cmd, epoch="2025-10-29"):
    res = horizons({
        "COMMAND": f"'{cmd}'", "EPHEM_TYPE": "ELEMENTS", "START_TIME": f"'{epoch}'",
        "STOP_TIME": f"'{epoch} 00:01'", "STEP_SIZE": "'1'", "REF_PLANE": "ECLIPTIC",
        "OUT_UNITS": "AU-D", "CSV_FORMAT": "YES",
    })
    body = res.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()[0]
    f = [s.strip() for s in body.split(",")]
    # JDTDB, Cal, EC, QR, IN, OM, W, Tp, N, MA, TA, A, AD, PR
    return {"e": float(f[2]), "a": float(f[11]), "i": float(f[4]), "om": float(f[5]), "w": float(f[6])}


def jd_to_iso(jd):
    return (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)).strftime("%Y-%m-%dT%H:%M")


# ---------- interpolation (cubic Hermite with velocities) ----------
def hermite(jd, pv, t):
    step = jd[1] - jd[0]
    k = min(max(int((t - jd[0]) // step), 0), len(jd) - 2)
    h = step
    s = (t - jd[k]) / h
    a, b = pv[k], pv[k + 1]
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    return [h00 * a[i] + h10 * h * a[i + 3] + h01 * b[i] + h11 * h * b[i + 3] for i in range(3)]


def dist(p, q):
    return math.dist(p[:3], q[:3])


def refine_min(f, t0, t1, iters=60):
    """Golden-section minimisation of f on [t0, t1]."""
    g = (math.sqrt(5) - 1) / 2
    a, b = t0, t1
    c, d = b - g * (b - a), a + g * (b - a)
    for _ in range(iters):
        if f(c) < f(d):
            b = d
        else:
            a = c
        c, d = b - g * (b - a), a + g * (b - a)
    t = (a + b) / 2
    return t, f(t)


def local_minima(jd, vals):
    return [k for k in range(1, len(vals) - 1) if vals[k] < vals[k - 1] and vals[k] <= vals[k + 1]]


def main():
    bodies = {}
    raw_comet = None
    for b in [COMET] + PLANETS:
        print(f"Fetching {b['name']} ...", file=sys.stderr)
        jd, pv, raw = fetch_vectors(b["cmd"])
        bodies[b["id"]] = (jd, pv)
        if b is COMET:
            raw_comet = raw
    elements = {}
    for p in PLANETS:
        print(f"Elements {p['name']} ...", file=sys.stderr)
        elements[p["id"]] = fetch_elements(p["cmd"])

    jd, cpv = bodies["atlas"]
    for k, (j2, _) in bodies.items():
        assert j2 == jd, f"time grid mismatch for {k}"

    # Solution metadata from the Horizons header
    m_sol = re.search(r"soln ref\.=\s*([^,]+),\s*data arc:\s*(\S+) to (\S+)", raw_comet)
    m_obs = re.search(r"# obs:\s*(\d+)", raw_comet)
    arc_start, arc_end = (m_sol.group(2), m_sol.group(3)) if m_sol else (None, None)

    cpos = lambda t: hermite(jd, cpv, t)  # noqa: E731
    events = []

    def add(t, title, detail, kind):
        events.append({"jd": round(t, 4), "date": jd_to_iso(t), "title": title, "detail": detail, "kind": kind})

    # Perihelion
    r = [math.hypot(*p[:3]) for p in cpv]
    for k in local_minima(jd, r):
        t, d = refine_min(lambda t: math.hypot(*cpos(t)), jd[k - 1], jd[k + 1])
        v = math.hypot(*[x for x in hermite_v(jd, cpv, t)]) * AU_KM / 86400
        add(t, "Perihelion", f"Closest to the Sun: {d:.3f} AU ({d * AU_KM / 1e6:.0f} million km), speed {v:.1f} km/s", "perihelion")

    # Closest approaches to planets (global minimum within the window, if meaningful)
    for p in PLANETS:
        ppv = bodies[p["id"]][1]
        dd = [dist(a, b) for a, b in zip(cpv, ppv)]
        mins = local_minima(jd, dd)
        if mins:
            k = min(mins, key=lambda k: dd[k])
            f = lambda t, pid=p["id"]: math.dist(cpos(t), hermite(jd, bodies[pid][1], t))  # noqa: E731
            t, d = refine_min(f, jd[k - 1], jd[k + 1])
            if d < 1.0 or p["id"] == "earth":
                add(t, f"Closest to {p['name']}", f"{d:.3f} AU ({d * AU_KM / 1e6:.0f} million km) from {p['name']}",
                    "approach")

    # Solar conjunction as seen from Earth (min Sun–Earth–comet elongation)
    epv = bodies["earth"][1]

    def elong(t):
        e = hermite(jd, epv, t)
        c = cpos(t)
        u = [-x for x in e]
        w = [c[i] - e[i] for i in range(3)]
        cosang = sum(u[i] * w[i] for i in range(3)) / (math.hypot(*u) * math.hypot(*w))
        return math.degrees(math.acos(max(-1, min(1, cosang))))

    el = [elong(t) for t in jd]
    for k in local_minima(jd, el):
        t, a = refine_min(elong, jd[k - 1], jd[k + 1])
        if a < 30 and math.hypot(*cpos(t)) < 3.0:
            add(t, "Solar conjunction", f"Only {a:.1f}° from the Sun as seen from Earth — hidden in solar glare",
                "conjunction")

    # Ecliptic plane crossings
    for k in range(len(jd) - 1):
        z0, z1 = cpv[k][2], cpv[k + 1][2]
        if z0 == 0 or z0 * z1 < 0:
            a, b = jd[k], jd[k + 1]
            for _ in range(60):
                m = (a + b) / 2
                if cpos(a)[2] * cpos(m)[2] <= 0:
                    b = m
                else:
                    a = m
            node = "descending" if z0 > 0 else "ascending"
            add((a + b) / 2, "Crosses the ecliptic", f"Passes through the planets' orbital plane ({node} node)", "node")

    # Known milestones
    def iso_to_jd(s):
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return 2451545.0 + (d - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400

    add(iso_to_jd("2025-07-01"), "Discovery",
        "Discovered by the ATLAS survey telescope at Río Hurtado, Chile — the third known interstellar object", "milestone")
    if arc_start:
        add(iso_to_jd(arc_start), "Earliest observation",
            "First observation in JPL's orbit solution (pre-discovery images)", "milestone")
    if arc_end:
        add(iso_to_jd(arc_end), "End of observed arc",
            "Last observation used in the orbit fit — path after this is a prediction", "milestone")

    events.sort(key=lambda e: e["jd"])

    def pack(pv):
        return [round(x, 8) for row in pv for x in row[:3]] , [round(x, 10) for row in pv for x in row[3:]]

    out = {
        "meta": {
            "source": "NASA/JPL Horizons API (ssd.jpl.nasa.gov)",
            "frame": "Heliocentric ecliptic J2000 (ICRF), AU and AU/day, TDB",
            "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "solution": m_sol.group(1).strip() if m_sol else None,
            "observations": int(m_obs.group(1)) if m_obs else None,
            "arc": [arc_start, arc_end],
            "jd0": jd[0], "step": jd[1] - jd[0], "n": len(jd),
        },
        "bodies": [],
        "events": events,
    }
    for b in [COMET] + PLANETS:
        pos, vel = pack(bodies[b["id"]][1])
        entry = {k: v for k, v in b.items() if k != "cmd"}
        entry.update({"pos": pos, "vel": vel})
        if b["id"] in elements:
            entry["elements"] = elements[b["id"]]
        out["bodies"].append(entry)

    far = {"meta": None, "bodies": []}
    for b in [COMET] + PLANETS:
        print(f"Fetching {b['name']} (far range) ...", file=sys.stderr)
        fjd, fpv, _ = fetch_vectors(b["cmd"], FAR_START, FAR_STOP, FAR_STEP)
        far["meta"] = {"jd0": fjd[0], "step": fjd[1] - fjd[0], "n": len(fjd)}
        far["bodies"].append({
            "id": b["id"],
            "pos": [round(x, 7) for row in fpv for x in row[:3]],
            "vel": [round(x, 10) for row in fpv for x in row[3:]],
        })

    DATA_DIR.mkdir(exist_ok=True)
    OUT_FAR.write_text(json.dumps(far, separators=(",", ":")))
    print(f"Wrote {OUT_FAR} ({OUT_FAR.stat().st_size / 1e6:.2f} MB)", file=sys.stderr)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB), {len(events)} events", file=sys.stderr)
    for e in events:
        print(f"  {e['date']}  {e['title']:24s} {e['detail']}", file=sys.stderr)


def hermite_v(jd, pv, t):
    step = jd[1] - jd[0]
    k = min(max(int((t - jd[0]) // step), 0), len(jd) - 2)
    s = (t - jd[k]) / step
    a, b = pv[k], pv[k + 1]
    return [a[i + 3] + (b[i + 3] - a[i + 3]) * s for i in range(3)]


if __name__ == "__main__":
    main()
