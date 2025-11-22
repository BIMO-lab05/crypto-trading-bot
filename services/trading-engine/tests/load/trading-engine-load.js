/**
 * k6 Load Test for Trading Engine
 * Purpose: Test API performance under various load conditions
 *
 * Run with: k6 run trading-engine-load.js
 * For smoke test: k6 run --vus 1 --duration 30s trading-engine-load.js
 * For load test: k6 run --vus 10 --duration 5m trading-engine-load.js
 * For stress test: k6 run --vus 50 --duration 10m trading-engine-load.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const signalResponseTime = new Trend('signal_response_time');
const healthResponseTime = new Trend('health_response_time');
const apiErrors = new Counter('api_errors');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8005';
const SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'];

// Test options
export const options = {
  // Stages for ramping up and down
  stages: [
    { duration: '30s', target: 5 },   // Ramp up to 5 users
    { duration: '1m', target: 10 },   // Stay at 10 users
    { duration: '30s', target: 20 },  // Spike to 20 users
    { duration: '1m', target: 10 },   // Back to 10 users
    { duration: '30s', target: 0 },   // Ramp down
  ],

  // Thresholds - SLAs for the API
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // 95% under 500ms, 99% under 1s
    http_req_failed: ['rate<0.05'],                  // Less than 5% errors
    errors: ['rate<0.1'],                            // Less than 10% errors
    http_reqs: ['rate>10'],                          // At least 10 req/s
  },

  // Graceful ramp down
  gracefulStop: '30s',
};

// Setup function - runs once before the test
export function setup() {
  // Verify service is up
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    throw new Error('Service is not healthy');
  }
  console.log('Setup: Trading Engine is healthy');
  return { startTime: new Date().toISOString() };
}

// Main test function - runs for each VU
export default function (data) {
  // Test health endpoint
  group('Health Checks', () => {
    const start = new Date();
    const res = http.get(`${BASE_URL}/health`);
    const duration = new Date() - start;

    healthResponseTime.add(duration);

    const success = check(res, {
      'health status is 200': (r) => r.status === 200,
      'health response has status': (r) => r.json('status') === 'healthy',
      'health response time < 100ms': () => duration < 100,
    });

    errorRate.add(!success);
    if (!success) apiErrors.add(1);
  });

  sleep(0.5);

  // Test ready endpoint
  group('Readiness Checks', () => {
    const res = http.get(`${BASE_URL}/ready`);

    check(res, {
      'ready status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    });
  });

  sleep(0.5);

  // Test signal aggregation endpoint - the critical path
  group('Signal Aggregation', () => {
    const symbol = SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)];
    const interval = [15, 60, 240, 1440][Math.floor(Math.random() * 4)];

    const start = new Date();
    const res = http.get(`${BASE_URL}/api/v1/signals/aggregate`, {
      params: {
        symbol: symbol,
        interval: interval.toString(),
      },
      tags: { name: 'SignalAggregation' },
    });
    const duration = new Date() - start;

    signalResponseTime.add(duration);

    const success = check(res, {
      'signal status is 200 or 503': (r) => r.status === 200 || r.status === 503,
      'signal response time < 2000ms': () => duration < 2000,
    });

    if (res.status === 200) {
      const hasAction = check(res, {
        'signal has action': (r) => {
          try {
            const body = r.json();
            return body.action !== undefined || (body.signal && body.signal.action !== undefined);
          } catch (e) {
            return false;
          }
        },
        'signal has confidence': (r) => {
          try {
            const body = r.json();
            return body.confidence !== undefined || (body.signal && body.signal.confidence !== undefined);
          } catch (e) {
            return false;
          }
        },
      });

      if (!hasAction) apiErrors.add(1);
    }

    errorRate.add(!success);
  });

  sleep(1);

  // Test positions endpoint
  group('Position Management', () => {
    const res = http.get(`${BASE_URL}/api/v1/positions`);

    check(res, {
      'positions status is 200': (r) => r.status === 200,
      'positions response is valid': (r) => {
        try {
          const body = r.json();
          return Array.isArray(body) || typeof body === 'object';
        } catch (e) {
          return false;
        }
      },
    });
  });

  sleep(0.5);

  // Test portfolio endpoints
  group('Portfolio Queries', () => {
    const res = http.get(`${BASE_URL}/api/v1/portfolio/balance`);

    check(res, {
      'balance status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    });
  });

  // Random think time between iterations
  sleep(Math.random() * 3 + 1); // 1-4 seconds
}

// Teardown function - runs once after the test
export function teardown(data) {
  console.log('Teardown: Test completed');
  console.log(`Started at: ${data.startTime}`);
  console.log(`Ended at: ${new Date().toISOString()}`);
}

// Handle summary data
export function handleSummary(data) {
  return {
    'load-test-summary.json': JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let summary = `\n${indent}Test Summary:\n`;
  summary += `${indent}=============\n\n`;

  // Metrics
  if (data.metrics) {
    summary += `${indent}Metrics:\n`;

    // HTTP requests
    const httpReqs = data.metrics.http_reqs;
    if (httpReqs) {
      summary += `${indent}  Total Requests: ${httpReqs.values.count}\n`;
      summary += `${indent}  Request Rate: ${httpReqs.values.rate.toFixed(2)} req/s\n`;
    }

    // Response time
    const httpDuration = data.metrics.http_req_duration;
    if (httpDuration) {
      summary += `${indent}  Response Time (avg): ${httpDuration.values.avg.toFixed(2)}ms\n`;
      summary += `${indent}  Response Time (p95): ${httpDuration.values['p(95)'].toFixed(2)}ms\n`;
      summary += `${indent}  Response Time (p99): ${httpDuration.values['p(99)'].toFixed(2)}ms\n`;
    }

    // Error rate
    const httpFailed = data.metrics.http_req_failed;
    if (httpFailed) {
      const failRate = (httpFailed.values.rate * 100).toFixed(2);
      summary += `${indent}  Error Rate: ${failRate}%\n`;
    }
  }

  return summary;
}
