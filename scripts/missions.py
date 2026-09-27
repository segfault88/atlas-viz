#!/usr/bin/env python3
"""Build data/missions.json: hypothetical spacecraft trajectories to intercept 3I/ATLAS.

Each mission is a chain of two-body (patched-conic) heliocentric arcs between real
JPL Horizons positions, solved with a Lambert solver. Published studies are
reconstructed from their stated dates / geometry; "computed" ones are searched here.

Run after scripts/fetch_data.py:  python3 scripts/missions.py
"""
import json
import math
import sys

import numpy as np
from scipy.optimize import differential_evolution

from orbits import AU_KM, DATA, KMS, Ephemeris, departure_dv, iso, jd, lambert, sample_conic

eph = Ephemeris()
MU_J, R_J = 126686534.0, 71492.0
R_SUN_AU = 695700 / AU_KM

# ---------- building blocks ----------

def arc(r1, r2, t1, t2, prefer=None):
    """Both-direction Lambert solutions from r1@t1 to r2@t2 as (prograde, v1, v2)."""
    out = []
    for pro in (True, False):
        s = lambert(r1, r2, t2 - t1, pro)
        if s is not None:
            out.append((pro, *s))
    return out


def body_to_comet(body, t1, t2, rendezvous=False):
    """Best direct arc from a planet (or a probe co-orbiting it) to the comet."""
    r1, vb = eph.state(body, t1)
    r2, vc = eph.state("atlas", t2)
    best = None
    for pro, v1, v2 in arc(r1, r2, t1, t2):
        vinf = np.linalg.norm(v1 - vb) * KMS
        rel = np.linalg.norm(v2 - vc) * KMS
        cost = vinf + (rel if rendezvous else 0)
        if best is None or cost < best["cost"]:
            best = dict(cost=cost, vinf=vinf, rel=rel, r1=r1, v1=v1, r2=r2, t1=t1, t2=t2)
    return best


def grid_search(body, dep, arr_max, rendezvous=False, ddep=2, darr=2, min_tof=10):
    best = None
    for t1 in np.arange(jd(dep[0]), jd(dep[1]) + 1e-6, ddep):
        for t2 in np.arange(t1 + min_tof, jd(arr_max), darr):
            r = body_to_comet(body, t1, t2, rendezvous)
            if r and (best is None or r["cost"] < best["cost"]):
                best = r
    # local refinement on a 0.25-day grid
    for _ in range(2):
        t1c, t2c = best["t1"], best["t2"]
        for t1 in np.arange(max(t1c - ddep, jd(dep[0])), min(t1c + ddep, jd(dep[1])) + 1e-6, 0.25):
            for t2 in np.arange(t2c - darr, min(t2c + darr, jd(arr_max)), 0.25):
                r = body_to_comet(body, t1, t2, rendezvous)
                if r and r["cost"] < best["cost"]:
                    best = r
    return best


def leg_samples(r0, v0, t0, t1, n=300):
    ts, ps = sample_conic(r0, v0, t1 - t0, n)
    return {"t": [round(t0 + t, 5) for t in ts], "p": [round(float(x), 6) for p in ps for x in p]}


def encounter(t, r_sc, rel):
    re, _ = eph.state("earth", t)
    return {"jd": round(t, 4), "date": iso(t), "rSun": round(float(np.linalg.norm(r_sc)), 3),
            "rEarth": round(float(np.linalg.norm(r_sc - re)), 3), "relSpeed": round(float(rel), 2)}


def burn(t, body, dv, label):
    return {"jd": round(t, 4), "date": iso(t), "body": body, "dv": round(float(dv), 2), "label": label}


# ---------- scenarios ----------

def direct_flyby(body, t1, t2, park_label, dv_label):
    r = body_to_comet(body, t1, t2)
    dv = departure_dv(r["vinf"], body)
    return r, dict(
        burns=[burn(t1, body, dv, dv_label)],
        legs=[leg_samples(r["r1"], r["v1"], t1, t2)],
        encounter=encounter(t2, r["r2"], r["rel"]),
        stats={"vinf": round(r["vinf"], 2), "c3": round(r["vinf"] ** 2, 1), "park": park_label},
    )


