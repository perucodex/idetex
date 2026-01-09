// Kiosk Control Pedido - Carrusel 4 columnas visibles (la 5ta queda oculta para animación)

const REFRESH_MS = 15 * 60 * 1000; // 15 min
const SLIDE_MS = 5 * 1000;        // 20 s
const DEFAULT_LIMIT = 300;

const VISIBLE_COLS = 4;              // ✅ SOLO 4 visibles en pantalla
const TRACK_COLS = VISIBLE_COLS + 1; // columna extra para animación (queda fuera de vista)
const GAP_PX = 12;                   // debe coincidir con el CSS

let state = {
  records: [],
  columns: [],
  startCol: 0,
  rowsPerCol: null,
  slideTimer: null,
  refreshTimer: null,
  sliding: false,
};

function fmtNow() {
  return new Date().toLocaleString();
}

// ✅ Compatible (sin replaceAll)
function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function pad2(n) {
  n = Number(n) || 0;
  return n < 10 ? "0" + n : String(n);
}

// Fecha: DD/MM/YY (sin siglo)
function fmtDateDMYShort(v) {
  if (!v) return "-";
  const s = String(v).trim();
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1].slice(2)}`;

  const d = new Date(s);
  if (!isNaN(d.getTime())) {
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${String(d.getFullYear()).slice(2)}`;
  }
  return s;
}

// Normaliza textos (quita acentos)
function normArea(s) {
  return String(s ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

// Abreviación de áreas
function abbrevArea(area) {
  const a = normArea(area);
  if (!a) return "-";

  const map = {
    "tejeduria": "TEJ",
    "pre tintoreria": "PTI",
    "tintoreria": "TIN",
    "pre estampado": "PES",
    "estampado": "EST",
    "pre acabado": "PAC",
    "acabado": "ACA",
    "control de calidad": "CC",
    "voucher": "VOU",
  };

  if (map[a]) return map[a];

  const only = a.replace(/[^a-z]/g, "");
  if (only.length >= 3) return only.slice(0, 3).toUpperCase();
  return (only || a).toUpperCase();
}

// Etiquetas de estado
function badgeForState(st) {
  const v = String(st ?? "").toLowerCase();
  if (v === "on") return `<span class="badge badge-on">On Time</span>`;
  if (v === "de") return `<span class="badge badge-de">Delayed</span>`;
  return `<span class="badge badge-ot">${escapeHtml(v || "-")}</span>`;
}

function buildTable(colRecords) {
  const headers = ["Fecha", "Pedido", "Días", "Área", "Estado"];

  const rows = (colRecords || []).map(r => {
    const fecShort = fmtDateDMYShort(r.fecoc);
    const areaShort = abbrevArea(r.area);
    return `
      <tr>
        <td class="kiosk-amber" title="${escapeHtml(r.fecoc)}">${escapeHtml(fecShort)}</td>
        <td title="${escapeHtml(r.numordped)}">${escapeHtml(r.numordped)}</td>
        <td title="${escapeHtml(r.num_days)}">${escapeHtml(r.num_days)}</td>
        <td title="${escapeHtml(r.area)}">${escapeHtml(areaShort)}</td>
        <td>${badgeForState(r.state)}</td>
      </tr>
    `;
  }).join("");

  return `
    <table class="kiosk-table">
      <thead>
        <tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function chunkIntoColumns(records, rowsPerCol) {
  const cols = [];
  const size = Math.max(1, Number(rowsPerCol) || 30);
  for (let i = 0; i < records.length; i += size) {
    cols.push(records.slice(i, i + size));
  }
  return cols.length ? cols : [[]];
}

function getDbParam() {
  const params = new URLSearchParams(window.location.search);
  return params.get("db");
}

async function fetchData() {
  const db = getDbParam();
  const limit = DEFAULT_LIMIT;

  const url = db
    ? `/kiosk/control_pedido/data?limit=${encodeURIComponent(limit)}&db=${encodeURIComponent(db)}`
    : `/kiosk/control_pedido/data?limit=${encodeURIComponent(limit)}`;

  const res = await fetch(url, { credentials: "same-origin" });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${txt.slice(0, 250)}`);
  }

  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (!ct.includes("application/json")) {
    const txt = await res.text();
    throw new Error(`Respuesta no JSON (CT=${ct}): ${txt.slice(0, 250)}`);
  }

  return await res.json();
}

