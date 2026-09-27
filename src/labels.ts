/** HTML labels that track 3D objects, with simple overlap avoidance. */
import * as THREE from 'three';
import type { MissionLabel } from './missionLayer';
import type { LinkInfo, SolarScene } from './scene';

interface Item { pos: THREE.Vector3; text: string; cls: string; priority: number }

export class Labels {
  private readonly fixed: Item[];
  private readonly links: { info: LinkInfo; el: HTMLDivElement }[];
  private readonly pool: HTMLDivElement[] = [];
  private readonly v = new THREE.Vector3();

  constructor(
    private readonly layer: HTMLElement,
    private readonly world: SolarScene,
    private readonly extra: () => MissionLabel[] = () => [],
  ) {
    this.fixed = [
      { pos: world.comet.position, text: '3I/ATLAS', cls: 'comet', priority: 0 },
      { pos: world.sun.position, text: 'Sun', cls: 'sun', priority: 1 },
      ...world.planets.map(p => ({ pos: p.dot.position, text: p.name, cls: '', priority: 2 })),
    ];
    this.links = [world.earthLink, world.approachLink].map(info => ({ info, el: this.make('link') }));
  }

  private make(cls: string): HTMLDivElement {
    const el = document.createElement('div');
    el.className = `label ${cls}`;
    this.layer.appendChild(el);
    return el;
  }

  /** Screen position in CSS pixels, or null if behind the camera. */
  private project(p: THREE.Vector3): [number, number] | null {
    this.v.copy(p).project(this.world.camera);
    if (this.v.z > 1 || this.v.z < -1) return null;
    return [(this.v.x * 0.5 + 0.5) * innerWidth, (-this.v.y * 0.5 + 0.5) * innerHeight];
  }

  update() {
    const items = [...this.fixed, ...this.extra()].sort((a, b) => a.priority - b.priority);
    while (this.pool.length < items.length) this.pool.push(this.make(''));

    // Higher-priority labels win; lower ones that would overlap are hidden.
    const placed: number[][] = [];
    items.forEach((it, i) => {
      const el = this.pool[i];
      const cls = `label ${it.cls}`;
      if (el.className !== cls) el.className = cls;
      if (el.textContent !== it.text) el.textContent = it.text;
      const p = this.project(it.pos);
      if (!p) { el.hidden = true; return; }
      const w = el.offsetWidth || 50, x = p[0] + 9, y = p[1] - 8;
      const box = [x, y, x + w, y + 15];
      const overlaps = placed.some(q => !(box[2] < q[0] || box[0] > q[2] || box[3] < q[1] || box[1] > q[3]));
      if (overlaps && it.priority > 0) { el.hidden = true; return; }
      el.hidden = false;
      placed.push(box);
      el.style.transform = `translate(${x}px, ${y}px)`;
    });
    for (let i = items.length; i < this.pool.length; i++) this.pool[i].hidden = true;

    // Distance labels at the midpoint of each visible link line
    for (const { info, el } of this.links) {
      if (!info.line.visible) { el.hidden = true; continue; }
      const a = info.line.geometry.getAttribute('position');
      const mid = new THREE.Vector3().fromBufferAttribute(a, 0).add(this.v.fromBufferAttribute(a, 1)).multiplyScalar(0.5);
      const p = this.project(mid);
      if (!p) { el.hidden = true; continue; }
      el.hidden = false;
      el.textContent = info.text;
      el.style.transform = `translate(${p[0] + 6}px, ${p[1]}px)`;
    }
  }
}