def solar_oberth(years, seed=1):
    """Earth → Jupiter (unpowered flyby) → burn at 3.2 solar radii → 3I/ATLAS.

    Mirrors the E-J-SOM-3I sequence of Hibberd, Eubanks & Hein (2026), launch year 2035.
    """
    r_som = 3.2 * R_SUN_AU

    def solve(p):
        tE, dEJ, dJS, th, ph = p
        tJ, tS, tA = tE + dEJ, tE + dEJ + dJS, tE + years * 365.25
        if tS > tA - 100:
            return 1e3, None
        rE, vE = eph.state("earth", tE)
        rJ, vJ = eph.state("jupiter", tJ)
        rA, vA = eph.state("atlas", tA)
        rS = r_som * np.array([math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph)])
        best = (1e3, None)
        for _, a1, a2 in arc(rE, rJ, tE, tJ):
            vinfE = np.linalg.norm(a1 - vE) * KMS
            vin = (a2 - vJ) * KMS
            for _, b1, b2 in arc(rJ, rS, tJ, tS):
                vout = (b1 - vJ) * KMS
                na, nb = np.linalg.norm(vin), np.linalg.norm(vout)
                dvJ = abs(na - nb)  # powered-flyby mismatch; optimiser drives it to ~0
                turn = math.acos(np.clip(np.dot(vin, vout) / (na * nb), -1, 1))
                vm = (na + nb) / 2
                rp = MU_J / vm**2 * (1 / math.sin(turn / 2) - 1) if turn > 1e-9 else 1e12
                pen = max(0.0, (R_J + 200) - rp) / 1e4
                for _, c1, c2 in arc(rS, rA, tS, tA):
                    dvS = np.linalg.norm(c1 - b2) * KMS
                    cost = dvS + 0.3 * vinfE + 5 * dvJ + 10 * pen
                    if cost < best[0]:
                        best = (cost, dict(tE=tE, tJ=tJ, tS=tS, tA=tA, rE=rE, rJ=rJ, rS=rS, rA=rA, vinfE=vinfE,
                                           dvJ=dvJ, rpJ=rp - R_J, dvS=dvS, a1=a1, b1=b1, c1=c1,
                                           vperi=np.linalg.norm(b2) * KMS, rel=np.linalg.norm(c2 - vA) * KMS))
        return best

    bounds = [(jd("2035-01-01"), jd("2035-12-31")), (250, 1400), (150, 1200), (-math.pi, math.pi), (-0.6, 0.6)]
    res = differential_evolution(lambda p: solve(p)[0], bounds, seed=seed, popsize=40, maxiter=1500,
                                 tol=1e-12, atol=1e-9, polish=True)
    _, d = solve(res.x)
    dvE = departure_dv(d["vinfE"], "earth")
    return d, dict(
        burns=[burn(d["tE"], "earth", dvE, "Launch from low Earth orbit"),
               burn(d["tJ"], "jupiter", d["dvJ"], f"Jupiter gravity assist (passes {d['rpJ'] / 1000:,.0f} thousand km above the cloud tops)"),
               burn(d["tS"], "sun", d["dvS"], f"Solar Oberth burn at 3.2 solar radii, moving at {d['vperi']:.0f} km/s")],
        legs=[leg_samples(d["rE"], d["a1"], d["tE"], d["tJ"]),
              leg_samples(d["rJ"], d["b1"], d["tJ"], d["tS"], 400),
              leg_samples(d["rS"], d["c1"], d["tS"], d["tA"], 500)],
        encounter=encounter(d["tA"], d["rA"], d["rel"]),
        stats={"vinf": round(d["vinfE"], 2), "c3": round(d["vinfE"] ** 2, 1), "park": "200 km low Earth orbit",
               "perihelionSpeed": round(d["vperi"], 1)},
    )


