// Payload size comparison: minimal vs inflated feature values.
import http from 'k6/http';
import { Trend, Rate } from 'k6/metrics';

const smallLatency = new Trend('small_payload_ms');
const largeLatency = new Trend('large_payload_ms');
const failures = new Rate('failures');

export const options = {
  vus: 5,
  duration: '30s',
  thresholds: { 'failures': ['rate<0.01'] },
};

const TARGET = __ENV.TARGET;

const small = {
  temp_c: 25.0, vibration_mm_s: 1.0, pressure_kpa: 100.0,
  hours_since_service: 100.0, load_pct: 10.0, ambient_humidity: 20.0,
};

const large = {
  temp_c: 25.123456789012345, vibration_mm_s: 1.098765432109876,
  pressure_kpa: 100.987654321098765, hours_since_service: 100.123456789,
  load_pct: 10.987654321, ambient_humidity: 20.5678901234,
};

export default function () {
  const s = http.post(TARGET, JSON.stringify(small), {
    headers: { 'Content-Type': 'application/json' },
  });
  smallLatency.add(s.timings.duration);
  failures.add(s.status !== 200);

  const l = http.post(TARGET, JSON.stringify(large), {
    headers: { 'Content-Type': 'application/json' },
  });
  largeLatency.add(l.timings.duration);
  failures.add(l.status !== 200);
}
