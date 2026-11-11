import { useState } from 'react'

export function DateRange() {
  const [start, setStart] = useState('2003-01-01')
  const [end, setEnd] = useState('2024-01-31')
  return (
    <div>
      <label>Start<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>End<input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>
    </div>
  )
}
