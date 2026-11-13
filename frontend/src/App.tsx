import AppHeader from './components/AppHeader/AppHeader';
import SyntheticBanner from './components/SyntheticBanner/SyntheticBanner';
import MapCard from './components/MapCard/MapCard';
import './index.css';

export default function App() {
  return (
    <main style={{ maxWidth: 1440, margin: '0 auto', padding: '24px 32px', background: 'var(--paper)' }}>
      <AppHeader />
      <SyntheticBanner />
      <div id="live-region" aria-live="polite" className="visually-hidden" />
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 24 }}>
        <div style={{ flex: '999 1 640px' }}><MapCard /></div>
        <div style={{ flex: '1 1 360px', maxWidth: 420, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--surface)', padding: 20 }}>Side panel</div>
      </div>
      <section style={{ marginTop: 24, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--surface)', padding: 22 }}>Burning calendar</section>
    </main>
  );
}