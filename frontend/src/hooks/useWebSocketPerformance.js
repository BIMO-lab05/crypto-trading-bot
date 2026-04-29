/**
 * useWebSocketPerformance.js - Real-Time Performance WebSocket Hook
 *
 * Purpose: Custom React hook for connecting to the trading-engine WebSocket
 * endpoint to receive real-time performance metric updates.
 *
 * Features:
 * - Automatic WebSocket connection management
 * - Reconnection with exponential backoff
 * - Heartbeat/ping-pong for connection health
 * - React Query cache updates for real-time data
 * - Connection state tracking
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_OPTIONS = {
  // WebSocket URL - defaults to current host
  url: null,
  // Enable automatic connection on mount
  autoConnect: true,
  // Reconnection settings
  maxReconnectAttempts: 10,
  reconnectDelay: 1000,
  maxReconnectDelay: 30000,
  // Heartbeat settings
  heartbeatInterval: 30000,
  // Channels to subscribe to
  channels: ['metrics', 'equity', 'drawdown', 'trade'],
}

// ============================================================================
// WEBSOCKET STATES
// ============================================================================

const WS_STATES = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  RECONNECTING: 'reconnecting',
  FAILED: 'failed',
}

// ============================================================================
// MAIN HOOK
// ============================================================================

/**
 * useWebSocketPerformance - Real-time performance metrics via WebSocket
 *
 * @param {Object} options - Hook options
 * @param {string} options.url - WebSocket URL (default: auto-detect)
 * @param {boolean} options.autoConnect - Connect automatically on mount
 * @param {number} options.maxReconnectAttempts - Max reconnection attempts
 * @param {number} options.reconnectDelay - Initial reconnection delay (ms)
 * @param {number} options.heartbeatInterval - Heartbeat interval (ms)
 * @param {Array} options.channels - Channels to subscribe to
 * @returns {Object} WebSocket state and controls
 */
