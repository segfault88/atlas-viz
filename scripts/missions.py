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

from orbits import (AU_KM, DATA, KMS, PLANET_GM, PLANET_R, Ephemeris, departure_dv, iso, jd, lambert,
                    sample_conic)

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


def alt_text(km):
    """Human-friendly flyby altitude."""
    return f"{km:,.0f} km" if km < 10000 else f"{km / 1000:,.0f} thousand km"


def solar_oberth(years, radii=3.2, seed=1):
    """Earth → Jupiter (unpowered flyby) → burn at `radii` solar radii → 3I/ATLAS.

    Mirrors the E-J-SOM-3I sequence of Hibberd, Eubanks & Hein (2026), launch year 2035.
    """
    r_som = radii * R_SUN_AU

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
               burn(d["tJ"], "jupiter", d["dvJ"], f"Jupiter gravity assist (passes {alt_text(d['rpJ'])} above the cloud tops)"),
               burn(d["tS"], "sun", d["dvS"], f"Solar Oberth burn at {radii:g} solar radii, moving at {d['vperi']:.0f} km/s")],
        legs=[leg_samples(d["rE"], d["a1"], d["tE"], d["tJ"]),
              leg_samples(d["rJ"], d["b1"], d["tJ"], d["tS"], 400),
              leg_samples(d["rS"], d["c1"], d["tS"], d["tA"], 500)],
        encounter=encounter(d["tA"], d["rA"], d["rel"]),
        stats={"vinf": round(d["vinfE"], 2), "c3": round(d["vinfE"] ** 2, 1), "park": "200 km low Earth orbit",
               "perihelionSpeed": round(d["vperi"], 1)},
    )


def powered_flyby(vin, vout, mu, r_min):
    """ΔV (km/s) for a flyby that turns v∞-in into v∞-out with a single burn at periapsis.

    vin/vout are planet-relative hyperbolic excess velocities in km/s. If the turn needs a
    periapsis below r_min, the shortfall is made up with a (costly) non-Oberth turn.
    Returns (ΔV, periapsis radius in km).
    """
    a, b = np.linalg.norm(vin), np.linalg.norm(vout)
    delta = math.acos(np.clip(np.dot(vin, vout) / (a * b), -1, 1))

    def turn(rp):
        return math.asin(1 / (1 + rp * a * a / mu)) + math.asin(1 / (1 + rp * b * b / mu))

    def burn_at(rp):
        return abs(math.sqrt(b * b + 2 * mu / rp) - math.sqrt(a * a + 2 * mu / rp))

    if turn(r_min) < delta:
        return burn_at(r_min) + 2 * b * math.sin((delta - turn(r_min)) / 2), r_min
    lo, hi = r_min, 1e12  # turn(rp) decreases with rp
    for _ in range(200):
        m = math.sqrt(lo * hi)
        if turn(m) > delta:
            lo = m
        else:
            hi = m
    return burn_at(lo), lo


