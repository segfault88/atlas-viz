/** Bottom timeline: draggable slider, date ticks, event markers, and play/pause. */
import { MONTHS, arcEnd, arcStart, dateToJd, events, formatDate, jd0, jdEnd, jdToDate } from './ephemeris';
import { EVENT_COLORS } from './hud';
import type { Mission } from './missions';

const SNAP_PX = 5;        // snap to markers within this many pixels while dragging
const MARKER_GAP_PX = 12; // markers closer than this are stacked into a second row
const PROBE_CSS = '#ff5fc8';

const $ = (id: string) => document.getElementById(id)!;

interface Marker { jd: number; title: string; detail: string; color: string; cls: string }

export class Timeline {
  /** Current time (Julian Date). */
  time: number;
  playing = false;
  dragging = false;
  start = jd0;
  end = jdEnd;

  private markers: Marker[] = [];
  private mission: Mission | null = null;
  private readonly wrap = $('track-wrap');
  private readonly thumb = $('thumb');
  private readonly progress = $('progress');
  private readonly observed = $('observed');
  private readonly tooltip = $('tooltip');
  private readonly playBtn = $('play');
  private readonly speedSel = $('speed') as HTMLSelectElement;

  constructor(startJd: number, private readonly nowJd: number) {
    this.time = this.clamp(startJd);
    this.render();
    this.bindInput();
    new ResizeObserver(() => this.layoutMarkers()).observe(this.wrap);
  }

  /** Days of simulated time per real second. */
  get speed() { return Number(this.speedSel.value); }
  set speed(daysPerSec: number) { this.speedSel.value = String(daysPerSec); }

  setTime(jd: number) {
    this.time = this.clamp(jd);
    if (this.time >= this.end) this.setPlaying(false);
  }

  /** Change the visible date range and the mission whose markers are shown. */
  setRange(start: number, end: number, mission: Mission | null) {
    this.start = start;
    this.end = end;
    this.mission = mission;
    this.time = this.clamp(this.time);
    this.render();
  }

  togglePlay() {
    if (!this.playing && this.time >= this.end - 1e-6) this.time = this.start;
    this.setPlaying(!this.playing);
  }

  /** Advance by dt real seconds if playing. */
  tick(dt: number) {
    if (this.playing && !this.dragging) this.setTime(this.time + dt * this.speed);
    this.thumb.style.left = this.pct(this.time);
    this.progress.style.width = this.pct(this.time);
  }

  /** Timeline markers near t (for the event card). */
  nearby(t: number, withinDays: number): Marker | null {
    let best: Marker | null = null;
    for (const m of this.markers) {
      if (Math.abs(m.jd - t) < withinDays && (!best || Math.abs(m.jd - t) < Math.abs(best.jd - t))) best = m;
    }
    return best;
  }

  private frac(jd: number) { return (jd - this.start) / (this.end - this.start); }
  private pct(jd: number) { return `${(Math.min(Math.max(this.frac(jd), 0), 1) * 100).toFixed(4)}%`; }
  private clamp(jd: number) { return Math.min(Math.max(jd, this.start), this.end); }

  private setPlaying(p: boolean) {
    this.playing = p;
    this.playBtn.textContent = p ? '❚❚' : '▶';
  }

