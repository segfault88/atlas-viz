/**
 * The Three.js world: Sun, planets, orbits, ecliptic grid, and 3I/ATLAS with its
 * trail. `SolarScene.update(t)` moves everything to time t (Julian Date).
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  arcEnd, bodies, byId, events, samples, scenePositionAt, toScene,
  type OrbitalElements,
} from './ephemeris';
import { sampleIndex } from './missions';

const COMET_COLOR = 0x7cf7c8;
const TRAIL_FADE_DAYS = 110;   // trail brightens over this span toward the comet
const APPROACH_LINK_DAYS = 25;
const SUN_RADIUS_AU = 695700 / 149597870.7;  // show the link to a planet within ± this many days of closest approach

// ---------- small builders ----------

/** Radial-gradient sprite texture: a hard-edged disc or a soft glow. */
function discTexture(soft: boolean): THREE.Texture {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  if (soft) {
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(0.25, 'rgba(255,255,255,.55)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
  } else {
    grad.addColorStop(0, '#fff');
    grad.addColorStop(0.72, '#fff');
    grad.addColorStop(0.86, 'rgba(255,255,255,.25)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
  }
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}
const DISC = discTexture(false);
const GLOW = discTexture(true);

/** A single point drawn at a constant pixel size, always on top. */
export function makeDot(color: THREE.ColorRepresentation, sizePx: number, tex = DISC): THREE.Points {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0], 3));
  const mat = new THREE.PointsMaterial({
    color, size: sizePx, map: tex, sizeAttenuation: false,
    transparent: true, depthWrite: false, depthTest: false,
  });
  const p = new THREE.Points(geo, mat);
  p.renderOrder = 10;
  p.frustumCulled = false;
  return p;
}

/** A two-point line whose endpoints are updated every frame. */
export function makeSegment(material: THREE.LineBasicMaterial | THREE.LineDashedMaterial): THREE.Line {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(new Array(6).fill(0), 3));
  const l = new THREE.Line(g, material);
  l.frustumCulled = false;
  return l;
}

export function setSegment(line: THREE.Line, a: THREE.Vector3, b: THREE.Vector3, dash?: number) {
  const attr = line.geometry.getAttribute('position') as THREE.BufferAttribute;
  attr.setXYZ(0, a.x, a.y, a.z);
  attr.setXYZ(1, b.x, b.y, b.z);
  attr.needsUpdate = true;
  if (dash !== undefined && line.material instanceof THREE.LineDashedMaterial) {
    line.material.dashSize = line.material.gapSize = dash;
    line.computeLineDistances();
  }
}

/** Closed orbit ellipse from osculating elements, in scene space. */
function orbitPoints(el: OrbitalElements, N = 512): THREE.Vector3[] {
  const d = Math.PI / 180, i = el.i * d, O = el.om * d, w = el.w * d;
  const p = el.a * (1 - el.e * el.e);
  const pts: THREE.Vector3[] = [];
  for (let k = 0; k <= N; k++) {
    const nu = (k / N) * Math.PI * 2, r = p / (1 + el.e * Math.cos(nu)), u = w + nu;
    pts.push(toScene([
      r * (Math.cos(O) * Math.cos(u) - Math.sin(O) * Math.sin(u) * Math.cos(i)),
      r * (Math.sin(O) * Math.cos(u) + Math.cos(O) * Math.sin(u) * Math.cos(i)),
      r * Math.sin(u) * Math.sin(i),
    ]));
  }
  return pts;
}

