import AppHeader from './components/AppHeader/AppHeader';
import SyntheticBanner from './components/SyntheticBanner/SyntheticBanner';
import MapCard from './components/MapCard/MapCard';
import SidePanel from './components/SidePanel/SidePanel';
import BurningCalendar from './components/BurningCalendar/BurningCalendar';
import HotspotTable from './components/HotspotTable/HotspotTable';
import Downloads from './components/Downloads/Downloads';
import CoverControl from './components/CoverControl/CoverControl';
import { useAppState } from './state/useAppState';
import { useIsFetching } from '@tanstack/react-query';
import './index.css';

export default function App() {
  const { state } = useAppState();
  const isFetching = useIsFetching();
  if (!state) return null;
  return (
    <main style={{ maxWidth: 1440, margin: '0 auto', padding: '24px 32px', background: 'var(--paper)' }}>
      {isFetching > 0 ? <div role="status" aria-live="polite" style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 3, background: 'var(--ink)', zIndex: 9999 }} /> : null}
      <div className="visually-hidden" aria-live="polite">{isFetching > 0 ? 'Loading results for this area…' : ''}</div>
      <AppHeader />
      <SyntheticBanner />
      <div id="live-region" aria-live="polite" className="visually-hidden" />
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 24, alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 0', minWidth: 0 }}><MapCard /></div>
        <div style={{ flex: '0 0 360px', maxWidth: 420 }}><SidePanel /></div>
      </div>
      <CoverControl />
      <BurningCalendar />
      <HotspotTable />
      <Downloads />
    </main>
  );
}