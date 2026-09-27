/** HTML labels that track 3D objects, with simple overlap avoidance. */
import * as THREE from 'three';
import type { LinkInfo, SolarScene } from './scene';

interface Label { el: HTMLDivElement; obj: THREE.Object3D; priority: number }

export class Labels {
  private readonly labels: Label[];
  private readonly links: { info: LinkInfo; el: HTMLDivElement }[];
  private readonly v = new THREE.Vector3();

  constructor(private readonly layer: HTMLElement, private readonly world: SolarScene) {
    this.labels = [
      { el: this.make('3I/ATLAS', 'comet'), obj: world.comet, priority: 0 },
      { el: this.make('Sun', 'sun'), obj: world.sun, priority: 1 },
      ...world.planets.map(p => ({ el: this.make(p.name), obj: p.dot, priority: 2 })),
    ];
    this.links = [world.earthLink, world.approachLink].map(info => ({ info, el: this.make('', 'link') }));
  }

  private make(text: string, cls = ''): HTMLDivElement {
    const el = document.createElement('div');
    el.className = `label ${cls}`;
    el.textContent = text;
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
    // Higher-priority labels win; lower ones that would overlap are hidden.
    const placed: number[][] = [];
    for (const L of this.labels) {
      const p = this.project(L.obj.position);
      if (!p) { L.el.hidden = true; continue; }
      const w = L.el.offsetWidth || 50, x = p[0] + 9, y = p[1] - 8;
      const box = [x, y, x + w, y + 15];
      const overlaps = placed.some(q => !(box[2] < q[0] || box[0] > q[2] || box[3] < q[1] || box[1] > q[3]));
      if (overlaps && L.priority > 0) { L.el.hidden = true; continue; }
      L.el.hidden = false;
      placed.push(box);
      L.el.style.transform = `translate(${x}px, ${y}px)`;
    }

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
