import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AreaSelector } from './components/AreaSelector/AreaSelector'
import { DateRange } from './components/DateRange/DateRange'
import { BurningCalendar } from './components/BurningCalendar/BurningCalendar'

const qc = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={qc}>
      <div>
        <h1>Fire Calendar</h1>
        <AreaSelector />
        <DateRange />
        <BurningCalendar />
      </div>
    </QueryClientProvider>
  )
}

export default App
