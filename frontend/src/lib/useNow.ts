import { useEffect, useState } from 'react'

/** Current time, re-rendered every `everyMs` so relative times and staleness stay fresh. */
export function useNow(everyMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), everyMs)
    return () => window.clearInterval(id)
  }, [everyMs])
  return now
}