def planet_assist(planet, dep_window, dJ, dA, cap_years, r_min, seed=1):
    """Earth → powered flyby of `planet` → 3I/ATLAS, minimising total ΔV from low Earth orbit."""
    mu = PLANET_GM[planet]

    def solve(p):
        tE, d1, d2 = p
        tP, tA = tE + d1, tE + d1 + d2
        if tA > tE + cap_years * 365.25:
            return 1e3, None
        rE, vE = eph.state("earth", tE)
        rP, vP = eph.state(planet, tP)
        rA, vA = eph.state("atlas", tA)
        best = (1e3, None)
        for _, a1, a2 in arc(rE, rP, tE, tP):
            vinfE = np.linalg.norm(a1 - vE) * KMS
            dvE = departure_dv(vinfE, "earth")
            for _, b1, b2 in arc(rP, rA, tP, tA):
                dvP, rp = powered_flyby((a2 - vP) * KMS, (b1 - vP) * KMS, mu, r_min)
                cost = dvE + dvP
                if cost < best[0]:
                    best = (cost, dict(tE=tE, tP=tP, tA=tA, rE=rE, rP=rP, rA=rA, a1=a1, b1=b1, vinfE=vinfE,
                                       dvE=dvE, dvP=dvP, rp=rp, rel=np.linalg.norm(b2 - vA) * KMS))
        return best

    bounds = [(jd(dep_window[0]), jd(dep_window[1])), dJ, dA]
    res = differential_evolution(lambda p: solve(p)[0], bounds, seed=seed, popsize=30, maxiter=600,
                                 tol=1e-10, atol=1e-8, polish=True)
    return solve(res.x)[1]


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
    add({"id": "hindsight", "name": "If we'd known in advance", "kind": "paper", "source": Y25,
         "summary": "The cheapest direct launch from Earth left in January 2025, six months before 3I/ATLAS was "
                    "discovered. Needs a hyperbolic excess speed of only 6.9 km/s, within reach of today's rockets.",
         "paper": "v∞ 6.94 km/s, flyby at 79.96 km/s"}, g)

    # 2. Launch on discovery day
    _, g = direct_flyby("earth", jd("2025-07-01"), jd("2025-11-15"), "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "earth-discovery", "name": "Launch the day it was found", "kind": "paper", "source": Y25,
         "summary": "The best direct Earth launch after discovery: lift off on 1 July 2025. It needs v∞ = 24 km/s "
                    "(C3 ≈ 576 km²/s²), nearly double the record set by New Horizons (v∞ ≈ 12.6 km/s). That is far beyond any existing launcher.",
         "paper": "v∞ 24.0 km/s, flyby at 79.73 km/s"}, g)

    # 3. One month to prepare (computed)
    r = grid_search("earth", ("2025-08-01", "2025-08-01"), "2027-06-01")
    _, g = direct_flyby("earth", r["t1"], r["t2"], "200 km low Earth orbit", "Launch from low Earth orbit")
    add({"id": "earth-1month", "name": "One month to build a rocket", "kind": "computed",
         "summary": "Allow a month of preparation after discovery and launch on 1 August 2025. By then Earth has moved "
                    "and 3I/ATLAS is closer to the Sun, so the best intercept needs even more energy than launching on day one."}, g)

    # 4. Probe waiting at Mars
    _, g = direct_flyby("mars", jd("2025-07-01"), jd("2025-10-03"), "300 km low Mars orbit", "Depart low Mars orbit")
    g["burns"][0]["dv"] = round(departure_dv(g["stats"]["vinf"], "mars", 300), 2)
    add({"id": "mars-staged", "name": "Probe waiting at Mars", "kind": "paper", "source": Y25,
         "summary": "3I/ATLAS passed just 0.19 AU from Mars. A spacecraft already orbiting Mars could have left on "
                    "discovery day and met it on 3 October 2025 with a modest burn. This is the case for staging "
                    "interceptors around other planets.",
         "paper": "v∞ 3.54 km/s, flyby at 86.43 km/s"}, g)

    # 5. Juno redirect (paper ΔV; heliocentric arc approximated from Jupiter)
    t1, t2 = jd("2025-09-09"), jd("2026-03-14")
    r = body_to_comet("jupiter", t1, t2)
    add({"id": "juno", "name": "Redirect Juno at Jupiter", "kind": "paper",
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
    add({"id": "saturn-staged", "name": "Probe waiting at Saturn", "kind": "computed",
         "summary": "What if we had parked interceptors at the outer planets? For 3I/ATLAS, Saturn was nowhere near "
                    "its path, so even with a deep Oberth burn in Saturn's gravity well this needs a huge ΔV. "
                    "Staging only helps if the object happens to pass near your planet."}, g)

    # 7. Rendezvous (computed): match velocity and fly alongside
    r = grid_search("earth", ("2025-07-01", "2026-07-01"), "2030-01-01", rendezvous=True, ddep=5, darr=10)
    dvL = departure_dv(r["vinf"], "earth")
    add({"id": "rendezvous", "name": "Stop alongside it", "kind": "computed",
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
    add({"id": "direct-chase", "name": "Brute-force chase (2035)", "kind": "computed",
         "summary": "No tricks: launch straight at 3I/ATLAS in 2035 and catch it 50 years later. Compare its total ΔV "
                    "with the solar Oberth plan below, which has the same launch year and flight time."}, g)

    # 9-10. Solar Oberth (Hibberd, Eubanks & Hein 2026)
    H26 = {"label": "Hibberd, Eubanks & Hein 2026 — Catching 3I/ATLAS using a Solar Oberth",
           "url": "https://arxiv.org/abs/2601.02533"}
    _, g = solar_oberth(50)
    add({"id": "solar-oberth", "name": "Solar Oberth slingshot (50 yr)", "kind": "paper", "source": H26,
         "summary": "Launch in 2035 to Jupiter, whose gravity cancels the probe's sideways motion so it falls straight "
                    "at the Sun. It skims 3.2 solar radii from the Sun's centre at about 345 km/s and fires an 8 km/s "
                    "burn there, where the Oberth effect multiplies its value. It catches 3I/ATLAS around 732 AU from "
                    "the Sun, 50 years later. Needs a heat shield and solid rocket stages, or a refuelled Starship.",
         "paper": "C3 130.2 km²/s², SOM ΔV 8.355 km/s, 732 AU, arrives at 16 km/s"}, g)

    _, g = solar_oberth(10)
    add({"id": "solar-oberth-fast", "name": "Solar Oberth, 10-year sprint", "kind": "paper", "source": H26,
         "summary": "The same slingshot, but squeezed into 10 years. The burn at the Sun balloons to about 30 km/s and "
                    "the probe screams past 3I/ATLAS at around 85 km/s, 240 AU out. The paper judged flights under "
                    "30–40 years untenable.",
         "paper": "SOM ΔV 29.99 km/s, 239 AU, arrives at 85 km/s"}, g)


    # ---------- Rough ideas: back-of-envelope, loosely modelled ----------

    # R1. Jupiter Oberth catch-up: launch 2025–2030, burn deep in Jupiter's gravity well
    rj_min = PLANET_R["jupiter"] + 10000
    best, per_year = None, []
    for y0, y1 in (("2025-07-01", "2025-12-31"), *((f"{y}-01-01", f"{y}-12-31") for y in range(2026, 2031))):
        d = planet_assist("jupiter", (y0, y1), (150, 2000), (100, 50 * 365), 50, rj_min)
        per_year.append((y0[:4], d["dvE"] + d["dvP"]))
        if best is None or d["dvE"] + d["dvP"] < best["dvE"] + best["dvP"]:
            best = d
    d = best
    years_txt = ", ".join(f"{y}: {v:.0f}" for y, v in per_year)
    add({"id": "jupiter-oberth", "name": "Jupiter Oberth catch-up", "kind": "rough",
         "summary": "Launch in the next few years, dive to 1.1 Jupiter radii and fire a big burn at the bottom of Jupiter's "
                    "gravity well to chase 3I/ATLAS out of the solar system (flight time capped at 50 years). Jupiter's well "
                    "is far shallower than the Sun's, so this costs about twice the solar Oberth plan. "
                    f"Best total ΔV by launch year (km/s): {years_txt}."},
        dict(burns=[burn(d["tE"], "earth", d["dvE"], "Launch from low Earth orbit"),
                    burn(d["tP"], "jupiter", d["dvP"], f"Burn at perijove, {(d['rp'] - PLANET_R['jupiter']) / 1000:,.0f} thousand km above the cloud tops")],
             legs=[leg_samples(d["rE"], d["a1"], d["tE"], d["tP"]), leg_samples(d["rP"], d["b1"], d["tP"], d["tA"], 500)],
             encounter=encounter(d["tA"], d["rA"], d["rel"]),
             stats={"vinf": round(d["vinfE"], 2), "c3": round(d["vinfE"] ** 2, 1), "park": "200 km low Earth orbit"}))

    # R2. Waiting at Sun–Earth L2 like ESA's Comet Interceptor: fall back to Earth and burn at perigee
    r = grid_search("earth", ("2025-07-01", "2025-09-30"), "2026-06-01", ddep=2, darr=2)
    mu, rp = PLANET_GM["earth"], PLANET_R["earth"] + 200
    dv_l2 = math.sqrt(r["vinf"] ** 2 + 2 * mu / rp) - math.sqrt(2 * mu / rp)
    add({"id": "l2-waiting", "name": "Probe waiting at L2 (Comet Interceptor style)", "kind": "rough",
         "summary": "ESA's Comet Interceptor (launching ~2029) will park at the Sun–Earth L2 point, 1.5 million km from Earth, "
                    "and wait for a target. From there it can fall back past Earth and burn at perigee, for about 1.5 km/s of "
                    "effective ΔV. 3I/ATLAS would have needed about ten times that, even with the head start.",
         "source": {"label": "ESA — Comet Interceptor", "url": "https://www.esa.int/Science_Exploration/Space_Science/Comet_Interceptor"}},
        dict(burns=[burn(r["t1"], "earth", dv_l2, "Leave L2, burn at Earth perigee (200 km)")],
             legs=[leg_samples(r["r1"], r["v1"], r["t1"], r["t2"])], encounter=encounter(r["t2"], r["r2"], r["rel"]),
             stats={"vinf": round(r["vinf"], 2), "c3": round(r["vinf"] ** 2, 1), "park": "Sun–Earth L2 halo orbit"}))

    # R3. Probe waiting at Venus
    r = grid_search("venus", ("2025-07-01", "2026-01-31"), "2026-12-31", ddep=2, darr=2)
    _, g = direct_flyby("venus", r["t1"], r["t2"], "300 km low Venus orbit", "Depart low Venus orbit")
    g["burns"][0]["dv"] = round(departure_dv(g["stats"]["vinf"], "venus", 300), 2)
    add({"id": "venus-staged", "name": "Probe waiting at Venus", "kind": "rough",
         "summary": "3I/ATLAS passed 0.65 AU from Venus in early November 2025. A spacecraft parked in Venus orbit could "
                    "have caught it, but it passed over three times farther from Venus than from Mars, so the burn is "
                    "roughly three times bigger than the Mars option."}, g)

    # R4. Earth launch with a Mars (or Venus) flyby on the way
    dM = planet_assist("mars", ("2025-07-01", "2025-12-31"), (20, 700), (5, 900), 3, PLANET_R["mars"] + 200)
    dV = planet_assist("venus", ("2025-07-01", "2025-10-31"), (20, 400), (5, 900), 3, PLANET_R["venus"] + 200)
    d = dM
    add({"id": "mars-assist", "name": "Launch via a Mars flyby", "kind": "rough",
         "summary": "Launch after discovery and swing past Mars to boost toward 3I/ATLAS. It doesn't help: Mars was about "
                    "2 AU away on the far side of the Sun, so by the time a probe could get there the comet was long gone, "
                    "and Mars's weak gravity can't bend the path far enough. A Venus flyby works geometrically "
                    f"({dV['dvE'] + dV['dvP']:.1f} km/s total) but is still slightly worse than launching straight at it."},
        dict(burns=[burn(d["tE"], "earth", d["dvE"], "Launch from low Earth orbit"),
                    burn(d["tP"], "mars", d["dvP"], f"Burn during Mars flyby ({(d['rp'] - PLANET_R['mars']):,.0f} km altitude)")],
             legs=[leg_samples(d["rE"], d["a1"], d["tE"], d["tP"]), leg_samples(d["rP"], d["b1"], d["tP"], d["tA"])],
             encounter=encounter(d["tA"], d["rA"], d["rel"]),
             stats={"vinf": round(d["vinfE"], 2), "c3": round(d["vinfE"] ** 2, 1), "park": "200 km low Earth orbit"}))

    # R5. Solar Oberth burn distance: Parker Solar Probe's perihelion vs skimming the photosphere
    for radii, mid, name, blurb in (
        (9.86, "solar-oberth-parker", "Solar Oberth at Parker Solar Probe distance",
         "The same 2035 slingshot, but with the burn at 9.86 solar radii, the closest any spacecraft has actually been "
         "(Parker Solar Probe, 2024). Today's heat-shield technology would work, but the shallower dive costs more ΔV."),
        (2.0, "solar-oberth-2rs", "Solar Oberth skimming the Sun (2 R☉)",
         "Push the burn to 2 solar radii, just 700,000 km above the Sun's surface, where the probe moves at about 440 km/s. "
         "The deeper dive saves ΔV, but no heat shield we know how to build would survive."),
    ):
        _, g = solar_oberth(50, radii)
        add({"id": mid, "name": name, "kind": "rough", "summary": blurb}, g)

    # R6. Laser light sail: straight-line flight at 1% of light speed (gravity negligible)
    t0 = jd("2050-01-01")
    v_sail = 0.01 * 299792.458 / KMS  # AU/day
    rE, _ = eph.state("earth", t0)
    lo, hi = t0, t0 + 5 * 365.25   # find t with |r_comet(t) - r_E(t0)| = v (t - t0)
    for _ in range(100):
        m = (lo + hi) / 2
        if np.linalg.norm(eph.state("atlas", m)[0] - rE) > v_sail * (m - t0):
            lo = m
        else:
            hi = m
    tA = (lo + hi) / 2
    rA, vA = eph.state("atlas", tA)
    vel = (rA - rE) / (tA - t0)
    ts = np.linspace(t0, tA, 50)
    add({"id": "light-sail", "name": "Laser light sail (2050)", "kind": "rough", "propulsion": "laser",
         "summary": "A Breakthrough Starshot-style gram-scale sail, pushed by a gigawatt ground laser array to 1% of light "
                    "speed in minutes. It needs no rocket ΔV at all, just a laser that doesn't exist yet. It reaches "
                    f"3I/ATLAS in about {tA - t0:.0f} days and passes it at about 3,000 km/s. The path is a straight line, "
                    "since the Sun's gravity barely matters at that speed."},
        dict(burns=[burn(t0, "earth", 0.0, "Laser array accelerates the sail to ~3,000 km/s (1% of light speed)")],
             legs=[{"t": [round(float(t), 5) for t in ts],
                    "p": [round(float(x), 6) for t in ts for x in rE + vel * (t - t0)]}],
             encounter=encounter(tA, rA, np.linalg.norm(vel - vA) * KMS),
             stats={"park": "Earth (ground-based laser)"}))

    return missions


if __name__ == "__main__":
    print("Building missions ...", file=sys.stderr)
    ms = build()
    out = DATA / "missions.json"
    out.write_text(json.dumps({"missions": ms}, separators=(",", ":")))
    print(f"Wrote {out} ({out.stat().st_size / 1e3:.0f} kB)", file=sys.stderr)
