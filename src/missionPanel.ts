/** Side panel listing intercept missions ranked by total ΔV, with expandable details. */
import { formatDate } from './ephemeris';
import { missions, type Mission } from './missions';

const $ = (id: string) => document.getElementById(id)!;
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', text = '') =>
  Object.assign(document.createElement(tag), { className: cls, textContent: text });

const years = (days: number) => {
  const y = days / 365.25;
  return y < 1 ? `${Math.round(days)} days` : `${y.toFixed(y < 10 ? 1 : 0)} years`;
};

const GROUPS: { kind: Mission['kind']; title: string; note: string }[] = [
  { kind: 'paper', title: 'Published studies', note: 'Reconstructed from peer-reviewed / preprint papers' },
  { kind: 'computed', title: 'What-ifs', note: 'Solved here with the same trajectory model' },
  { kind: 'rough', title: 'Rough ideas', note: 'Back-of-envelope and loosely modelled; for fun' },
];
const TAGS: Record<Mission['kind'], string> = { paper: 'study', computed: 'what-if', rough: 'rough' };
/** Bars are scaled to this ΔV; anything above it is drawn full-width with an overflow cap. */
const BAR_MAX_DV = 50;

export interface MissionPanelHandlers {
  select: (m: Mission | null) => void;
  follow: (target: 'comet' | 'probe') => void;
  showAll: (on: boolean) => void;
}

export class MissionPanel {
  private selectedId: string | null = null;
  private readonly list = $('mission-list');
  private readonly rows = new Map<string, HTMLLIElement>();

  constructor(private readonly on: MissionPanelHandlers) {
    const dvKey = (m: Mission) => (m.propulsion ? Infinity : m.totalDv);
    for (const g of GROUPS) {
      const group = missions.filter(m => m.kind === g.kind).sort((a, b) => dvKey(a) - dvKey(b));
      if (!group.length) continue;
      const head = el('li', `mgroup ${g.kind}`);
      head.append(el('span', 'mgroup-title', g.title), el('span', 'mgroup-note', g.note));
      this.list.append(head);
      for (const m of group) this.addRow(m);
    }
    ($('opt-all-missions') as HTMLInputElement).addEventListener('change', e => {
      this.on.showAll((e.target as HTMLInputElement).checked);
    });
    // Start collapsed on small screens so the 3D view stays visible
    if (matchMedia('(max-width: 760px)').matches) ($('missions') as HTMLDetailsElement).open = false;
  }

  private addRow(m: Mission) {
    const li = el('li', `mitem ${m.kind}`);
    const row = el('button', 'mrow');
    row.type = 'button';
    row.setAttribute('aria-expanded', 'false');
    const name = el('span', 'mname', m.name);
    name.append(el('span', `mtag ${m.kind}`, TAGS[m.kind]));
    const bar = el('span', 'mbar');
    if (!m.propulsion) {
      const fill = el('span', m.totalDv > BAR_MAX_DV ? 'mfill over' : 'mfill');
      fill.style.width = `${Math.min(m.totalDv / BAR_MAX_DV, 1) * 100}%`;
      bar.append(fill);
    }
    row.append(name, bar, el('span', 'mval', m.propulsion ? m.propulsion : m.totalDv.toFixed(1)));
    row.title = m.propulsion ? 'No rocket ΔV: pushed by a ground-based laser' : `Total ΔV ${m.totalDv.toFixed(2)} km/s`;
    row.addEventListener('click', () => this.select(this.selectedId === m.id ? null : m));
    li.append(row);
    this.list.append(li);
    this.rows.set(m.id, li);
  }

  select(m: Mission | null) {
    if (this.selectedId) {
      const li = this.rows.get(this.selectedId)!;
      li.classList.remove('selected');
      li.querySelector('.mrow')!.setAttribute('aria-expanded', 'false');
      li.querySelector('.mdetail')?.remove();
    }
    this.selectedId = m?.id ?? null;
    if (m) {
      const li = this.rows.get(m.id)!;
      li.classList.add('selected');
      li.querySelector('.mrow')!.setAttribute('aria-expanded', 'true');
      li.append(this.details(m));
    }
    this.on.select(m);
  }

  private details(m: Mission): HTMLElement {
    const d = el('div', 'mdetail');
    d.append(el('p', 'msummary', m.summary));

    const burns = el('table', 'mburns');
    for (const b of m.burns) {
      const tr = el('tr');
      tr.append(el('td', 'mdate', formatDate(b.jd, false)), el('td', '', b.label),
        el('td', 'mnum', b.dv >= 0.05 ? `${b.dv.toFixed(2)} km/s` : m.propulsion ?? 'free'));
      burns.append(tr);
    }
    const e = m.encounter;
    const tr = el('tr', 'menc');
    tr.append(el('td', 'mdate', formatDate(e.jd, false)),
      el('td', '', e.relSpeed > 0.05
        ? `Flyby ${e.rSun.toFixed(e.rSun < 10 ? 2 : 0)} AU from the Sun`
        : `Arrive alongside, ${e.rSun.toFixed(0)} AU from the Sun`),
      el('td', 'mnum', e.relSpeed > 0.05 ? `${e.relSpeed.toFixed(1)} km/s` : 'matched'));
    burns.append(tr);
    d.append(burns);

    const facts: string[] = [`Flight time ${years(e.jd - m.burns[0].jd)}`];
    if (m.stats.vinf !== undefined) facts.push(`departure v∞ ${m.stats.vinf.toFixed(1)} km/s`);
    if (m.stats.c3 !== undefined) facts.push(`C3 ${m.stats.c3.toFixed(0)} km²/s²`);
    if (m.stats.park) facts.push(`starts from ${m.stats.park}`);
    if (e.relSpeed > 0.05) {
      // How long a 1,000 km-wide view would last at this relative speed
      facts.push(`crosses a 1,000 km window in ${(1000 / e.relSpeed).toFixed(0)} s`);
    }
    d.append(el('p', 'mfacts', facts.join(' · ')));

    const src = el('p', 'msource');
    if (m.source) {
      src.append('Source: ');
      const a = el('a', '', m.source.label);
      a.href = m.source.url;
      a.target = '_blank';
      a.rel = 'noopener';
      src.append(a);
      if (m.paper) src.append(el('span', 'mpaper', ` Published figures: ${m.paper}. The path shown is this tool's patched-conic reconstruction.`));
      if (m.kind === 'rough') src.append(el('span', 'mpaper', ' Trajectory and ΔV are this tool\'s rough estimate.'));
    } else if (m.kind === 'rough') {
      src.append('Rough estimate by this tool: a simplified trajectory model, not a mission design.');
    } else {
      src.append('Computed by this tool: best two-body (Lambert) trajectory between JPL Horizons positions.');
    }
    d.append(src);

    const follow = el('div', 'mfollow');
    follow.append(el('span', '', 'Camera follows:'));
    for (const target of ['comet', 'probe'] as const) {
      const b = el('button', target === 'comet' ? 'active' : '', target === 'comet' ? '3I/ATLAS' : 'Probe');
      b.type = 'button';
      b.addEventListener('click', () => {
        follow.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
        this.on.follow(target);
      });
      follow.append(b);
    }
    d.append(follow);
    return d;
  }
}