  private render() {
    const { wrap } = this;
    wrap.querySelectorAll('.tick, .marker, .now-marker').forEach(el => el.remove());

    const obStart = Math.max(arcStart, this.start), obEnd = Math.min(arcEnd, this.end);
    this.observed.hidden = obEnd <= obStart;
    this.observed.style.left = this.pct(obStart);
    this.observed.style.width = `${(this.frac(obEnd) - this.frac(obStart)) * 100}%`;
    this.observed.title = 'Observed arc';

    this.renderTicks();

    if (this.nowJd > this.start && this.nowJd < this.end) {
      const now = document.createElement('div');
      now.className = 'now-marker';
      now.style.left = this.pct(this.nowJd);
      now.innerHTML = '<span>NOW</span>';
      now.title = 'Today';
      now.addEventListener('pointerdown', ev => { ev.stopPropagation(); this.setTime(this.nowJd); });
      wrap.appendChild(now);
    }

    this.markers = events.map(e => ({ jd: e.jd, title: e.title, detail: e.detail, color: EVENT_COLORS[e.kind], cls: '' }));
    const m = this.mission;
    if (m) {
      for (const b of m.burns) {
        if (b.dv < 0.05) {
          this.markers.push({ jd: b.jd, title: 'Probe: gravity assist', detail: b.label, color: PROBE_CSS, cls: 'mission' });
        } else {
          this.markers.push({ jd: b.jd, title: `Probe burn: ΔV ${b.dv.toFixed(2)} km/s`, detail: b.label, color: PROBE_CSS, cls: 'mission' });
        }
      }
      const e = m.encounter;
      this.markers.push({
        jd: e.jd, color: PROBE_CSS, cls: 'mission encounter',
        title: e.relSpeed > 0.05 ? `Probe intercepts 3I/ATLAS at ${e.relSpeed.toFixed(1)} km/s` : 'Probe matches speed with 3I/ATLAS',
        detail: `${e.rSun.toFixed(1)} AU from the Sun, ${e.rEarth.toFixed(1)} AU from Earth`,
      });
    }
    this.markers.sort((a, b) => a.jd - b.jd);

    for (const mk of this.markers) {
      if (mk.jd < this.start || mk.jd > this.end) continue;
      const el = document.createElement('div');
      el.className = `marker ${mk.cls}`;
      el.dataset.jd = String(mk.jd);
      el.style.left = this.pct(mk.jd);
      el.style.background = mk.color;
      el.addEventListener('pointerenter', ev => this.showTip(mk, ev));
      el.addEventListener('pointermove', ev => this.showTip(mk, ev));
      el.addEventListener('pointerleave', () => { this.tooltip.hidden = true; });
      el.addEventListener('pointerdown', ev => { ev.stopPropagation(); this.setTime(mk.jd); });
      wrap.appendChild(el);
    }
    this.layoutMarkers();
  }

  /** Quarterly ticks for short ranges, yearly or multi-year ticks for long ones. */
  private renderTicks() {
    const years = (this.end - this.start) / 365.25;
    const monthStep = years <= 5 ? 3 : 12;
    const yearStep = years <= 15 ? 1 : years <= 40 ? 5 : 10;
    for (let y = jdToDate(this.start).getUTCFullYear(); dateToJd(new Date(Date.UTC(y, 0, 1))) <= this.end; y++) {
      if (monthStep === 12 && y % yearStep !== 0) continue;
      for (let mo = 0; mo < 12; mo += monthStep) {
        const jd = dateToJd(new Date(Date.UTC(y, mo, 1)));
        if (jd < this.start || jd > this.end) continue;
        const tick = document.createElement('div');
        tick.className = mo === 0 ? 'tick year' : 'tick';
        tick.textContent = mo === 0 ? String(y) : MONTHS[mo];
        tick.style.left = this.pct(jd);
        this.wrap.appendChild(tick);
      }
    }
  }

  /** Stack markers that would overlap into a second row. */
  private layoutMarkers() {
    const w = this.wrap.clientWidth, lastX = [-1e9, -1e9];
    for (const m of this.wrap.querySelectorAll<HTMLElement>('.marker')) {
      const x = this.frac(Number(m.dataset.jd)) * w;
      const row = x - lastX[0] >= MARKER_GAP_PX ? 0 : 1;
      m.classList.toggle('row1', row === 1);
      lastX[row] = x;
    }
  }

  private showTip(mk: Marker, ev: PointerEvent) {
    const tip = this.tooltip;
    tip.replaceChildren(
      Object.assign(document.createElement('div'), { className: 't', textContent: mk.title }),
      Object.assign(document.createElement('div'), { className: 'when', textContent: formatDate(mk.jd) }),
      Object.assign(document.createElement('div'), { textContent: mk.detail }),
    );
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = `${Math.min(Math.max(8, ev.clientX - r.width / 2), innerWidth - r.width - 8)}px`;
    tip.style.top = `${ev.clientY - r.height - 16}px`;
  }

  private jdFromPointer(ev: PointerEvent): number {
    const r = this.wrap.getBoundingClientRect();
    const span = this.end - this.start;
    const jd = this.start + Math.min(Math.max((ev.clientX - r.left) / r.width, 0), 1) * span;
    const pxPerDay = r.width / span;
    return this.markers.find(m => Math.abs(m.jd - jd) * pxPerDay < SNAP_PX)?.jd ?? jd;
  }

  private bindInput() {
    const { wrap } = this;
    wrap.addEventListener('pointerdown', ev => {
      this.dragging = true;
      wrap.setPointerCapture(ev.pointerId);
      this.setTime(this.jdFromPointer(ev));
    });
    wrap.addEventListener('pointermove', ev => { if (this.dragging) this.setTime(this.jdFromPointer(ev)); });
    wrap.addEventListener('pointerup', () => { this.dragging = false; });
    wrap.addEventListener('pointercancel', () => { this.dragging = false; });
    this.playBtn.addEventListener('click', () => this.togglePlay());
  }
}