function makeStarfield(camera: THREE.Camera): THREE.Points {
  const N = 3000, R = 2000, pts: number[] = [], cols: number[] = [];
  for (let i = 0; i < N; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    pts.push(R * s * Math.cos(th), R * u, R * s * Math.sin(th));
    const b = 0.35 + Math.random() * 0.65;
    cols.push(b, b, b * (0.9 + Math.random() * 0.2));
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  const stars = new THREE.Points(g, new THREE.PointsMaterial({
    size: 1.4, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.7,
  }));
  // Keep stars "at infinity" by following the camera.
  stars.onBeforeRender = () => stars.position.copy(camera.position);
  return stars;
}

/** Reference rings on the ecliptic plane at notable radii, plus spokes every 30°. */
function makeEclipticGrid(): THREE.Group {
  const grid = new THREE.Group();
  const ringMat = new THREE.LineBasicMaterial({ color: 0x5870a8, transparent: true, opacity: 0.16 });
  for (const r of [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30]) {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= 256; i++) {
      const a = (i / 256) * Math.PI * 2;
      pts.push(new THREE.Vector3(r * Math.cos(a), 0, r * Math.sin(a)));
    }
    grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), ringMat));
  }
  const spokeMat = new THREE.LineBasicMaterial({ color: 0x5870a8, transparent: true, opacity: 0.08 });
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    const end = new THREE.Vector3(30 * Math.cos(a), 0, 30 * Math.sin(a));
    grid.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), end]), spokeMat));
  }
  return grid;
}

// ---------- the scene ----------

export interface LinkInfo { line: THREE.Line; text: string }

