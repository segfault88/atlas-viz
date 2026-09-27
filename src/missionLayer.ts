/**
 * 3D rendering of intercept missions: the selected mission's planned path, travelled
 * path, probe, burn points and encounter point, plus faint paths for all missions.
 */
import * as THREE from 'three';
import { makeDot, makeSegment, setSegment } from './scene';
import { missions, pathSamples, probePositionAt, sampleIndex, type Mission } from './missions';

export const PROBE_COLOR = 0xff5fc8;
const GHOST_COLOR = 0x8a94ab;

type Path = ReturnType<typeof pathSamples>;

export interface MissionLabel { pos: THREE.Vector3; text: string; cls: string; priority: number }

export class MissionLayer {
  readonly probePos = new THREE.Vector3();
  selected: Mission | null = null;
  /** Probe → comet distance (AU) and heliocentric speed (km/s) at the last update. */
  probeToComet = 0;
  probeSpeed = 0;

  private readonly root = new THREE.Group();
  private readonly ghosts = new THREE.Group();
  private readonly paths = new Map<string, Path>();
  private readonly sel = new THREE.Group();
  private readonly probe = makeDot(PROBE_COLOR, 9);
  private readonly probeGlow = makeDot(PROBE_COLOR, 26);
  private readonly link = makeSegment(new THREE.LineDashedMaterial({ color: PROBE_COLOR, transparent: true, opacity: 0.55 }));
  private planned: THREE.Line | null = null;
  private travelled = new THREE.Line();
  private travelledPos = new Float32Array(0);
  private burnPoints: { pos: THREE.Vector3; dv: number }[] = [];
  private encounterPoint: { pos: THREE.Vector3; text: string } | null = null;
  launched = false;

  constructor(scene: THREE.Scene) {
    for (const m of missions) {
      const path = pathSamples(m);
      this.paths.set(m.id, path);
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(path.p),
        new THREE.LineBasicMaterial({ color: GHOST_COLOR, transparent: true, opacity: 0.35 }));
      line.userData.id = m.id;
      this.ghosts.add(line);
    }
    this.ghosts.visible = false;
    (this.probeGlow.material as THREE.PointsMaterial).opacity = 0.35;
    this.probe.renderOrder = this.probeGlow.renderOrder = 11;
    this.root.add(this.ghosts, this.sel);
    scene.add(this.root);
  }

  set showAll(v: boolean) { this.ghosts.visible = v; }
  get showAll() { return this.ghosts.visible; }

  select(m: Mission | null) {
    this.selected = m;
    this.sel.clear();
    this.burnPoints = [];
    this.encounterPoint = null;
    for (const g of this.ghosts.children) g.visible = g.userData.id !== m?.id;
    if (!m) return;

    const path = this.paths.get(m.id)!;
    const planned = new THREE.Line(new THREE.BufferGeometry().setFromPoints(path.p),
      new THREE.LineDashedMaterial({ color: PROBE_COLOR, transparent: true, opacity: 0.45, dashSize: 0.05, gapSize: 0.05 }));
    planned.computeLineDistances();
    this.planned = planned;

    this.travelledPos = new Float32Array((path.p.length + 1) * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.travelledPos, 3));
    this.travelled = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: PROBE_COLOR }));
    this.travelled.frustumCulled = false;

    this.sel.add(planned, this.travelled, this.link, this.probeGlow, this.probe);

    // Burn and encounter markers
    for (const b of m.burns) {
      if (b.dv < 0.05) continue; // unpowered flyby: no marker
      const pos = probePositionAt(path, b.jd + 1e-6);
      // Burns at (nearly) the same place, e.g. Juno's two burns, share one marker
      const same = this.burnPoints.find(p => p.pos.distanceTo(pos) < 1e-3);
      if (same) { same.dv += b.dv; continue; }
      const dot = makeDot(0xffffff, 6);
      dot.position.copy(pos);
      this.sel.add(dot);
      this.burnPoints.push({ pos, dv: b.dv });
    }
    const e = m.encounter;
    const epos = probePositionAt(path, e.jd);
    const ring = makeDot(PROBE_COLOR, 14);
    (ring.material as THREE.PointsMaterial).opacity = 0.5;
    ring.position.copy(epos);
    this.sel.add(ring);
    this.encounterPoint = {
      pos: epos,
      text: e.relSpeed > 0.05 ? `Flyby at ${e.relSpeed.toFixed(1)} km/s` : 'Rendezvous',
    };
  }

  update(t: number, cometPos: THREE.Vector3, camDist: number) {
    const m = this.selected;
    if (!m) return;
    const path = this.paths.get(m.id)!;
    const launch = path.t[0], end = path.t[path.t.length - 1];
    // Dashes are in world units; scale them with zoom so they stay visible at any distance
    const dash = this.planned!.material as THREE.LineDashedMaterial;
    dash.dashSize = dash.gapSize = camDist * 0.01;
    this.launched = t >= launch;

    probePositionAt(path, t, this.probePos);
    this.probe.position.copy(this.probePos);
    this.probeGlow.position.copy(this.probePos);
    this.probe.visible = this.probeGlow.visible = this.launched;

    // Travelled path up to t
    const k = sampleIndex(path.t, t);
    const count = k < 0 ? 0 : Math.min(k + 2, path.p.length);
    for (let j = 0; j <= k && j < path.p.length; j++) {
      const p = path.p[j];
      this.travelledPos.set([p.x, p.y, p.z], 3 * j);
    }
    if (k >= 0 && k < path.p.length - 1) this.travelledPos.set([this.probePos.x, this.probePos.y, this.probePos.z], 3 * (k + 1));
    this.travelled.geometry.setDrawRange(0, count);
    this.travelled.geometry.getAttribute('position').needsUpdate = true;

    // Probe → comet link while in flight
    this.link.visible = this.launched && t < end;
    if (this.link.visible) setSegment(this.link, this.probePos, cometPos, camDist * 0.008);
    this.probeToComet = this.probePos.distanceTo(cometPos);

    // Speed from the path samples around t (km/s)
    const i = Math.min(Math.max(k, 0), path.t.length - 2);
    const dt = path.t[i + 1] - path.t[i];
    this.probeSpeed = this.launched && t < end ? path.p[i + 1].distanceTo(path.p[i]) / dt * 149597870.7 / 86400 : 0;
  }

  /** Labels to draw this frame. */
  labels(): MissionLabel[] {
    const out: MissionLabel[] = [];
    const m = this.selected;
    if (m) {
      if (this.launched) out.push({ pos: this.probePos, text: 'Probe', cls: 'probe', priority: 1 });
      for (const b of this.burnPoints) out.push({ pos: b.pos, text: `ΔV ${b.dv.toFixed(2)} km/s`, cls: 'burn', priority: 3 });
      if (this.encounterPoint) out.push({ pos: this.encounterPoint.pos, text: this.encounterPoint.text, cls: 'burn', priority: 3 });
    }
    if (this.showAll) {
      for (const mm of missions) {
        if (mm.id === m?.id) continue;
        const path = this.paths.get(mm.id)!;
        out.push({ pos: path.p[path.p.length - 1], text: mm.name, cls: 'ghost', priority: 4 });
      }
    }
    return out;
  }
}
