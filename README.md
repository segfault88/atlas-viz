# 3I/ATLAS Tracker

Interactive 3D view of the interstellar comet **3I/ATLAS (C/2025 N1)** passing through the solar system.

**Live:** https://segfault88.github.io/atlas-viz/

Drag the timeline to move through time, and click the markers to jump to events such as perihelion and the close approaches to Mars, Earth and Jupiter.

The **Intercept missions** panel plots hypothetical spacecraft trajectories to 3I/ATLAS, ranked by total ΔV. It includes published studies (redirecting Juno, a probe waiting at Mars, the 2035 solar Oberth slingshot) and some computed what-ifs (a probe parked at Saturn, stopping alongside the comet, a brute-force chase).

Positions come from [NASA/JPL Horizons](https://ssd.jpl.nasa.gov/horizons/). The dashed orange section of the path comes after the last observation in JPL's orbit fit, so it is a prediction.

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

Mission trajectories are patched two-body arcs between real JPL positions, solved with a Lambert solver. They reproduce the published figures closely, e.g. the Earth and Mars cases of Yaginuma et al. to within 0.01 km/s. They are not high-fidelity mission designs.
