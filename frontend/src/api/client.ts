import { CalendarSchema } from './schemas'

export async function fetchCalendar() {
  const res = await fetch('/api/calendar?bbox=-64,-18,-60,-14&start=2003-01-01&end=2024-01-31')
  const data = await res.json()
  return CalendarSchema.parse(data)
}
