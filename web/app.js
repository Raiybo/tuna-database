/* Tuna - client-side bluefin casting dashboard.
 * Mirrors src/tuna/config.py + scoring.py so the map matches the CLI report.
 * Pulls live sea-surface temperature + wave height per spot from Open-Meteo
 * (free, no key, CORS-enabled) and ranks spots for surface casting today.
 */

// --- scoring config (keep in sync with src/tuna/config.py) ---
const SST_BANDS = [[18, 24, 1.0], [16, 26, 0.6], [14, 28, 0.3]];
const SST_FLOOR = 0.1;
const WAVE_BANDS = [[0.8, 1.0], [1.5, 0.7], [2.0, 0.4]];
const WAVE_FLOOR = 0.1;
const W_SST = 0.55, W_WAVE = 0.30, W_FRONT = 0.15;
const FRONT_MIN_SPREAD = 0.5, FRONT_BASELINE = 0.3;

const COLORS = { PRIME: "#1a9850", GOOD: "#91cf60", FAIR: "#fdae61", POOR: "#d73027" };

function sstScore(t) {
  if (t == null) return 0;
  for (const [lo, hi, s] of SST_BANDS) if (t >= lo && t <= hi) return s;
  return SST_FLOOR;
}
function waveScore(h) {
  if (h == null) return 0;
  for (const [max, s] of WAVE_BANDS) if (h <= max) return s;
  return WAVE_FLOOR;
}
function median(xs) {
  const a = [...xs].sort((p, q) => p - q);
  const m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
function frontScores(ssts) {
  const vals = ssts.filter((s) => s != null);
  if (!vals.length) return ssts.map(() => FRONT_BASELINE);
  const spread = Math.max(...vals) - Math.min(...vals);
  if (spread < FRONT_MIN_SPREAD) return ssts.map(() => FRONT_BASELINE);
  const mid = median(vals), half = spread / 2;
  return ssts.map((s) => (s == null ? FRONT_BASELINE : Math.max(0, Math.min(1, Math.abs(s - mid) / half))));
}
function rating(score) {
  if (score >= 0.75) return "PRIME";
  if (score >= 0.55) return "GOOD";
  if (score >= 0.35) return "FAIR";
  return "POOR";
}

// --- live marine data ---
async function fetchMarine(lat, lon) {
  const url = `https://marine-api.open-meteo.com/v1/marine?latitude=${lat}&longitude=${lon}` +
    `&hourly=sea_surface_temperature,wave_height&timezone=auto&forecast_days=1`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Open-Meteo ${res.status}`);
  const d = await res.json();
  const times = d.hourly?.time || [];
  const ssts = d.hourly?.sea_surface_temperature || [];
  const waves = d.hourly?.wave_height || [];
  const offset = d.utc_offset_seconds || 0;
  const local = new Date(Date.now() + offset * 1000);
  const label = local.toISOString().slice(0, 13) + ":00";
  let idx = times.indexOf(label);
  if (idx < 0) idx = times.findIndex((t) => t.endsWith(`T${String(local.getUTCHours()).padStart(2, "0")}:00`));
  if (idx < 0) idx = Math.min(12, times.length - 1);
  return { sst: ssts[idx] ?? null, wave: waves[idx] ?? null, hour: times[idx] || label };
}

// --- map setup ---
const map = L.map("map").setView([33.85, 35.45], 8);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap &copy; CARTO", maxZoom: 19,
}).addTo(map);

const markers = {};
const statusEl = document.getElementById("status");
const rankingEl = document.getElementById("ranking");

function fmt(v, suffix, nd = 1) { return v == null ? "n/a" : v.toFixed(nd) + suffix; }

async function load() {
  statusEl.textContent = "Loading live sea conditions…";
  rankingEl.innerHTML = "";
  Object.values(markers).forEach((m) => map.removeLayer(m));

  let db;
  try {
    const res = await fetch("../data/spots.json");
    db = await res.json();
  } catch (e) {
    statusEl.textContent = "Could not load spots.json — serve the repo root (see README).";
    return;
  }
  const spots = db.spots;

  const marine = await Promise.all(spots.map((s) =>
    fetchMarine(s.lat, s.lon).catch(() => ({ sst: null, wave: null, hour: null }))));
  const fronts = frontScores(marine.map((m) => m.sst));

  const rows = spots.map((spot, i) => {
    const m = marine[i];
    const total = W_SST * sstScore(m.sst) + W_WAVE * waveScore(m.wave) + W_FRONT * fronts[i];
    return { spot, m, score: total, rating: rating(total) };
  }).sort((a, b) => b.score - a.score);

  const asof = rows.find((r) => r.m.hour)?.m.hour || "now";
  statusEl.textContent = `As of ${asof} (Asia/Beirut) · ${rows.length} spots · prime windows 05:00–08:00 & 18:00–20:00`;

  rows.forEach((r, rank) => {
    const c = COLORS[r.rating];
    const marker = L.circleMarker([r.spot.lat, r.spot.lon], {
      radius: 9, color: "#0b1f2a", weight: 2, fillColor: c, fillOpacity: 0.9,
    }).addTo(map);
    marker.bindPopup(
      `<b>#${rank + 1} ${r.spot.name}</b> — ${r.spot.area}<br>` +
      `<b>${r.rating}</b> · score ${r.score.toFixed(2)}<br>` +
      `SST ${fmt(r.m.sst, " °C")} · wave ${fmt(r.m.wave, " m")}<br>` +
      `<small>${r.spot.lat.toFixed(3)}, ${r.spot.lon.toFixed(3)} · ${r.spot.depth_zone}</small><br>` +
      `<small>${r.spot.notes}</small>`);
    markers[r.spot.id] = marker;

    const li = document.createElement("li");
    li.className = r.rating.toLowerCase();
    li.innerHTML =
      `<div class="rk-head"><span class="rk-name">${rank + 1}. ${r.spot.name}</span>` +
      `<span class="rk-rating">${r.rating} ${r.score.toFixed(2)}</span></div>` +
      `<div class="rk-meta">SST ${fmt(r.m.sst, " °C")} · wave ${fmt(r.m.wave, " m")} · ${r.spot.area}</div>` +
      `<div class="rk-coords">${r.spot.lat.toFixed(3)}, ${r.spot.lon.toFixed(3)}</div>`;
    li.onclick = () => { map.setView([r.spot.lat, r.spot.lon], 11); marker.openPopup(); };
    rankingEl.appendChild(li);
  });
}

document.getElementById("refresh").onclick = load;
load();
