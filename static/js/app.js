/* ------------------------------------------------------------------
   MODIS x VIIRS dashboard.
   Talks to app.py (which calls compare.py) and draws the results.
   ------------------------------------------------------------------ */
"use strict";

const COLORS = {
  both: "#22c55e",
  modis: "#3b82f6",
  viirs: "#f97316",
  low: "#ef4444",
  nominal: "#eab308",
  high: "#22c55e",
};

const state = {
  report: null,
  source: "sample",
  settings: { grid: 0.05, day_mode: "local" },
  days: new Set(),              // selected days -- empty means "all days"
  cats: { both: true, modis_only: true, viirs_only: true },
  page: 100,
  sort: { key: "utc", dir: 1 },
  filters: { sensor: "all", conf: "all", day: "all", q: "" },
};

let map = null;
let cellLayer = null;
let calendarChart = null;
let confChart = null;
let firstDraw = true;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ----------------------------- helpers ----------------------------- */
function banner(message, ok = false) {
  const el = $("#banner");
  if (!message) { el.hidden = true; return; }
  el.hidden = false;
  el.textContent = message;
  el.classList.toggle("ok", ok);
}

function busy(on) { $("#loading").hidden = !on; }

function fmt(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function params() {
  return `grid=${state.settings.grid}&day_mode=${state.settings.day_mode}`;
}

/* ----------------------------- data load --------------------------- */
async function load() {
  busy(true);
  try {
    const res = await fetch(`/api/analyze?${params()}`);
    if (!res.ok) throw new Error((await res.json()).error || `HTTP ${res.status}`);
    state.report = await res.json();
    state.source = state.report.source || "sample";
    renderAll();
    banner("");
  } catch (err) {
    banner(`Could not run the analysis: ${err.message}`);
  } finally {
    busy(false);
  }
}

async function loadState() {
  const res = await fetch("/api/state");
  const cfg = await res.json();
  const select = $("#gridSelect");
  select.innerHTML = "";
  for (const g of cfg.grid_choices) {
    const opt = document.createElement("option");
    opt.value = g;
    opt.textContent = `${g.toFixed(2)}°`;
    if (g === cfg.default_grid) opt.selected = true;
    select.appendChild(opt);
  }
  state.settings.grid = cfg.default_grid;
}

/* ----------------------------- rendering --------------------------- */
function renderAll() {
  renderKpis();
  renderCalendarChart();
  renderConfChart();
  renderChips();
  renderCalendarTable();
  renderChecks();
  renderRows(true);
  drawMap();
  syncDownloadLinks();
  $("#gridLabel").textContent = `· ${state.settings.grid.toFixed(2)}° cells`;
  $("#dayModeSelect").value = state.settings.day_mode;
  $("#gridSelect").value = state.settings.grid;
  fillDayFilter();
}

function renderKpis() {
  const s = state.report.summary;
  const cells = state.report.cells;
  const uniqueCells = new Set(cells.map((c) => c.cell)).size;
  const bothDays = s.both_sensor_days.length;
  const totalDays = s.days.total;
  const cards = [
    {
      cls: "modis", label: "MODIS detections", value: fmt(s.rows.MODIS || 0),
      sub: `avg pixel ${fmt(s.avg_area_km2.MODIS, 2)} km²`,
    },
    {
      cls: "viirs", label: "VIIRS detections", value: fmt(s.rows.VIIRS || 0),
      sub: `avg pixel ${fmt(s.avg_area_km2.VIIRS, 2)} km²`,
    },
    {
      cls: "both", label: "MODIS cells also seen by VIIRS",
      value: `${fmt(s.modis_cells_seen_by_viirs_pct, 1)}%`,
      sub: `both-sensor days · pooled cells ${fmt(s.modis_cells_seen_by_viirs_union_pct, 1)}%`,
    },
    {
      cls: "both", label: "Days with data from both sensors",
      value: `${bothDays} / ${totalDays}`,
      sub: s.one_sensor_days.length ? `one sensor only: ${s.one_sensor_days.join(", ")}` : "all days covered by both",
    },
    {
      cls: "", label: "Grid cells with fires", value: fmt(uniqueCells),
      sub: `${state.settings.grid.toFixed(2)}° cells (≈ ${fmt(state.settings.grid * 111, 1)} km)`,
    },
    {
      cls: "", label: "Days in range", value: fmt(totalDays),
      sub: state.settings.day_mode === "local" ? "grouped by local solar date" : "grouped by UTC date",
    },
  ];

  $("#kpis").innerHTML = cards.map((c) => `
    <div class="kpi ${c.cls}">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub}</div>
    </div>`).join("");
}

/* ----------------------------- charts ------------------------------ */
function renderCalendarChart() {
  const cal = state.report.calendar;
  const labels = cal.map((d) => d.day);
  const data = {
    labels,
    datasets: [
      { label: "both", data: cal.map((d) => d.both), backgroundColor: COLORS.both },
      { label: "MODIS only", data: cal.map((d) => d.modis_only), backgroundColor: COLORS.modis },
      { label: "VIIRS only", data: cal.map((d) => d.viirs_only), backgroundColor: COLORS.viirs },
    ],
  };

  if (calendarChart) calendarChart.destroy();
  calendarChart = new Chart($("#calendarChart"), {
    type: "bar",
    data,
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      onClick: (_evt, elements) => {
        if (!elements.length) return;
        toggleDay(labels[elements[0].index]);
      },
      plugins: {
        legend: { labels: { color: "#cfe0ff", boxWidth: 12 } },
        layout: { padding: { right: 16 } },
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const row = cal[items[0].dataIndex];
              const share = row.both + row.modis_only > 0
                ? (100 * row.both / (row.both + row.modis_only)).toFixed(1) : "0.0";
              return `MODIS cells also seen by VIIRS: ${share}%\nrows ${row.modis_rows} / ${row.viirs_rows}`
                + (row.only_one_sensor ? "\n⚠ only one sensor has data" : "");
            },
          },
        },
      },
      scales: {
        x: { stacked: true, ticks: { color: "#93a0c4" }, grid: { color: "#1d2745" } },
        y: { stacked: true, ticks: { color: "#cfe0ff" }, grid: { color: "#1d2745" } },
      },
    },
  });
}

