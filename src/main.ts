/** Entry point: wires the 3D scene, missions, labels, HUD and timeline together and runs the frame loop. */
import './style.css';
import { dataEnd, dateToJd, jd0, jdEnd, loadFar } from './ephemeris';
import { Hud } from './hud';
import { Labels } from './labels';
import { MissionLayer } from './missionLayer';
import { MissionPanel } from './missionPanel';
import { launchJd, needsFarData, type Mission } from './missions';
import { SolarScene } from './scene';
import { Timeline } from './timeline';

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

const EVENT_CARD_FRACTION = 0.004; // show the event card within this fraction of the timeline span of an event
const DEFAULT_SPEED = 7;

const nowJd = dateToJd(new Date());
const world = new SolarScene($('scene'));
const missionLayer = new MissionLayer(world.scene);
const labels = new Labels($('labels'), world, () => missionLayer.labels());
const hud = new Hud();
const timeline = new Timeline(nowJd, nowJd);

// ---------- missions ----------
let farPathBuilt = false;
let selectToken = 0;

async function selectMission(m: Mission | null) {
  const token = ++selectToken;
  if (m && needsFarData(m)) {
    document.body.classList.add('loading');
    await loadFar();
    document.body.classList.remove('loading');
    if (token !== selectToken) return; // another selection happened while loading
    if (!farPathBuilt) { world.buildCometPath(); farPathBuilt = true; }
  }
  missionLayer.select(m);
  world.setFocus(world.cometPos);
  if (!m) {
    timeline.setRange(jd0, jdEnd, null);
    timeline.speed = DEFAULT_SPEED;
    return;
  }
  // Short missions keep the default 2024–2028 window; long ones get their own
  const launch = launchJd(m), arrive = m.encounter.jd;
  const start = launch < jdEnd ? jd0 : launch - 180;
  const end = arrive < jdEnd ? jdEnd : Math.min(arrive + 365, dataEnd());
  timeline.setRange(start, end, m);
  timeline.setTime(launch);
  const spanYears = (end - start) / 365.25;
  timeline.speed = spanYears > 20 ? 365 : spanYears > 6 ? 91 : DEFAULT_SPEED;
  // Reframe around the comet so both it and the inner solar system are in view
  world.update(timeline.time);
  world.frameInitial(timeline.time);
}

new MissionPanel({
  select: m => { void selectMission(m); },
  follow: target => {
    if (target === 'comet') return world.setFocus(world.cometPos);
    // Zoom in proportionally to the probe's distance from the Sun, keeping the Sun in frame
    // (so a Sun-grazing burn is shown close up)
    const r = missionLayer.probePos.length();
    world.setFocus(missionLayer.probePos, Math.min(r * 3 + 0.01, 30));
  },
  showAll: on => { missionLayer.showAll = on; },
});

// ---------- controls ----------
$('recenter').addEventListener('click', () => world.recenter());
world.renderer.domElement.addEventListener('dblclick', () => world.recenter());
$<HTMLInputElement>('opt-earth').addEventListener('change', e => {
  world.showEarthLink = (e.target as HTMLInputElement).checked;
});
$<HTMLInputElement>('opt-orbits').addEventListener('change', e => {
  world.orbits.visible = (e.target as HTMLInputElement).checked;
});
$<HTMLInputElement>('opt-grid').addEventListener('change', e => {
  world.grid.visible = (e.target as HTMLInputElement).checked;
});

addEventListener('keydown', e => {
  const tag = (e.target as HTMLElement).tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || (tag === 'BUTTON' && e.code === 'Space')) return;
  if (e.code === 'Space') { e.preventDefault(); timeline.togglePlay(); }
  else if (e.code === 'ArrowRight') timeline.setTime(timeline.time + (e.shiftKey ? 7 : 1));
  else if (e.code === 'ArrowLeft') timeline.setTime(timeline.time - (e.shiftKey ? 7 : 1));
  else if (e.key === 'c' || e.key === 'C') world.recenter();
});

const resize = () => world.resize(innerWidth, innerHeight);
addEventListener('resize', resize);
resize();

// ---------- frame loop ----------
world.frameInitial(timeline.time);
let last = performance.now();
function frame(now: number) {
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;
  timeline.tick(dt);
  const t = timeline.time;
  world.update(t);
  missionLayer.update(t, world.cometPos, world.camera.position.distanceTo(world.controls.target));
  world.follow();
  world.render();
  const m = missionLayer.selected;
  hud.update(t, timeline.nearby(t, (timeline.end - timeline.start) * EVENT_CARD_FRACTION),
    m ? { launched: missionLayer.launched, toComet: missionLayer.probeToComet, speed: missionLayer.probeSpeed } : null);
  labels.update();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Handy for debugging from the console: atlasViz.timeline.setTime(2460977.98)
Object.assign(window, { atlasViz: { world, timeline, missionLayer, selectMission } });
