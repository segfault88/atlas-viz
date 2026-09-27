/** Bottom timeline: draggable slider, date ticks, event markers, and play/pause. */
import { MONTHS, arcEnd, arcStart, dateToJd, events, formatDate, jd0, jdEnd, jdToDate, type AtlasEvent } from './ephemeris';
import { EVENT_COLORS } from './hud';

const SNAP_PX = 5;        // snap to event markers within this many pixels while dragging
const MARKER_GAP_PX = 12; // markers closer than this are stacked into a second row

const $ = (id: string) => document.getElementById(id)!;
const frac = (jd: number) => (jd - jd0) / (jdEnd - jd0);
const pct = (jd: number) => `${(frac(jd) * 100).toFixed(4)}%`;

export class Timeline {
  /** Current time (Julian Date). */
  time: number;
  playing = false;
  dragging = false;

  private readonly wrap = $('track-wrap');
  private readonly thumb = $('thumb');
  private readonly progress = $('progress');
  private readonly tooltip = $('tooltip');
  private readonly playBtn = $('play');
  private readonly speedSel = $('speed') as HTMLSelectElement;

  constructor(startJd: number, private readonly nowJd: number) {
    this.time = this.clamp(startJd);
    this.buildTrack();
    this.bindInput();
  }

  /** Days of simulated time per real second. */
  get speed() { return Number(this.speedSel.value); }

  setTime(jd: number) {
    this.time = this.clamp(jd);
    if (this.time >= jdEnd) this.setPlaying(false);
  }

  togglePlay() {
    if (!this.playing && this.time >= jdEnd - 1e-6) this.time = jd0;
    this.setPlaying(!this.playing);
  }

  /** Advance by dt real seconds if playing. */
  tick(dt: number) {
    if (this.playing && !this.dragging) this.setTime(this.time + dt * this.speed);
    this.thumb.style.left = pct(this.time);
    this.progress.style.width = pct(this.time);
  }

  private clamp(jd: number) { return Math.min(Math.max(jd, jd0), jdEnd); }

  private setPlaying(p: boolean) {
    this.playing = p;
    this.playBtn.textContent = p ? '❚❚' : '▶';
  }

  private buildTrack() {
    const { wrap } = this;
    const observed = $('observed');
    observed.style.left = pct(arcStart);
    observed.style.width = `${(frac(arcEnd) - frac(arcStart)) * 100}%`;
    observed.title = 'Observed arc';

    // Quarterly ticks, labelled with the year in January
    for (let y = jdToDate(jd0).getUTCFullYear(); dateToJd(new Date(Date.UTC(y, 0, 1))) <= jdEnd; y++) {
      for (let m = 0; m < 12; m += 3) {
        const jd = dateToJd(new Date(Date.UTC(y, m, 1)));
        if (jd < jd0 || jd > jdEnd) continue;
        const tick = document.createElement('div');
        tick.className = m === 0 ? 'tick year' : 'tick';
        tick.textContent = m === 0 ? String(y) : MONTHS[m];
        tick.style.left = pct(jd);
        wrap.appendChild(tick);
      }
    }

    if (this.nowJd > jd0 && this.nowJd < jdEnd) {
      const now = document.createElement('div');
      now.className = 'now-marker';
      now.style.left = pct(this.nowJd);
      now.innerHTML = '<span>NOW</span>';
      now.title = 'Today';
      now.addEventListener('pointerdown', ev => { ev.stopPropagation(); this.setTime(this.nowJd); });
      wrap.appendChild(now);
    }

    for (const e of events) {
      const m = document.createElement('div');
      m.className = 'marker';
      m.dataset.jd = String(e.jd);
      m.style.left = pct(e.jd);
      m.style.background = EVENT_COLORS[e.kind];
      m.addEventListener('pointerenter', ev => this.showTip(e, ev));
      m.addEventListener('pointermove', ev => this.showTip(e, ev));
      m.addEventListener('pointerleave', () => { this.tooltip.hidden = true; });
      m.addEventListener('pointerdown', ev => { ev.stopPropagation(); this.setTime(e.jd); });
      wrap.appendChild(m);
    }
    new ResizeObserver(() => this.layoutMarkers()).observe(wrap);
  }

  /** Stack markers that would overlap into a second row. */
  private layoutMarkers() {
    const w = this.wrap.clientWidth, lastX = [-1e9, -1e9];
    for (const m of this.wrap.querySelectorAll<HTMLElement>('.marker')) {
      const x = frac(Number(m.dataset.jd)) * w;
      const row = x - lastX[0] >= MARKER_GAP_PX ? 0 : 1;
      m.classList.toggle('row1', row === 1);
      lastX[row] = x;
    }
  }

  private showTip(e: AtlasEvent, ev: PointerEvent) {
    const tip = this.tooltip;
    tip.replaceChildren(
      Object.assign(document.createElement('div'), { className: 't', textContent: e.title }),
      Object.assign(document.createElement('div'), { className: 'when', textContent: formatDate(e.jd) }),
      Object.assign(document.createElement('div'), { textContent: e.detail }),
    );
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = `${Math.min(Math.max(8, ev.clientX - r.width / 2), innerWidth - r.width - 8)}px`;
    tip.style.top = `${ev.clientY - r.height - 16}px`;
  }

  private jdFromPointer(ev: PointerEvent): number {
    const r = this.wrap.getBoundingClientRect();
    const jd = jd0 + Math.min(Math.max((ev.clientX - r.left) / r.width, 0), 1) * (jdEnd - jd0);
    const pxPerDay = r.width / (jdEnd - jd0);
    return events.find(e => Math.abs(e.jd - jd) * pxPerDay < SNAP_PX)?.jd ?? jd;
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
