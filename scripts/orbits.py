"""Two-body orbital mechanics helpers: ephemeris lookup, Lambert solver, conic sampling.

Units: AU, days, AU/day. Frame: heliocentric ecliptic J2000 (same as the Horizons data).
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MU_SUN = 2.959122082855911e-4           # AU^3 / day^2
AU_KM = 149597870.7
KMS = AU_KM / 86400                     # 1 AU/day in km/s
DATA = Path(__file__).resolve().parent.parent / "data"

# Planetary GM (km^3/s^2) and equatorial radius (km) for departure-burn estimates
PLANET_GM = {"earth": 398600.4, "mars": 42828.4, "venus": 324859.0, "jupiter": 126686534.0, "saturn": 37931187.0}
PLANET_R = {"earth": 6378.1, "mars": 3396.2, "venus": 6051.8, "jupiter": 71492.0, "saturn": 60268.0}


def jd(iso: str) -> float:
    """Julian Date (TDB≈UTC here) for an ISO date/time string."""
    d = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    return 2451545.0 + (d - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400


def iso(t: float) -> str:
    from datetime import timedelta
    return (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=t - 2451545.0)).strftime("%Y-%m-%d")


class Ephemeris:
    """Hermite-interpolated states from data/ephemeris.json + data/ephemeris-far.json."""

    def __init__(self):
        near = json.loads((DATA / "ephemeris.json").read_text())
        far = json.loads((DATA / "ephemeris-far.json").read_text())
        self.segments = []
        for src, meta in ((near, near["meta"]), (far, far["meta"])):
            bodies = {b["id"]: (np.array(b["pos"]).reshape(-1, 3), np.array(b["vel"]).reshape(-1, 3)) for b in src["bodies"]}
            self.segments.append((meta["jd0"], meta["step"], meta["n"], bodies))

    def state(self, body: str, t: float):
        for jd0, step, n, bodies in self.segments:
            if t <= jd0 + step * (n - 1) + 1e-9:
                break
        P, V = bodies[body]
        s0 = (t - jd0) / step
        k = min(max(int(math.floor(s0)), 0), n - 2)
        s = s0 - k
        if not (-1e-6 <= s <= 1 + 1e-6):
            raise ValueError(f"t={iso(t)} outside ephemeris range")
        h00, h10, h01, h11 = 2*s**3 - 3*s**2 + 1, s**3 - 2*s**2 + s, -2*s**3 + 3*s**2, s**3 - s**2
        r = h00 * P[k] + h10 * step * V[k] + h01 * P[k + 1] + h11 * step * V[k + 1]
        d00, d10, d01, d11 = 6*s**2 - 6*s, 3*s**2 - 4*s + 1, -6*s**2 + 6*s, 3*s**2 - 2*s
        v = (d00 * P[k] + d01 * P[k + 1]) / step + d10 * V[k] + d11 * V[k + 1]
        return r, v


# ---------- universal-variable machinery ----------

def stumpff(z: float):
    if z > 1e-8:
        s = math.sqrt(z)
        return (1 - math.cos(s)) / z, (s - math.sin(s)) / s**3
    if z < -1e-8:
        s = math.sqrt(-z)
        return (math.cosh(s) - 1) / -z, (math.sinh(s) - s) / s**3
    return 0.5 - z / 24, 1 / 6 - z / 120


def lambert(r1, r2, tof: float, prograde: bool = True, mu: float = MU_SUN):
    """Single-revolution Lambert problem (universal variables, bisection on z).

    Returns (v1, v2) or None. `prograde` picks the transfer direction relative to the ecliptic north.
    """
    r1, r2 = np.asarray(r1, float), np.asarray(r2, float)
    R1, R2 = np.linalg.norm(r1), np.linalg.norm(r2)
    cos_dth = np.clip(np.dot(r1, r2) / (R1 * R2), -1, 1)
    cz = np.cross(r1, r2)[2]
    dth = math.acos(cos_dth)
    if (prograde and cz < 0) or (not prograde and cz >= 0):
        dth = 2 * math.pi - dth
    if abs(1 - cos_dth) < 1e-12:
        return None
    A = math.sin(dth) * math.sqrt(R1 * R2 / (1 - cos_dth))
    if abs(A) < 1e-12:
        return None

    def y_of(z):
        C, S = stumpff(z)
        return R1 + R2 + A * (z * S - 1) / math.sqrt(C)

    def tof_of(z):
        C, S = stumpff(z)
        y = R1 + R2 + A * (z * S - 1) / math.sqrt(C)
        if y < 0:
            return None
        return ((y / C) ** 1.5 * S + A * math.sqrt(y)) / math.sqrt(mu)

    z_hi = 4 * math.pi**2 - 1e-6
    # Walk z_lo down until TOF(z_lo) < tof (or y hits 0, where TOF -> 0)
    z_lo = -1.0
    while True:
        t_lo = tof_of(z_lo)
        if t_lo is None:
            # find the y = 0 boundary between z_lo and a valid z above it
            a, b = z_lo, z_hi
            for _ in range(200):
                m = (a + b) / 2
                if y_of(m) < 0:
                    a = m
                else:
                    b = m
            z_lo = b
            break
        if t_lo < tof:
            break
        z_lo *= 2
        if z_lo < -4e4:
            return None
    a, b = z_lo, z_hi
    for _ in range(300):
        m = (a + b) / 2
        t = tof_of(m)
        if t is None or t < tof:
            a = m
        else:
            b = m
        if b - a < 1e-13 * max(1, abs(m)):
            break
    z = (a + b) / 2
    y = y_of(z)
    f = 1 - y / R1
    g = A * math.sqrt(y / mu)
    gdot = 1 - y / R2
    v1 = (r2 - f * r1) / g
    v2 = (gdot * r2 - r1) / g
    return v1, v2


def sample_conic(r0, v0, tof: float, n: int = 400, mu: float = MU_SUN):
    """Sample a Keplerian arc uniformly in the universal anomaly (dense near perihelion).

    Returns (times [days from start], positions [n x 3]).
    """
    r0, v0 = np.asarray(r0, float), np.asarray(v0, float)
    R0 = np.linalg.norm(r0)
    vr0 = np.dot(r0, v0) / R0
    alpha = 2 / R0 - np.dot(v0, v0) / mu
    smu = math.sqrt(mu)

    def t_of(x):
        z = alpha * x * x
        C, S = stumpff(z)
        return (R0 * vr0 / smu * x * x * C + (1 - alpha * R0) * x**3 * S + R0 * x) / smu

    # bracket and bisect for the final universal anomaly
    hi = 1e-3
    while t_of(hi) < tof:
        hi *= 2
    lo = 0.0
    for _ in range(200):
        m = (lo + hi) / 2
        if t_of(m) < tof:
            lo = m
        else:
            hi = m
    xf = (lo + hi) / 2

    ts, ps = [], []
    for x in np.linspace(0, xf, n):
        z = alpha * x * x
        C, S = stumpff(z)
        t = t_of(x)
        f = 1 - x * x / R0 * C
        g = t - x**3 * S / smu
        ts.append(t)
        ps.append(f * r0 + g * v0)
    return np.array(ts), np.array(ps)


def departure_dv(vinf_kms: float, body: str, alt_km: float = 200.0) -> float:
    """Burn from a circular parking orbit to reach hyperbolic excess speed vinf (Oberth-assisted)."""
    mu, r = PLANET_GM[body], PLANET_R[body] + alt_km
    return math.sqrt(vinf_kms**2 + 2 * mu / r) - math.sqrt(mu / r)