// calcula cuántas filas caben
function computeRowsPerCol(gridEl) {
  gridEl.innerHTML = `
    <div class="kiosk-track" style="--visible-cols:${VISIBLE_COLS}; --gap:${GAP_PX}px;">
      <section class="kiosk-col">
        <table class="kiosk-table">
          <thead><tr><th>Fecha</th><th>Pedido</th><th>Días</th><th>Área</th><th>Estado</th></tr></thead>
          <tbody>
            <tr><td>01/01/26</td><td>123</td><td>1</td><td>TIN</td><td><span class="badge badge-on">On Time</span></td></tr>
            <tr><td>01/01/26</td><td>123</td><td>1</td><td>TEJ</td><td><span class="badge badge-de">Delayed</span></td></tr>
          </tbody>
        </table>
      </section>
      <section class="kiosk-col"></section>
      <section class="kiosk-col"></section>
      <section class="kiosk-col"></section>
      <section class="kiosk-col"></section>
    </div>
  `;

  const colEl = gridEl.querySelector(".kiosk-col");
  const theadEl = gridEl.querySelector(".kiosk-table thead");
  const trEl = gridEl.querySelector(".kiosk-table tbody tr");
  if (!colEl || !theadEl || !trEl) return 30;

  const colH = colEl.clientHeight;
  const headH = theadEl.offsetHeight;
  const rowH = trEl.offsetHeight || 18;

  const usable = Math.max(colH - headH - 8, 60);
  return Math.max(1, Math.floor(usable / rowH));
}

function renderTrack(gridEl) {
  const cols = state.columns;
  const total = cols.length || 1;

  const take = [];
  for (let i = 0; i < TRACK_COLS; i++) {
    const idx = (state.startCol + i) % total;
    take.push(cols[idx] || []);
  }

  gridEl.innerHTML = `
    <div class="kiosk-track" id="kiosk-track"
         style="--visible-cols:${VISIBLE_COLS}; --gap:${GAP_PX}px; transform: translateX(0px);">
      ${take.map(col => `<section class="kiosk-col">${buildTable(col)}</section>`).join("")}
    </div>
  `;
}

function getSlidePx() {
  const track = document.getElementById("kiosk-track");
  if (!track) return 0;

  const col = track.querySelector(".kiosk-col");
  if (!col) return 0;

  const styles = getComputedStyle(track);
  const gap = parseFloat(styles.gap || styles.columnGap || "0") || 0;

  return col.getBoundingClientRect().width + gap;
}

function startCarousel(gridEl) {
  stopCarousel();
  if (!state.columns || state.columns.length <= 1) return;

  state.slideTimer = setInterval(() => {
    if (state.sliding) return;
    state.sliding = true;

    const track = document.getElementById("kiosk-track");
    if (!track) {
      state.sliding = false;
      return;
    }

    const slidePx = getSlidePx();

    track.classList.add("is-sliding");
    requestAnimationFrame(() => {
      track.style.transform = `translateX(-${slidePx}px)`;
    });

    setTimeout(() => {
      state.startCol = (state.startCol + 1) % state.columns.length;

      renderTrack(gridEl);

      const newTrack = document.getElementById("kiosk-track");
      if (newTrack) {
        newTrack.classList.remove("is-sliding");
        newTrack.style.transform = "translateX(0px)";
        void newTrack.offsetWidth;
      }

      state.sliding = false;
    }, 720);
  }, SLIDE_MS);
}

function stopCarousel() {
  if (state.slideTimer) clearInterval(state.slideTimer);
  state.slideTimer = null;
}

async function loadAndStart() {
  const grid = document.getElementById("kiosk-grid");
  if (!grid) return;

  let payload;
  try {
    payload = await fetchData();
  } catch (e) {
    grid.innerHTML = `<div class="kiosk-error">Error cargando data: ${escapeHtml(e.message || e)}</div>`;
    return;
  }

  const records = payload.records || [];
  const count = payload.count ?? records.length ?? 0;

  const countEl = document.getElementById("kiosk-count");
  const lastEl = document.getElementById("kiosk-last");
  if (countEl) countEl.textContent = String(count);
  if (lastEl) lastEl.textContent = fmtNow();

  state.records = records;

  const rowsPerCol = computeRowsPerCol(grid);
  state.rowsPerCol = rowsPerCol;

  state.columns = chunkIntoColumns(records, rowsPerCol);
  state.startCol = 0;

  renderTrack(grid);
  startCarousel(grid);
}

function boot() {
  loadAndStart();

  if (state.refreshTimer) clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(() => loadAndStart(), REFRESH_MS);

  window.addEventListener("resize", () => loadAndStart());
}

document.addEventListener("DOMContentLoaded", boot);