export class SolarScene {
  readonly renderer = new THREE.WebGLRenderer({ antialias: true });
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 1, 0.0005, 5000);
  readonly controls: OrbitControls;

  readonly grid = makeEclipticGrid();
  readonly orbits = new THREE.Group();
  readonly sun = makeDot(0xfff2c8, 12);
  readonly planets: { name: string; id: string; dot: THREE.Points }[];
  readonly comet = makeDot(0xd9fff0, 8);
  readonly cometPos = new THREE.Vector3();

  /** Links drawn from the comet to a planet, with a text label for the overlay. */
  readonly earthLink: LinkInfo;
  readonly approachLink: LinkInfo;
  showEarthLink = false;

  /** The point the camera follows (the comet by default; see setFocus). */
  private focus: THREE.Vector3 = this.cometPos;
  private readonly lastFocus = new THREE.Vector3();

  private readonly atlas = byId.atlas;
  private readonly cometGlow = makeDot(COMET_COLOR, 30, GLOW);
  private cometTimes = new Float64Array(0);
  private cometPoints: THREE.Vector3[] = [];
  private trailPos = new Float32Array(0);
  private trailCol = new Float32Array(0);
  private readonly trailGeo = new THREE.BufferGeometry();
  private readonly pathGroup = new THREE.Group();
  private predictedLine: THREE.Line | null = null;
  private readonly tail: THREE.Line;
  private readonly dropLine: THREE.Line;
  private readonly foot = makeDot(COMET_COLOR, 4);
  private readonly tmp = new THREE.Vector3();

  constructor(container: HTMLElement) {
    const { renderer, scene, camera } = this;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    scene.background = new THREE.Color(0x05070d);

    this.controls = new OrbitControls(camera, renderer.domElement);
    Object.assign(this.controls, {
      enableDamping: true, dampingFactor: 0.1, minDistance: 0.002, maxDistance: 3000,
      screenSpacePanning: true, zoomSpeed: 1.2,
    });

    scene.add(makeStarfield(camera), this.grid, this.orbits);

    // Sun and planets. The sphere is the Sun at true size, visible only when zoomed right in.
    const sunSphere = new THREE.Mesh(new THREE.SphereGeometry(SUN_RADIUS_AU, 48, 24), new THREE.MeshBasicMaterial({ color: 0xffd98a }));
    scene.add(sunSphere, makeDot(0xffc76b, 46, GLOW), this.sun);
    this.planets = bodies.filter(b => b.id !== 'atlas').map(b => {
      const dot = makeDot(b.color, b.id === 'jupiter' || b.id === 'saturn' ? 9 : 7);
      scene.add(dot);
      if (b.elements) {
        const mat = new THREE.LineBasicMaterial({ color: b.color, transparent: true, opacity: 0.32 });
        this.orbits.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(orbitPoints(b.elements)), mat));
      }
      return { name: b.name, id: b.id, dot };
    });

    scene.add(this.pathGroup);
    this.buildCometPath();

    // Travelled trail (rebuilt each frame up to the current time)
    const trail = new THREE.Line(this.trailGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.95 }));
    trail.frustumCulled = false;

    this.tail = makeSegment(new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.8 }));
    this.tail.geometry.setAttribute('color', new THREE.Float32BufferAttribute([0.55, 1, 0.85, 0.02, 0.06, 0.05], 3));
    this.dropLine = makeSegment(new THREE.LineDashedMaterial({ color: COMET_COLOR, transparent: true, opacity: 0.35 }));
    (this.foot.material as THREE.PointsMaterial).opacity = 0.5;
    this.cometGlow.renderOrder = this.comet.renderOrder = 12;
    scene.add(trail, this.tail, this.dropLine, this.foot, this.cometGlow, this.comet);

    const link = (color: number): LinkInfo => {
      const line = makeSegment(new THREE.LineDashedMaterial({ color, transparent: true, opacity: 0.7 }));
      line.visible = false;
      scene.add(line);
      return { line, text: '' };
    };
    this.earthLink = link(0x4f9dff);
    this.approachLink = link(0xc9d3ff);
  }

  /** (Re)build the comet's full path and trail buffers from all loaded ephemeris samples. */
  buildCometPath() {
    const all = samples(this.atlas);
    this.cometTimes = Float64Array.from(all.map(s => s.jd));
    this.cometPoints = all.map(s => s.p);

    // Solid (faint) within the observed arc, dashed orange after it (prediction)
    const observed = all.filter(s => s.jd <= arcEnd).map(s => s.p);
    const predicted = all.filter((s, i) => s.jd >= arcEnd || all[i + 1]?.jd > arcEnd).map(s => s.p);
    this.pathGroup.clear();
    const observedLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(observed),
      new THREE.LineBasicMaterial({ color: COMET_COLOR, transparent: true, opacity: 0.18 }));
    const predictedLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(predicted),
      new THREE.LineDashedMaterial({ color: 0xffbe6e, transparent: true, opacity: 0.3, dashSize: 0.08, gapSize: 0.08 }));
    predictedLine.computeLineDistances();
    this.predictedLine = predictedLine;
    this.pathGroup.add(observedLine, predictedLine);

    this.trailPos = new Float32Array((all.length + 1) * 3);
    this.trailCol = new Float32Array((all.length + 1) * 3);
    this.trailGeo.setAttribute('position', new THREE.BufferAttribute(this.trailPos, 3));
    this.trailGeo.setAttribute('color', new THREE.BufferAttribute(this.trailCol, 3));
  }

  resize(w: number, h: number) {
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  /** Initial framing: behind the comet looking back toward the Sun, slightly above the ecliptic. */
  frameInitial(t: number) {
    scenePositionAt(this.atlas, t, this.cometPos);
    this.lastFocus.copy(this.cometPos);
    this.controls.target.copy(this.cometPos);
    const d = Math.max(3, this.cometPos.length() * 0.9 + 2);
    const dir = this.tmp.copy(this.cometPos).setY(0).normalize();
    this.camera.position.copy(this.cometPos).addScaledVector(dir, d * 0.8).add(new THREE.Vector3(0, d * 0.35, 0));
    this.controls.update();
  }

  /** Move camera + target so the focus point is centred, keeping the current viewing angle. */
  recenter() {
    const delta = this.tmp.subVectors(this.focus, this.controls.target);
    this.controls.target.add(delta);
    this.camera.position.add(delta);
  }

  /**
   * Follow a different point (e.g. a probe). The vector is read every frame.
   * Optionally zoom to `distance` AU, keeping the current viewing direction.
   */
  setFocus(v: THREE.Vector3, distance?: number) {
    this.focus = v;
    this.lastFocus.copy(v);
    this.recenter();
    if (distance !== undefined) {
      const dir = this.tmp.subVectors(this.camera.position, this.controls.target).normalize();
      this.camera.position.copy(this.controls.target).addScaledVector(dir, distance);
    }
  }

  /**
   * Shift camera and target by the focus point's displacement since the last frame, so
   * the user's rotation / pan / zoom are preserved relative to it. Call after all updates.
   */
  follow() {
    const delta = this.tmp.subVectors(this.focus, this.lastFocus);
    this.camera.position.add(delta);
    this.controls.target.add(delta);
    this.lastFocus.copy(this.focus);
  }

  update(t: number) {
    const { cometPos, tmp } = this;
    scenePositionAt(this.atlas, t, cometPos);
    this.comet.position.copy(cometPos);
    this.cometGlow.position.copy(cometPos);
    for (const p of this.planets) scenePositionAt(byId[p.id], t, p.dot.position);

    this.updateTrail(t);

    const camDist = this.camera.position.distanceTo(this.controls.target);
    const predicted = this.predictedLine!.material as THREE.LineDashedMaterial;
    predicted.dashSize = predicted.gapSize = camDist * 0.012;

    // Anti-sunward tail: direction is real, length is stylised for visibility.
    const r = cometPos.length();
    const tailLen = camDist * 0.08 * Math.min(1.5, Math.max(0.15, 2 / (r * r)));
    setSegment(this.tail, cometPos, tmp.copy(cometPos).normalize().multiplyScalar(tailLen).add(cometPos));

    // Drop line to the ecliptic plane helps judge height in 3D.
    tmp.set(cometPos.x, 0, cometPos.z);
    setSegment(this.dropLine, cometPos, tmp, camDist * 0.006);
    this.foot.position.copy(tmp);

    this.updateLinks(t, camDist * 0.008);
  }

  render() {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  /** Trail = every sample up to t plus the interpolated current point, fading with age. */
  private updateTrail(t: number) {
    const { trailPos, trailCol, cometPoints, cometTimes, cometPos } = this;
    const k = Math.max(sampleIndex(cometTimes, t), 0);
    const count = k + 2;
    for (let j = 0; j <= k; j++) {
      const p = cometPoints[j];
      trailPos[3 * j] = p.x;
      trailPos[3 * j + 1] = p.y;
      trailPos[3 * j + 2] = p.z;
    }
    trailPos.set([cometPos.x, cometPos.y, cometPos.z], 3 * (k + 1));
    // Fade by elapsed time (not sample count) so the look is the same on the 12 h and 5 d grids
    for (let j = 0; j < count; j++) {
      const age = t - (j <= k ? cometTimes[j] : t);
      const f = Math.max(0.18, 1 - age / TRAIL_FADE_DAYS);
      trailCol[3 * j] = 0.49 * f;
      trailCol[3 * j + 1] = 0.97 * f;
      trailCol[3 * j + 2] = 0.78 * f;
    }
    this.trailGeo.setDrawRange(0, count);
    this.trailGeo.getAttribute('position').needsUpdate = true;
    this.trailGeo.getAttribute('color').needsUpdate = true;
  }

  private updateLinks(t: number, dash: number) {
    const { cometPos } = this;
    const planetPos = (name: string) => this.planets.find(p => p.name === name)!.dot.position;

    const earth = planetPos('Earth');
    this.earthLink.line.visible = this.showEarthLink;
    if (this.showEarthLink) {
      setSegment(this.earthLink.line, cometPos, earth, dash);
      this.earthLink.text = `${cometPos.distanceTo(earth).toFixed(3)} AU`;
    }

    const ev = events.find(e => e.kind === 'approach' && Math.abs(e.jd - t) < APPROACH_LINK_DAYS
      && !(this.showEarthLink && e.title.endsWith('Earth')));
    this.approachLink.line.visible = !!ev;
    if (ev) {
      const name = ev.title.replace('Closest to ', '');
      const pl = planetPos(name);
      setSegment(this.approachLink.line, cometPos, pl, dash);
      this.approachLink.text = `${name}: ${cometPos.distanceTo(pl).toFixed(3)} AU`;
    }
  }
}
