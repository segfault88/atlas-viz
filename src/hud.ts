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
const EVENT_CARD_DAYS = 4; // show the event card within ± this many days of an event

const $ = (id: string) => document.getElementById(id)!;

export class Hud {
  private readonly el = {
    date: $('date'), rSun: $('r-sun'), rEarth: $('r-earth'), speed: $('speed-v'), light: $('light'),
    status: $('status'), card: $('event-card'),
  };

  constructor() {
    const kinds = [...new Set(events.map(e => e.kind))];
    $('legend').innerHTML = kinds
      .map(k => `<span><i style="background:${EVENT_COLORS[k]}"></i>${EVENT_LABELS[k]}</span>`)
      .join('') + '<span><i class="bar" style="background:rgba(124,247,200,.35)"></i>Observed arc</span>';
    $('soln').textContent = `orbit solution ${meta.solution ?? ''} (${meta.observations ?? '?'} obs, `
      + `${meta.arc.join(' → ')}) · fetched ${meta.fetched}`;
  }

  update(t: number) {
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

    let near = null;
    for (const ev of events) {
      if (Math.abs(ev.jd - t) < EVENT_CARD_DAYS && (!near || Math.abs(ev.jd - t) < Math.abs(near.jd - t))) near = ev;
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
