import AppHeader from './components/AppHeader/AppHeader';
import SyntheticBanner from './components/SyntheticBanner/SyntheticBanner';
import MapCard from './components/MapCard/MapCard';
import SidePanel from './components/SidePanel/SidePanel';
import BurningCalendar from './components/BurningCalendar/BurningCalendar';
import { useAppState } from './state/useAppState';
import './index.css';

export default function App() {
  const { state } = useAppState();
  if (!state) return null;
  return (
    <main style={{ maxWidth: 1440, margin: '0 auto', padding: '24px 32px', background: 'var(--paper)' }}>
      <AppHeader />
      <SyntheticBanner />
      <div id="live-region" aria-live="polite" className="visually-hidden" />
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 24, alignItems: 'flex-start' }}>
        <div style={{ flex: '999 1 640px' }}><MapCard /></div>
        <div style={{ flex: '1 1 360px', maxWidth: 420 }}><SidePanel /></div>
      </div>
      <BurningCalendar />
    </main>
  );
}