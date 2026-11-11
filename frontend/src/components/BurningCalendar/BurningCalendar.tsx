import { useQuery } from '@tanstack/react-query'
import { fetchCalendar } from '../../api/client'

export function BurningCalendar() {
  const { data, isLoading, error } = useQuery({ queryKey: ['calendar'], queryFn: fetchCalendar })
  if (isLoading) return <p>loading</p>
  if (error || !data) return <p>error</p>
  return (
    <table>
      <thead>
        <tr><th>Year</th>{Array.from({length:12},(_,i)=><th key={i}>{i+1}</th>)}</tr>
      </thead>
      <tbody>
        {data.years.map((y,i) => (
          <tr key={y}><td>{y}</td>{data.values[i].map((v,j)=><td key={j}>{v ?? ''}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}