export function useWebSocketPerformance(options = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options }

  // State
  const [connectionState, setConnectionState] = useState(WS_STATES.DISCONNECTED)
  const [lastMessage, setLastMessage] = useState(null)
  const [lastError, setLastError] = useState(null)
  const [metrics, setMetrics] = useState(null)

  // Refs for mutable values
  const wsRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const heartbeatTimerRef = useRef(null)
  const mountedRef = useRef(true)

  // React Query client for cache updates
  const queryClient = useQueryClient()

  // ============================================================================
  // WEBSOCKET URL CONSTRUCTION
  // ============================================================================

  const getWebSocketUrl = useCallback(() => {
    if (opts.url) return opts.url

    // Auto-detect WebSocket URL based on current location.
    //
    // Earlier code hardcoded `ws://localhost:8001/api/v1/trading/ws/performance`
    // for dev — port 8001 is bybit-connector (which has no WS endpoint),
    // and even on the trading-engine that path doesn't exist. The
    // server-side WebSocket lives at `/ws` on the api-gateway only.
    // Both dev and prod now point at that single real endpoint:
    //   * dev:  ws://localhost:8000/ws (Vite has no WS proxy; talk to gateway directly)
    //   * prod: ws[s]://<host>/ws      (nginx /ws block proxies to gateway)
    //
    // If a dedicated /ws/performance endpoint is ever added on the
    // gateway (or the WebSocketManager learns to dispatch by message
    // channel), update both branches in lockstep.
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host

    if (import.meta.env.DEV) {
      return 'ws://localhost:8000/ws'
    }
    return `${protocol}//${host}/ws`
  }, [opts.url])

  // ============================================================================
  // CONNECTION MANAGEMENT
  // ============================================================================

  /**
   * Establish WebSocket connection
   */
  const connect = useCallback(() => {
    if (!mountedRef.current) return

    // Prevent multiple connections
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[useWebSocketPerformance] Already connected')
      return
    }

    const url = getWebSocketUrl()
    console.log(`[useWebSocketPerformance] Connecting to ${url}`)
    setConnectionState(WS_STATES.CONNECTING)

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      // Connection opened
      ws.onopen = () => {
        if (!mountedRef.current) return

        console.log('[useWebSocketPerformance] Connected')
        setConnectionState(WS_STATES.CONNECTED)
        reconnectAttemptsRef.current = 0
        setLastError(null)

        // Subscribe to channels
        opts.channels.forEach((channel) => {
          ws.send(JSON.stringify({ type: 'subscribe', channel }))
        })

        // Start heartbeat
        startHeartbeat()
      }

      // Message received
      ws.onmessage = (event) => {
        if (!mountedRef.current) return

        try {
          const data = JSON.parse(event.data)
          setLastMessage(data)
          handleMessage(data)
        } catch (error) {
          console.error('[useWebSocketPerformance] Message parse error:', error)
        }
      }

      // Connection closed
      ws.onclose = (event) => {
        if (!mountedRef.current) return

        console.log(`[useWebSocketPerformance] Disconnected: ${event.code}`)
        setConnectionState(WS_STATES.DISCONNECTED)
        stopHeartbeat()

        // Attempt reconnection if not intentional close
        if (event.code !== 1000) {
          scheduleReconnect()
        }
      }

      // Connection error
      ws.onerror = (error) => {
        if (!mountedRef.current) return

        console.error('[useWebSocketPerformance] Error:', error)
        setLastError(error)
      }
    } catch (error) {
      console.error('[useWebSocketPerformance] Connection failed:', error)
      setLastError(error)
      setConnectionState(WS_STATES.FAILED)
    }
  }, [getWebSocketUrl, opts.channels])

  /**
   * Disconnect WebSocket
   */
  const disconnect = useCallback(() => {
    console.log('[useWebSocketPerformance] Disconnecting')

    // Clear timers
    stopHeartbeat()
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    // Close connection
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect')
      wsRef.current = null
    }

    setConnectionState(WS_STATES.DISCONNECTED)
    reconnectAttemptsRef.current = 0
  }, [])

  /**
   * Schedule reconnection attempt with exponential backoff
   */
  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return
    if (reconnectAttemptsRef.current >= opts.maxReconnectAttempts) {
      console.log('[useWebSocketPerformance] Max reconnection attempts reached')
      setConnectionState(WS_STATES.FAILED)
      return
    }

    reconnectAttemptsRef.current += 1
    const delay = Math.min(
      opts.reconnectDelay * Math.pow(2, reconnectAttemptsRef.current - 1),
      opts.maxReconnectDelay
    )

    console.log(
      `[useWebSocketPerformance] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${opts.maxReconnectAttempts})`
    )
    setConnectionState(WS_STATES.RECONNECTING)

    reconnectTimerRef.current = setTimeout(() => {
      connect()
    }, delay)
  }, [connect, opts.maxReconnectAttempts, opts.reconnectDelay, opts.maxReconnectDelay])

  // ============================================================================
  // HEARTBEAT MANAGEMENT
  // ============================================================================

  const startHeartbeat = useCallback(() => {
    stopHeartbeat()
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }))
      }
    }, opts.heartbeatInterval)
  }, [opts.heartbeatInterval])

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
  }, [])

  // ============================================================================
  // MESSAGE HANDLING
  // ============================================================================

  const handleMessage = useCallback(
    (data) => {
      switch (data.type) {
        case 'pong':
          // Heartbeat acknowledged
          break

        case 'subscribed':
          console.log(`[useWebSocketPerformance] Subscribed to: ${data.channel}`)
          break

        case 'metrics':
          // Update metrics state
          setMetrics(data.payload)

          // Update React Query cache
          queryClient.setQueryData(['analytics', 'performance'], (old) => ({
            ...old,
            ...data.payload,
            timestamp: Date.now(),
          }))
          break

        case 'equity':
          // Update equity curve cache
          queryClient.setQueryData(['equity-curve'], (old) => {
            if (!old?.curve) return old
            return {
              ...old,
              curve: [...old.curve, data.payload],
            }
          })
          break

        case 'drawdown':
          // Update drawdown cache
          queryClient.setQueryData(['drawdown'], (old) => {
            if (!old?.drawdown) return old
            return {
              ...old,
              drawdown: [...old.drawdown, data.payload],
            }
          })
          break

        case 'trade':
          // Invalidate trade-related queries to trigger refetch
          queryClient.invalidateQueries({ queryKey: ['analytics', 'trades'] })
          queryClient.invalidateQueries({ queryKey: ['analytics', 'performance'] })
          break

        default:
          console.log('[useWebSocketPerformance] Unknown message type:', data.type)
      }
    },
    [queryClient]
  )

  // ============================================================================
  // SEND MESSAGE
  // ============================================================================

  const sendMessage = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      return true
    }
    console.warn('[useWebSocketPerformance] Cannot send - not connected')
    return false
  }, [])

  // ============================================================================
  // LIFECYCLE
  // ============================================================================

  // Mount/unmount handling
  useEffect(() => {
    mountedRef.current = true

    if (opts.autoConnect) {
      connect()
    }

    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, []) // Intentionally empty - only run on mount/unmount

  // ============================================================================
  // RETURN VALUE
  // ============================================================================

  return {
    // Connection state
    connectionState,
    isConnected: connectionState === WS_STATES.CONNECTED,
    isConnecting: connectionState === WS_STATES.CONNECTING,
    isReconnecting: connectionState === WS_STATES.RECONNECTING,
    isFailed: connectionState === WS_STATES.FAILED,

    // Data
    lastMessage,
    metrics,

    // Error
    lastError,
    reconnectAttempts: reconnectAttemptsRef.current,

    // Controls
    connect,
    disconnect,
    sendMessage,
  }
}

// Export states for external use
export { WS_STATES }

// Default export
export default useWebSocketPerformance