function renderConfChart() {
  const split = state.report.summary.confidence_split_pct;
  const sensors = ["MODIS", "VIIRS"].filter((s) => split[s]);
  const data = {
    labels: sensors,
    datasets: [
      { label: "low", data: sensors.map((s) => split[s].low), backgroundColor: COLORS.low },
      { label: "nominal", data: sensors.map((s) => split[s].nominal), backgroundColor: COLORS.nominal },
      { label: "high", data: sensors.map((s) => split[s].high), backgroundColor: COLORS.high },
    ],
  };

  if (confChart) confChart.destroy();
  confChart = new Chart($("#confChart"), {
    type: "bar",
    data,
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#cfe0ff", boxWidth: 12 } },
        layout: { padding: { right: 16 } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.x.toFixed(1)}%` } },
      },
      scales: {
        x: { stacked: true, max: 100, ticks: { color: "#93a0c4", callback: (v) => `${v}%` }, grid: { color: "#1d2745" } },
        y: { stacked: true, ticks: { color: "#cfe0ff" }, grid: { color: "#1d2745" } },
      },
    },
  });
}

/* ----------------------------- day chips --------------------------- */
function toggleDay(day) {
  if (state.days.has(day)) state.days.delete(day);
  else state.days.add(day);
  if (state.filters.day !== "all" && !state.days.has(state.filters.day)) state.filters.day = "all";
  renderChips();
  renderCalendarTable();
  drawMap();
  renderRows(true);
}

function selectAllDays() {
  state.days.clear();
  state.filters.day = "all";
  renderChips();
  renderCalendarTable();
  drawMap();
  renderRows(true);
}

function renderChips() {
  const cal = state.report.calendar;
  const html = [
    `<button class="chip ${state.days.size ? "" : "on"}" data-day="__all">all days</button>`,
    ...cal.map((d) => `
      <button class="chip ${state.days.has(d.day) ? "on" : ""} ${d.only_one_sensor ? "flag" : ""}"
              data-day="${d.day}" title="${d.only_one_sensor ? "only one sensor has data" : "both sensors"}">
        ${d.day}${d.only_one_sensor ? " ⚑" : ""}
      </button>`),
  ].join("");
  $("#dayChips").innerHTML = html;
  $$("#dayChips .chip").forEach((chip) => chip.addEventListener("click", () => {
    chip.dataset.day === "__all" ? selectAllDays() : toggleDay(chip.dataset.day);
  }));
}

/* ----------------------------- calendar table ---------------------- */
function renderCalendarTable() {
  const body = $("#calendarTable tbody");
  body.innerHTML = state.report.calendar.map((d) => {
    const modisCells = d.both + d.modis_only;
    const share = modisCells ? (100 * d.both / modisCells) : 0;
    const selected = state.days.has(d.day);
    return `
      <tr class="clickable ${selected ? "sel" : ""}" data-day="${d.day}">
        <td>${d.day}</td>
        <td class="num">${d.both}</td>
        <td class="num">${d.modis_only}</td>
        <td class="num">${d.viirs_only}</td>
        <td class="num">${d.modis_rows} / ${d.viirs_rows}</td>
        <td class="num">${modisCells ? share.toFixed(1) + "%" : "–"}</td>
        <td>${d.only_one_sensor ? '<span class="badge flag">one sensor</span>' : '<span class="badge ok">both</span>'}</td>
      </tr>`;
  }).join("");
  $$("#calendarTable tbody tr").forEach((tr) =>
    tr.addEventListener("click", () => toggleDay(tr.dataset.day)));
}

/* ----------------------------- checks ------------------------------ */
function renderChecks() {
  const body = $("#checksTable tbody");
  const note = $("#checksNote");

  if (state.source !== "sample") {
    body.innerHTML = `<tr><td colspan="4" class="hint" style="padding:14px">
      Reference values only apply to the bundled sample files.</td></tr>`;
    note.textContent = "";
    return;
  }

  body.innerHTML = state.report.checks.map((c) => {
    const badge = c.ok === null ? '<span class="badge na">n/a</span>'
      : c.ok ? '<span class="badge ok">OK</span>' : '<span class="badge off">OFF</span>';
    return `
      <tr>
        <td>${badge}</td>
        <td>${c.label}${c.note ? `<div class="hint">${c.note}</div>` : ""}</td>
        <td class="num">${c.computed ?? "n/a"}</td>
        <td class="num">${c.expected}</td>
      </tr>`;
  }).join("");

  const s = state.report.summary;
  note.innerHTML = `The headline overlap (<b>${fmt(s.modis_cells_seen_by_viirs_pct, 1)}%</b>) covers every day
    with data from both sensors (${s.both_sensor_days.join(", ")}). The “≈59%” reference is the same
    statistic restricted to 27–28 Sep, as written in the instructions.`;
}

/* ----------------------------- map --------------------------------- */
function initMap() {
  map = L.map("map", { scrollWheelZoom: true });
  // Esri world imagery: no API key needed and it reads well under the
  // bright fire-cell colours.  If there is no internet connection the
  // rectangles still render on the dark background.
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
      maxZoom: 18,
      detectRetina: true,
    }
  ).addTo(map);
  cellLayer = L.layerGroup().addTo(map);
  map.setView([-16, -62], 6);
}

function activeCells() {
  // Merge the selected days into one rectangle per grid cell.
  const merged = new Map();
  for (const c of state.report.cells) {
    if (state.days.size && !state.days.has(c.day)) continue;
    const key = `${c.lat_min}|${c.lon_min}`;
    let e = merged.get(key);
    if (!e) {
      e = { lat_min: c.lat_min, lon_min: c.lon_min, m: 0, v: 0, days: new Set() };
      merged.set(key, e);
    }
    e.m += c.modis_rows;
    e.v += c.viirs_rows;
    e.days.add(c.day);
  }

  const out = [];
  for (const e of merged.values()) {
    const cat = e.m > 0 && e.v > 0 ? "both" : e.m > 0 ? "modis_only" : "viirs_only";
    if (!state.cats[cat]) continue;
    e.cat = cat;
    out.push(e);
  }
  return out;
}

function drawMap() {
  if (!state.report) return;
  if (!map) initMap();

  const cells = activeCells();
  cellLayer.clearLayers();

  const g = state.settings.grid;
  for (const c of cells) {
    const color = COLORS[c.cat === "modis_only" ? "modis" : c.cat === "viirs_only" ? "viirs" : "both"];
    const rect = L.rectangle(
      [[c.lat_min, c.lon_min], [c.lat_min + g, c.lon_min + g]],
      { color, weight: 0.7, fillColor: color, fillOpacity: 0.45 }
    );
    rect.bindPopup(popupHtml(c, g));
    rect.addTo(cellLayer);
  }

  if (firstDraw && cells.length) {
    const bounds = L.latLngBounds(cells.flatMap((c) => [
      [c.lat_min, c.lon_min], [c.lat_min + g, c.lon_min + g],
    ]));
    map.fitBounds(bounds.pad(0.15));
    firstDraw = false;
  }

  const dayText = state.days.size ? `${state.days.size} selected day(s)` : "all days";
  $("#mapCount").textContent = `${cells.length} cells · ${dayText}`;
}

function popupHtml(c, g) {
  const catLabel = { both: "both sensors", modis_only: "MODIS only", viirs_only: "VIIRS only" }[c.cat];
  const dayList = Array.from(c.days).sort().join("<br>");
  const lat = (c.lat_min + g / 2).toFixed(3);
  const lon = (c.lon_min + g / 2).toFixed(3);
  return `
    <div class="popup">
      <h4>${catLabel}</h4>
      <table>
        <tr><td>cell centre</td><td>${lat}, ${lon}</td></tr>
        <tr><td>MODIS rows</td><td>${c.m}</td></tr>
        <tr><td>VIIRS rows</td><td>${c.v}</td></tr>
        <tr><td>days</td><td>${dayList}</td></tr>
      </table>
    </div>`;
}

/* ----------------------------- detections table -------------------- */
function filteredRows() {
  const f = state.filters;
  const q = f.q.trim().toLowerCase();
  let rows = state.report.rows.filter((r) => {
    if (f.sensor !== "all" && r.sensor !== f.sensor) return false;
    if (f.conf !== "all" && r.conf !== f.conf) return false;
    if (f.day !== "all" && r.day !== f.day) return false;
    if (state.days.size && !state.days.has(r.day)) return false;
    if (q && !`${r.cell} ${r.day} ${r.satellite} ${r.utc} ${r.local} ${r.conf_raw}`.toLowerCase().includes(q)) return false;
    return true;
  });

  const { key, dir } = state.sort;
  rows.sort((a, b) => {
    const av = a[key], bv = b[key];
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });
  return rows;
}

function renderRows(resetPage) {
  if (!state.report) return;
  if (resetPage) state.page = 100;

  const rows = filteredRows();
  const shown = rows.slice(0, state.page);

  $("#rowsTable tbody").innerHTML = shown.map((r) => `
    <tr>
      <td><span class="badge ${r.sensor === "MODIS" ? "modis" : "viirs"}">${r.sensor}</span></td>
      <td>${r.day}</td>
      <td>${r.utc}</td>
      <td>${r.local}</td>
      <td class="num">${fmt(r.lat, 4)}</td>
      <td class="num">${fmt(r.lon, 4)}</td>
      <td><span class="badge ${r.conf}">${r.conf}</span></td>
      <td>${r.conf_raw}</td>
      <td class="num">${fmt(r.frp, 1)}</td>
      <td class="num">${fmt(r.area, 2)}</td>
      <td>${r.cell}</td>
    </tr>`).join("");

  $("#rowCount").textContent = `${fmt(shown.length)} of ${fmt(rows.length)} rows`;
  $("#btnMore").disabled = shown.length >= rows.length;
}

/* ----------------------------- downloads --------------------------- */
function syncDownloadLinks() {
  for (const [id, name] of [["#dlCombined", "combined.csv"], ["#dlCalendar", "calendar.csv"], ["#dlPng", "calendar.png"]]) {
    $(id).href = `/api/download/${name}?${params()}`;
  }
}

/* ----------------------------- events ------------------------------ */
function bindEvents() {
  $("#btnAnalyze").addEventListener("click", () => {
    state.settings.grid = parseFloat($("#gridSelect").value);
    state.settings.day_mode = $("#dayModeSelect").value;
    firstDraw = true;
    load();
  });

  $("#dayModeSelect").addEventListener("change", () => $("#btnAnalyze").click());
  $("#gridSelect").addEventListener("change", () => $("#btnAnalyze").click());

  $$(".cat").forEach((box) => box.addEventListener("change", () => {
    state.cats[box.value] = box.checked;
    drawMap();
  }));

  $("#fSensor").addEventListener("change", (e) => { state.filters.sensor = e.target.value; renderRows(true); });
  $("#fConf").addEventListener("change", (e) => { state.filters.conf = e.target.value; renderRows(true); });
  $("#fDay").addEventListener("change", (e) => { state.filters.day = e.target.value; renderRows(true); });
  $("#fSearch").addEventListener("input", (e) => { state.filters.q = e.target.value; renderRows(true); });
  $("#btnMore").addEventListener("click", () => { state.page += 100; renderRows(false); });

  $$("#rowsTable thead th").forEach((th) => th.addEventListener("click", () => {
    const key = th.dataset.key;
    state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : 1 };
    renderRows(false);
  }));

  // Upload flow: pick modis.csv, then viirs.csv, then send both to the server.
  $("#btnUpload").addEventListener("click", () => $("#fileModis").click());
  $("#fileModis").addEventListener("change", () => $("#fileViirs").click());
  $("#fileViirs").addEventListener("change", async () => {
    const modis = $("#fileModis").files[0];
    const viirs = $("#fileViirs").files[0];
    if (!modis || !viirs) return;
    const form = new FormData();
    form.append("modis", modis);
    form.append("viirs", viirs);
    busy(true);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
      state.days.clear();
      firstDraw = true;
      await load();
      banner(`Loaded ${modis.name} + ${viirs.name}.`, true);
    } catch (err) {
      banner(`Upload failed: ${err.message}`);
    } finally {
      busy(false);
      $("#fileModis").value = "";
      $("#fileViirs").value = "";
    }
  });

  $("#btnReset").addEventListener("click", async () => {
    await fetch("/api/reset", { method: "POST" });
    state.days.clear();
    firstDraw = true;
    await load();
    banner("Back to the bundled sample files.", true);
  });
}

function fillDayFilter() {
  const select = $("#fDay");
  const current = state.filters.day;
  select.innerHTML = `<option value="all">all days</option>` +
    state.report.calendar.map((d) => `<option value="${d.day}">${d.day}</option>`).join("");
  select.value = current;
}

/* ----------------------------- boot -------------------------------- */
document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadState();
  await load();
  fillDayFilter();
  window.addEventListener("resize", () => map && map.invalidateSize());
});
