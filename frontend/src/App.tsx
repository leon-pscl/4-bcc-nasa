import MapCard from './components/MapCard/MapCard';
import './index.css';

export default function App() {
  return (
    <main style={{ padding: 16, fontFamily: 'ui-monospace, monospace' }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 12px' }}>Burning Calendar</h1>
      <MapCard />
    </main>
  );
}