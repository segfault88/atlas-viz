/** Entry point: wires the 3D scene, labels, HUD and timeline together and runs the frame loop. */
import './style.css';
import { dateToJd } from './ephemeris';
import { Hud } from './hud';
import { Labels } from './labels';
import { SolarScene } from './scene';
import { Timeline } from './timeline';

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

const nowJd = dateToJd(new Date());
const world = new SolarScene($('scene'));
const labels = new Labels($('labels'), world);
const hud = new Hud();
const timeline = new Timeline(nowJd, nowJd);

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
  if (tag === 'INPUT' || tag === 'SELECT') return;
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
  world.update(timeline.time);
  world.render();
  hud.update(timeline.time);
  labels.update();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Handy for debugging from the console: atlasViz.timeline.setTime(2460977.98)
Object.assign(window, { atlasViz: { world, timeline } });
