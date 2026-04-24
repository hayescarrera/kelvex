/**
 * useEventStream — React hook for Server-Sent Events from ColdGrid.
 *
 * Connects to /api/v1/events/stream, auto-reconnects on disconnect,
 * and dispatches typed event callbacks.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { api } from '../lib/api'

export interface ColdGridEvent {
  type: string
  data: Record<string, unknown>
  timestamp: string
}

type EventHandler = (event: ColdGridEvent) => void

export function useEventStream(handlers?: Record<string, EventHandler>) {
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const connect = useCallback(() => {
    const url = api.getEventStreamUrl()
    if (!url || url.includes('null')) return

    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setConnected(true)

    es.onmessage = (ev) => {
      try {
        const event: ColdGridEvent = JSON.parse(ev.data)
        // Call type-specific handler
        const h = handlersRef.current?.[event.type]
        if (h) h(event)
        // Call wildcard handler
        const wildcard = handlersRef.current?.['*']
        if (wildcard) wildcard(event)
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
      // Auto-reconnect after 5s
      setTimeout(() => connect(), 5000)
    }

    return es
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [connect])

  return { connected }
}
