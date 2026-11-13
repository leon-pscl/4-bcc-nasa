import { useCoverage } from '../../api/hooks';

export default function AppHeader() {
  const { data } = useCoverage();
  const through = data?.regions?.[0]?.latest_date ?? '2026-11-12';
  function copy() {
    navigator.clipboard?.writeText(window.location.href);
    const live = document.getElementById('live-region');
    if (live) live.textContent = 'Link copied';
  }
  return (
    <header style={{ background: 'var(--surface)', borderBottom: '1px solid var(--line)', padding: '12px 32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span aria-hidden style={{ display: 'flex', gap: 2 }}>
          {['#ffffb2','#fed976','#feb24c','#fd8d3c','#fc4e2a','#e31a1c','#b10026'].map((c, i) => (
            <span key={i} style={{ width: 5, height: 8 + i * 4, background: c }} />
          ))}
        </span>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 600 }}>Burning Calendar</div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Harmonized MODIS + VIIRS fire hotspots, 2003 to today</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 13 }}>Data through {through}</span>
        <button onClick={copy} style={{ background: 'var(--surface)', border: '1px solid var(--ink)', borderRadius: 4, padding: '8px 12px', cursor: 'pointer' }}>Copy link to this view</button>
      </div>
    </header>
  );
}