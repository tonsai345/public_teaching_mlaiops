// Batch comparison: 100 singles vs 1 batch of 100.
import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const singleLatency = new Trend('single_latency_ms');
const batchLatency = new Trend('batch_latency_ms');
const failures = new Rate('failures');

export const options = {
  vus: 5,
  duration: '30s',
  thresholds: {
    'failures': ['rate<0.01'],
  },
};

const row = {
  temp_c: 78.4,
  vibration_mm_s: 3.1,
  pressure_kpa: 315.2,
  hours_since_service: 4200,
  load_pct: 68.0,
  ambient_humidity: 55.0,
};

const SINGLE_URL = __ENV.TARGET;
const BATCH_URL = SINGLE_URL.replace('/predict', '/predict/batch');

export default function () {
  // Single request
  const single = http.post(SINGLE_URL, JSON.stringify(row), {
    headers: { 'Content-Type': 'application/json' },
  });
  singleLatency.add(single.timings.duration);
  failures.add(single.status !== 200);

  // Batch of 100 identical rows
  const batch = http.post(BATCH_URL, JSON.stringify({ rows: Array(100).fill(row) }), {
    headers: { 'Content-Type': 'application/json' },
  });
  batchLatency.add(batch.timings.duration);
  failures.add(batch.status !== 200);

  check(batch, {
    'batch status 200': (r) => r.status === 200,
    'batch returned 100 probabilities': (r) =>
      r.status === 200 && r.json('probabilities').length === 100,
  });
}
