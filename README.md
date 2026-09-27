# 3I/ATLAS Tracker

Interactive 3D view of the interstellar comet **3I/ATLAS (C/2025 N1)** moving through the solar system.

- Positions for the comet and planets come from the NASA/JPL Horizons API. They are heliocentric ecliptic J2000 vectors sampled every 12 h and interpolated with cubic Hermite splines.
- Event markers (perihelion, close approaches, solar conjunction, ecliptic crossing) are computed from that data. Discovery and the observed-arc dates are also marked.
- The dashed orange part of the path comes after the last observation in JPL's orbit fit, so it is a prediction.

## Usage

Open `index.html` in a browser. It is a single self-contained file; Three.js loads from a CDN.

## Rebuilding

```sh
python3 scripts/fetch_data.py   # refresh data/ephemeris.json from JPL Horizons
python3 scripts/build.py        # embed data into src/template.html -> index.html
```
