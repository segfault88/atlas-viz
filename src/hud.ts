/** Info panel (distances, speed, status), event card, and legend. */
import {
  AU_KM, arcEnd, arcStart, byId, events, formatDate, meta, positionAt, velocityAt,
  type EventKind,
} from './ephemeris';

export const EVENT_COLORS: Record<EventKind, string> = {
  perihelion: '#ffd166',
  approach: '#6ea8ff',
  conjunction: '#ff7b72',
  node: '#c49bff',
  milestone: '#7cf7c8',
};
const EVENT_LABELS: Record<EventKind, string> = {
  milestone: 'Milestone',
  perihelion: 'Perihelion',
  approach: 'Close approach',
  conjunction: 'Solar conjunction',
  node: 'Ecliptic crossing',
};
const LIGHT_KM_S = 299792.458;

const $ = (id: string) => document.getElementById(id)!;

export class Hud {
  private readonly el = {
    date: $('date'), rSun: $('r-sun'), rEarth: $('r-earth'), speed: $('speed-v'), light: $('light'),
    status: $('status'), card: $('event-card'),
    probeRows: document.querySelectorAll<HTMLElement>('.probe-row'), probeDist: $('probe-dist'), probeSpeed: $('probe-speed'),
  };

  constructor() {
    const kinds = [...new Set(events.map(e => e.kind))];
    $('legend').innerHTML = kinds
      .map(k => `<span><i style="background:${EVENT_COLORS[k]}"></i>${EVENT_LABELS[k]}</span>`)
      .join('') + '<span><i class="bar" style="background:rgba(124,247,200,.35)"></i>Observed arc</span>';
    $('soln').textContent = `orbit solution ${meta.solution ?? ''} (${meta.observations ?? '?'} obs, `
      + `${meta.arc.join(' → ')}) · fetched ${meta.fetched}`;
  }

  /**
   * @param near  timeline marker to feature in the event card, if any
   * @param probe selected mission's probe state, or null when no mission is selected
   */
  update(t: number, near: { jd: number; title: string; detail: string } | null,
    probe: { launched: boolean; toComet: number; speed: number } | null) {
    const c = positionAt(byId.atlas, t), e = positionAt(byId.earth, t);
    const rSun = Math.hypot(...c);
    const rEarth = Math.hypot(c[0] - e[0], c[1] - e[1], c[2] - e[2]);
    const speed = Math.hypot(...velocityAt(byId.atlas, t)) * AU_KM / 86400;
    const lightMin = rEarth * AU_KM / LIGHT_KM_S / 60;

    this.el.date.textContent = formatDate(t);
    this.el.rSun.textContent = `${rSun.toFixed(3)} AU`;
    this.el.rEarth.textContent = `${rEarth.toFixed(3)} AU`;
    this.el.speed.textContent = `${speed.toFixed(1)} km/s`;
    this.el.light.textContent = lightMin < 60 ? `${lightMin.toFixed(1)} min` : `${(lightMin / 60).toFixed(2)} h`;

    const [cls, text] = t < arcStart ? ['predicted', 'Before first observation (back-computed)']
      : t <= arcEnd ? ['observed', 'Within observed arc']
      : ['predicted', 'Predicted (after last observation in fit)'];
    this.el.status.className = `status ${cls}`;
    this.el.status.textContent = text;

    for (const row of this.el.probeRows) row.hidden = !probe;
    if (probe) {
      this.el.probeDist.textContent = probe.launched ? `${probe.toComet.toFixed(3)} AU` : 'not launched';
      this.el.probeSpeed.textContent = probe.launched && probe.speed > 0 ? `${probe.speed.toFixed(1)} km/s` : '—';
    }

    const card = this.el.card;
    if (near) {
      card.querySelector('.t')!.textContent = `${near.title} — ${formatDate(near.jd, false)}`;
      card.querySelector('.d')!.textContent = near.detail;
      card.style.opacity = '1';
    } else {
      card.style.opacity = '0';
    }
  }
}
