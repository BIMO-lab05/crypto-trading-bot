/**
 * useGatewayWebSocket - subscribe to the api-gateway /ws broadcast.
 *
 * The gateway pushes a `dashboard_update` envelope every ~2s containing
 * { health, portfolio, tickers }. A single module-scoped client owns the
 * connection (auto-reconnect with exponential backoff, 30s heartbeat) and
 * mirrors incoming ticker payloads into the React Query cache. Components
 * call this hook to get `isLive`/`lastMessage`; calling it from multiple
 * places does NOT open multiple sockets.
 *
 * When `VITE_ENABLE_WEBSOCKET` is `'false'` the client never connects and
 * components fall back to their existing polling.
 */

import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const WS_STATES = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  RECONNECTING: 'reconnecting',
  DISABLED: 'disabled',
}

const HEARTBEAT_INTERVAL_MS = 30000
const INITIAL_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30000
const MAX_RECONNECT_ATTEMPTS = 10

function resolveUrl() {
  if (typeof window === 'undefined') return null
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (import.meta.env.DEV) return 'ws://localhost:8000/ws'
  return `${protocol}//${window.location.host}/ws`
}

const enabled = import.meta.env.VITE_ENABLE_WEBSOCKET !== 'false'

// Module-scoped singleton state.
const subscribers = new Set()
let ws = null
let connectionState = enabled ? WS_STATES.DISCONNECTED : WS_STATES.DISABLED
let lastMessage = null
let reconnectAttempts = 0
let reconnectTimer = null
let heartbeatTimer = null
let queryClientRef = null

function notify() {
  subscribers.forEach((cb) => cb({ connectionState, lastMessage }))
}

function setState(next) {
  connectionState = next
  notify()
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping')
  }, HEARTBEAT_INTERVAL_MS)
}

function applyTickersToCache(qc, tickers) {
  Object.keys(tickers).forEach((sym) => {
    qc.setQueryData(['ticker', sym], tickers[sym])
  })
  qc.getQueryCache()
    .findAll({ queryKey: ['tickers'] })
    .forEach((query) => {
      const [, requestedSymbols] = query.queryKey
      if (!Array.isArray(requestedSymbols)) return
      qc.setQueryData(query.queryKey, (prev) => {
        const next = { ...(prev || {}) }
        requestedSymbols.forEach((sym) => {
          if (tickers[sym] !== undefined) next[sym] = tickers[sym]
        })
        return next
      })
    })
}

function handleMessage(msg) {
  if (!msg || msg.type !== 'dashboard_update' || !msg.data) return
  if (!queryClientRef) return

  if (msg.data.tickers && typeof msg.data.tickers === 'object') {
    applyTickersToCache(queryClientRef, msg.data.tickers)
  }
  if (msg.data.portfolio) {
    queryClientRef.setQueryData(['portfolio'], msg.data.portfolio)
  }
}

function scheduleReconnect() {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    setState(WS_STATES.DISCONNECTED)
    return
  }
  reconnectAttempts += 1
  const delay = Math.min(
    INITIAL_RECONNECT_DELAY_MS * 2 ** (reconnectAttempts - 1),
    MAX_RECONNECT_DELAY_MS
  )
  setState(WS_STATES.RECONNECTING)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

function connect() {
  if (!enabled) return
  if (ws && ws.readyState === WebSocket.OPEN) return

  const url = resolveUrl()
  if (!url) return

  setState(WS_STATES.CONNECTING)
  try {
    ws = new WebSocket(url)
  } catch {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    reconnectAttempts = 0
    setState(WS_STATES.CONNECTED)
    startHeartbeat()
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      lastMessage = data
      handleMessage(data)
      notify()
    } catch {
      // Ignore non-JSON frames (e.g. plain-text pong).
    }
  }

  ws.onclose = (event) => {
    stopHeartbeat()
    if (event.code !== 1000) scheduleReconnect()
    else setState(WS_STATES.DISCONNECTED)
  }

  ws.onerror = () => {
    // onclose follows; reconnect there.
  }
}

export function useGatewayWebSocket() {
  const queryClient = useQueryClient()
  const [snapshot, setSnapshot] = useState({ connectionState, lastMessage })

  useEffect(() => {
    queryClientRef = queryClient
    const cb = (next) => setSnapshot({ ...next })
    subscribers.add(cb)

    // First subscriber starts the connection.
    if (enabled && !ws) connect()

    return () => {
      subscribers.delete(cb)
      // Last subscriber tears down — keeps the singleton lifecycle aligned
      // with the app's lifecycle. SPA navigation rarely empties subscribers
      // entirely, so this mostly fires on unmount-during-tests.
      if (subscribers.size === 0) {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
        stopHeartbeat()
        if (ws) {
          try {
            ws.close(1000, 'No subscribers')
          } catch {
            // ignore
          }
          ws = null
        }
        queryClientRef = null
      }
    }
  }, [queryClient])

  return {
    connectionState: snapshot.connectionState,
    lastMessage: snapshot.lastMessage,
    isLive: snapshot.connectionState === WS_STATES.CONNECTED,
  }
}

useGatewayWebSocket.STATES = WS_STATES
