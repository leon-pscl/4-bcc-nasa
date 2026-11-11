import { useState } from 'react'
import { MapContainer, TileLayer, Rectangle } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

export function AreaSelector() {
  const [n, setN] = useState(15)
  const [s, setS] = useState(14)
  const [e, setE] = useState(121.5)
  const [w, setW] = useState(121.0)
  return (
    <div>
      <div style={{ display: 'flex', gap: 8 }}>
        <label>N<input value={n} onChange={ev => setN(Number(ev.target.value))} /></label>
        <label>S<input value={s} onChange={ev => setS(Number(ev.target.value))} /></label>
        <label>E<input value={e} onChange={ev => setE(Number(ev.target.value))} /></label>
        <label>W<input value={w} onChange={ev => setW(Number(ev.target.value))} /></label>
      </div>
      <MapContainer center={[14.5, 121.25]} zoom={9} style={{ height: 300 }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Rectangle bounds={[[s, w], [n, e]]} />
      </MapContainer>
    </div>
  )
}
