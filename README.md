# 3I/ATLAS Tracker

Interactive 3D view of the interstellar comet **3I/ATLAS (C/2025 N1)** passing through the solar system.

**Live:** https://segfault88.github.io/atlas-viz/

 Drag the timeline to move through time, and click the markers to jump to events such as perihelion and the close approaches to Mars, Earth and Jupiter.

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
| `scripts/fetch_data.py` | Downloads ephemerides from JPL Horizons and computes events |
| `data/ephemeris.json` | Generated data (heliocentric ecliptic J2000, AU, 12 h steps) |

## Refreshing the data

```sh
npm run fetch-data   # needs python3; no extra packages required
```
