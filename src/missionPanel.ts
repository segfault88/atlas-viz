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
    const sorted = [...missions].sort((a, b) => a.totalDv - b.totalDv);
    const maxDv = Math.max(...sorted.map(m => m.totalDv));
    for (const m of sorted) {
      const li = el('li');
      const row = el('button', 'mrow');
      row.type = 'button';
      row.setAttribute('aria-expanded', 'false');
      const name = el('span', 'mname', m.name);
      name.append(el('span', `mtag ${m.kind}`, m.kind === 'paper' ? 'study' : 'what-if'));
      const bar = el('span', 'mbar');
      const fill = el('span', 'mfill');
      fill.style.width = `${(m.totalDv / maxDv) * 100}%`;
      bar.append(fill);
      row.append(name, bar, el('span', 'mval', m.totalDv.toFixed(1)));
      row.addEventListener('click', () => this.select(this.selectedId === m.id ? null : m));
      li.append(row);
      this.list.append(li);
      this.rows.set(m.id, li);
    }
    ($('opt-all-missions') as HTMLInputElement).addEventListener('change', e => {
      this.on.showAll((e.target as HTMLInputElement).checked);
    });
    // Start collapsed on small screens so the 3D view stays visible
    if (matchMedia('(max-width: 760px)').matches) ($('missions') as HTMLDetailsElement).open = false;
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
        el('td', 'mnum', b.dv < 0.05 ? 'free' : `${b.dv.toFixed(2)} km/s`));
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
