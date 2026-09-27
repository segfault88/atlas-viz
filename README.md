# 3I/ATLAS Tracker

Interactive 3D view of the interstellar comet **3I/ATLAS (C/2025 N1)** passing through the solar system.

**Live:** https://segfault88.github.io/atlas-viz/

Drag the timeline to move through time, and click the markers to jump to events such as perihelion and the close approaches to Mars, Earth and Jupiter. You can also fly hypothetical intercept missions, from redirecting Juno to a 50-year solar Oberth slingshot.

Positions come from [NASA/JPL Horizons](https://ssd.jpl.nasa.gov/horizons/). The dashed orange section of the path comes after the last observation in JPL's orbit fit, so it is a prediction.

## Intercept missions

The side panel lists hypothetical spacecraft missions to 3I/ATLAS, ranked by total ΔV. The ΔV is measured from a low parking orbit around the starting planet, so Earth launches include the burn out of Earth orbit. Clicking a mission flies a probe along its trajectory. The mission's burns and encounter appear on the timeline, and long missions switch the timeline to a decades-long range.

| Mission | Total ΔV (km/s) | Launch → intercept | Time to intercept | Flyby speed (km/s) | Basis |
| --- | ---: | --- | --- | ---: | --- |
| Probe waiting at Mars | 2.6 | 1 Jul 2025 → 3 Oct 2025 | 94 days (~3 months) | 86.7 | Yaginuma et al. 2025 |
| Redirect Juno at Jupiter | 2.7 | 9 Sep 2025 → 14 Mar 2026 | 186 days (~6 months) | 66.5 | Loeb, Hibberd & Crowl 2025 |
| If we'd known in advance (Jan 2025 launch) | 5.2 | 10 Jan 2025 → 15 Sep 2025 | 248 days (~8 months) | 80.0 | Yaginuma et al. 2025 |
| Solar Oberth slingshot (2035 → 2085, 732 AU) | 16.4 | Jul 2035 → Jul 2085 | 50 years | 15.2 | Hibberd, Eubanks & Hein 2026 |
| Launch the day it was found | 18.6 | 1 Jul 2025 → 15 Nov 2025 | 137 days (~4.5 months) | 79.7 | Yaginuma et al. 2025 |
| One month to build a rocket | 24.8 | 1 Aug 2025 → 1 Dec 2025 | 122 days (~4 months) | 69.3 | computed here |
| Probe waiting at Saturn | 36.6 | 1 Jul 2025 → 30 Nov 2027 | 2.4 years (883 days) | 22.6 | computed here |
| Stop alongside it (rendezvous by 2030) | 38.0 | Sep 2025 → Dec 2029 | 4.3 years | matched | computed here |
| Solar Oberth, 10-year sprint | 39.3 | Jul 2035 → Jul 2045 | 10 years | 87.9 | Hibberd, Eubanks & Hein 2026 |
| Brute-force chase (2035) | 45.0 | Sep 2035 → Sep 2085 | 50 years | 11.5 | computed here |

The trajectories are patched two-body arcs between real JPL positions, solved with a Lambert solver. The solar Oberth cases are re-optimised with scipy. They reproduce the published figures closely: the Earth and Mars cases of Yaginuma et al. match to within 0.01 km/s, and the 2035 solar Oberth reconstruction gives an 8.14 km/s burn at the Sun against the paper's 8.36. They are illustrations, not high-fidelity mission designs. For Juno, the ΔV is the paper's value; only the path is approximated.

References:

- Yaginuma et al. 2025, [The Feasibility of a Spacecraft Flyby with the Third Interstellar Object 3I/ATLAS from Earth or Mars](https://arxiv.org/abs/2507.15755)
- Loeb, Hibberd & Crowl 2025, [Intercepting 3I/ATLAS at Closest Approach to Jupiter with the Juno Spacecraft](https://arxiv.org/abs/2507.21402)
- Hibberd, Eubanks & Hein 2026, [Catching 3I/ATLAS Using a Solar Oberth](https://arxiv.org/abs/2601.02533)

## Development

```sh
npm install
npm run dev        # local dev server
npm run build      # type-check + production build into dist/
```

Pushing to `main` builds and deploys to GitHub Pages (`.github/workflows/deploy.yml`).

## Project layout

| Path | What it does |
| --- | --- |
| `index.html` | Page markup (panels, timeline) |
| `src/main.ts` | Entry point: wires everything together and runs the frame loop |
| `src/ephemeris.ts` | Loads the data and interpolates positions at any time |
| `src/scene.ts` | Three.js world: Sun, planets, orbits, comet trail, camera follow |
| `src/labels.ts` | HTML labels that follow 3D objects |
| `src/hud.ts` | Info panel, event card, legend |
| `src/timeline.ts` | Timeline slider, event markers, playback |
| `src/missions.ts` | Mission data and probe position lookup |
| `src/missionLayer.ts` | 3D paths, probe, burn and encounter markers for missions |
| `src/missionPanel.ts` | Side panel listing missions with ΔV bars and details |
| `scripts/fetch_data.py` | Downloads ephemerides from JPL Horizons and computes events |
| `scripts/orbits.py` | Lambert solver, conic sampling, departure-burn maths |
| `scripts/missions.py` | Builds the intercept missions (two-body patched conics, scipy optimiser) |
| `data/ephemeris.json` | Generated data (heliocentric ecliptic J2000, AU, 12 h steps, 2024–2028) |
| `data/ephemeris-far.json` | Same at 5-day steps for 2028–2090 (loaded only for long missions) |
| `data/missions.json` | Generated mission trajectories |

## Refreshing the data

```sh
npm run fetch-data   # needs python3; no extra packages required
npm run missions     # rebuild missions.json; needs numpy + scipy (takes a few minutes)
```
