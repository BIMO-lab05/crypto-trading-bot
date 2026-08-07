import '@testing-library/jest-dom'

// jsdom does not implement ResizeObserver, but recharts' ResponsiveContainer
// requires it at mount — without this stub every component that renders a
// chart throws "ReferenceError: ResizeObserver is not defined" during commit.
// A no-op stub is sufficient: no test asserts on real resize behavior.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = ResizeObserverStub
}