def build():
    missions = []

    def add(m, geom):
        m.update(geom)
        m["totalDv"] = round(sum(b["dv"] for b in m["burns"]), 2)
        missions.append(m)
        e = m["encounter"]
        print(f"  {m['name']:<34} total ΔV {m['totalDv']:6.2f} km/s  encounter {e['date']} "
              f"at {e['rSun']:7.2f} AU, {e['relSpeed']:5.1f} km/s", file=sys.stderr)

    Y25 = {"label": "Yaginuma et al. 2025 — Feasibility of a spacecraft flyby with 3I/ATLAS from Earth or Mars",
           "url": "https://arxiv.org/abs/2507.15755"}

    # 1. Hindsight: the optimal launch was before discovery
    _, g = direct_flyby("earth", jd("2025-01-10"), jd("2025-09-15"), "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "hindsight", "name": "If we'd known in advance", "kind": "paper", "source": Y25, "color": "#9ad0ff",
         "summary": "The cheapest direct launch from Earth left in January 2025, six months before 3I/ATLAS was "
                    "discovered. Needs a hyperbolic excess speed of only 6.9 km/s, within reach of today's rockets.",
         "paper": "v∞ 6.94 km/s, flyby at 79.96 km/s"}, g)

    # 2. Launch on discovery day
    _, g = direct_flyby("earth", jd("2025-07-01"), jd("2025-11-15"), "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "earth-discovery", "name": "Launch the day it was found", "kind": "paper", "source": Y25, "color": "#ff9f6e",
         "summary": "The best direct Earth launch after discovery: lift off on 1 July 2025. It needs v∞ = 24 km/s "
                    "(C3 ≈ 576 km²/s²), nearly double the record set by New Horizons (v∞ ≈ 12.6 km/s). That is far beyond any existing launcher.",
         "paper": "v∞ 24.0 km/s, flyby at 79.73 km/s"}, g)

    # 3. One month to prepare (computed)
    r = grid_search("earth", ("2025-08-01", "2025-08-01"), "2027-06-01")
    _, g = direct_flyby("earth", r["t1"], r["t2"], "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "earth-1month", "name": "One month to build a rocket", "kind": "computed", "color": "#ff6b8b",
         "summary": "Allow a month of preparation after discovery and launch on 1 August 2025. By then Earth has moved "
                    "and 3I/ATLAS is closer to the Sun, so the best intercept needs even more energy than launching on day one."}, g)

    # 4. Probe waiting at Mars
    _, g = direct_flyby("mars", jd("2025-07-01"), jd("2025-10-03"), "300 km low Mars orbit", "Depart low Mars orbit")
    g["burns"][0]["dv"] = round(departure_dv(g["stats"]["vinf"], "mars", 300), 2)
    add({"id": "mars-staged", "name": "Probe waiting at Mars", "kind": "paper", "source": Y25, "color": "#e0623a",
         "summary": "3I/ATLAS passed just 0.19 AU from Mars. A spacecraft already orbiting Mars could have left on "
                    "discovery day and met it on 3 October 2025 with a modest burn. This is the case for staging "
                    "interceptors around other planets.",
         "paper": "v∞ 3.54 km/s, flyby at 86.43 km/s"}, g)

    # 5. Juno redirect (paper ΔV; heliocentric arc approximated from Jupiter)
    t1, t2 = jd("2025-09-09"), jd("2026-03-14")
    r = body_to_comet("jupiter", t1, t2)
    add({"id": "juno", "name": "Redirect Juno at Jupiter", "kind": "paper", "color": "#d9a877",
         "source": {"label": "Loeb, Hibberd & Crowl 2025 — Intercepting 3I/ATLAS at closest approach to Jupiter with Juno",
                    "url": "https://arxiv.org/abs/2507.21402"},
         "summary": "NASA's Juno was already orbiting Jupiter. Two burns in September 2025 totalling 2.68 km/s (a "
                    "Jupiter Oberth manoeuvre) would have sent it to 3I/ATLAS near its closest pass by Jupiter on "
                    "14 March 2026. The path shown is a heliocentric approximation of that transfer.",
         "paper": "2.1574 + 0.5181 km/s burns, flyby at 66.5 km/s"},
        dict(burns=[burn(t1, "jupiter", 2.1574, "Burn 1: lower perijove (paper value)"),
                    burn(t1 + 0.01, "jupiter", 0.5181, "Burn 2: at perijove, Jupiter Oberth manoeuvre (paper value)")],
             legs=[leg_samples(r["r1"], r["v1"], t1, t2)], encounter=encounter(t2, r["r2"], 66.54),
             stats={"vinf": round(r["vinf"], 2), "park": "Juno's polar orbit around Jupiter"}))

    # 6. Probe waiting at Saturn (computed) — spoiler: nowhere near the path
    r = grid_search("saturn", ("2025-07-01", "2026-07-01"), "2027-12-01", ddep=5, darr=5)
    _, g = direct_flyby("saturn", r["t1"], r["t2"], "Low Saturn orbit (60,000 km radius)", "Depart low Saturn orbit")
    add({"id": "saturn-staged", "name": "Probe waiting at Saturn", "kind": "computed", "color": "#e6d49a",
         "summary": "What if we had parked interceptors at the outer planets? For 3I/ATLAS, Saturn was nowhere near "
                    "its path, so even with a deep Oberth burn in Saturn's gravity well this needs a huge ΔV. "
                    "Staging only helps if the object happens to pass near your planet."}, g)

    # 7. Rendezvous (computed): match velocity and fly alongside
    r = grid_search("earth", ("2025-07-01", "2026-07-01"), "2030-01-01", rendezvous=True, ddep=5, darr=10)
    dvL = departure_dv(r["vinf"], "earth")
    add({"id": "rendezvous", "name": "Stop alongside it", "kind": "computed", "color": "#c49bff",
         "summary": "Every other plan is a flyby at tens of km/s, lasting seconds. To orbit or land, you have to match "
                    "3I/ATLAS's velocity, which means chasing it out of the solar system at around 60 km/s. This is the "
                    "cheapest version that arrives before 2030. It would need fusion or antimatter propulsion.",
         }, dict(burns=[burn(r["t1"], "earth", dvL, "Launch from low Earth orbit"),
                        burn(r["t2"], "atlas", r["rel"], "Braking burn to match 3I/ATLAS")],
                 legs=[leg_samples(r["r1"], r["v1"], r["t1"], r["t2"])], encounter=encounter(r["t2"], r["r2"], 0.0),
                 stats={"vinf": round(r["vinf"], 2), "c3": round(r["vinf"] ** 2, 1), "park": "200 km low Earth orbit"}))

    # 8. Brute-force direct chase from Earth in 2035 (computed)
    r = grid_search("earth", ("2035-01-01", "2035-12-31"), "2085-12-31", ddep=5, darr=30, min_tof=50 * 365.25 - 1)
    r = body_to_comet("earth", r["t1"], r["t1"] + 50 * 365.25)
    _, g = direct_flyby("earth", r["t1"], r["t2"], "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "direct-chase", "name": "Brute-force chase (2035)", "kind": "computed", "color": "#8a94ab",
         "summary": "No tricks: launch straight at 3I/ATLAS in 2035 and catch it 50 years later. Compare its total ΔV "
                    "with the solar Oberth plan below, which has the same launch year and flight time."}, g)

    # 9-10. Solar Oberth (Hibberd, Eubanks & Hein 2026)
    H26 = {"label": "Hibberd, Eubanks & Hein 2026 — Catching 3I/ATLAS using a Solar Oberth",
           "url": "https://arxiv.org/abs/2601.02533"}
    _, g = solar_oberth(50)
    add({"id": "solar-oberth", "name": "Solar Oberth slingshot (50 yr)", "kind": "paper", "source": H26, "color": "#ffd166",
         "summary": "Launch in 2035 to Jupiter, whose gravity cancels the probe's sideways motion so it falls straight "
                    "at the Sun. It skims 3.2 solar radii from the Sun's centre at about 345 km/s and fires an 8 km/s "
                    "burn there, where the Oberth effect multiplies its value. It catches 3I/ATLAS around 732 AU from "
                    "the Sun, 50 years later. Needs a heat shield and solid rocket stages, or a refuelled Starship.",
         "paper": "C3 130.2 km²/s², SOM ΔV 8.355 km/s, 732 AU, arrives at 16 km/s"}, g)

    _, g = solar_oberth(10)
    add({"id": "solar-oberth-fast", "name": "Solar Oberth, 10-year sprint", "kind": "paper", "source": H26, "color": "#ff7b72",
         "summary": "The same slingshot, but squeezed into 10 years. The burn at the Sun balloons to about 30 km/s and "
                    "the probe screams past 3I/ATLAS at around 85 km/s, 240 AU out. The paper judged flights under "
                    "30–40 years untenable.",
         "paper": "SOM ΔV 29.99 km/s, 239 AU, arrives at 85 km/s"}, g)

    return missions


if __name__ == "__main__":
    print("Building missions ...", file=sys.stderr)
    ms = build()
    out = DATA / "missions.json"
    out.write_text(json.dumps({"missions": ms}, separators=(",", ":")))
    print(f"Wrote {out} ({out.stat().st_size / 1e3:.0f} kB)", file=sys.stderr)
