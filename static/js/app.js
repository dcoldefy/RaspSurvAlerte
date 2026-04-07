/* ── RaspSurAlert — app.js ──────────────────────────────────────── */

'use strict';

/* ── Tri colonnes ─────────────────────────────────────────────────── */

const SORT = { col: null, dir: 1 }; // dir : 1=asc, -1=desc

const NUM_COLS = new Set(['altitude_m', 'vitesse_kmh', 'cap_deg']);

function sortRows(rows) {
  if (!SORT.col) return rows;
  const col = SORT.col;
  return [...rows].sort((a, b) => {
    let va = a[col], vb = b[col];
    if (col === 'date') {
      // DD/MM/YYYY → YYYYMMDD pour tri correct
      const toISO = s => s ? s.split('/').reverse().join('') : '';
      va = toISO(va); vb = toISO(vb);
    }
    if (NUM_COLS.has(col)) {
      va = va ?? -Infinity; vb = vb ?? -Infinity;
      return SORT.dir * (va - vb);
    }
    va = (va ?? '').toString().toLowerCase();
    vb = (vb ?? '').toString().toLowerCase();
    return SORT.dir * va.localeCompare(vb, 'fr');
  });
}

function updateSortHeaders() {
  document.querySelectorAll('.col-sortable').forEach(th => {
    const col = th.dataset.col;
    th.classList.toggle('sort-active', col === SORT.col);
    const existing = th.querySelector('.sort-arrow');
    if (existing) existing.remove();
    if (col === SORT.col) {
      const small = document.createElement('small');
      small.className = 'sort-arrow d-block text-muted';
      small.style.fontSize = '0.65em';
      small.style.lineHeight = '1';
      small.textContent = SORT.dir === 1 ? '▲ asc' : '▼ desc';
      th.appendChild(small);
    }
  });
}

function updateStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      const dot  = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      if (!dot || !text) return;
      dot.className    = 'status-dot ' + (data.status_ok ? 'status-ok' : 'status-err');
      text.textContent = data.status;
    })
    .catch(() => {
      const dot = document.getElementById('status-dot');
      if (dot) dot.className = 'status-dot status-err';
    });
}

function updateTable() {
  const tbody  = document.getElementById('table-body');
  const sTotal = document.getElementById('s-total');
  const sInfr  = document.getElementById('s-infr');
  const sLast  = document.getElementById('s-last');
  if (!tbody) return;

  const activeFilter = (window.RASPALERT && window.RASPALERT.activeFilter) || 'tous';

  fetch('/api/survols')
    .then(r => r.json())
    .then(rows => {
      const nAlt    = rows.filter(r => r.code === 'ALT').length;
      const nNuit   = rows.filter(r => r.code === 'NUIT').length;
      const nDouble = rows.filter(r => r.code === 'ALT+NUIT').length;
      const nInfr   = nAlt + nNuit + nDouble;

      if (sTotal) sTotal.textContent = rows.length;
      if (sInfr)  sInfr.textContent  = nInfr;
      if (sLast && rows.length > 0)
        sLast.textContent = rows[rows.length - 1].indicatif || '—';

      const bdTous   = document.getElementById('badge-tous');
      const bdAlt    = document.getElementById('badge-alt');
      const bdNuit   = document.getElementById('badge-nuit');
      const bdDouble = document.getElementById('badge-double');
      if (bdTous)   bdTous.textContent   = rows.length;
      if (bdAlt)    bdAlt.textContent    = nAlt + nDouble;
      if (bdNuit)   bdNuit.textContent   = nNuit;
      if (bdDouble) bdDouble.textContent = nDouble;

      const filtered = sortRows(activeFilter === 'tous'
        ? rows
        : rows.filter(r => {
            if (activeFilter === 'ALT')      return r.code === 'ALT' || r.code === 'ALT+NUIT';
            if (activeFilter === 'NUIT')     return r.code === 'NUIT';
            if (activeFilter === 'ALT+NUIT') return r.code === 'ALT+NUIT';
            return true;
          }));

      if (filtered.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="9" class="text-center text-muted py-5">
              <i class="bi bi-radar fs-2 d-block mb-2 opacity-25"></i>
              Aucun vol correspondant au filtre actuel
            </td>
          </tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(r => {
        const infrText = r.infraction
          ? `<span class="infr-text small ms-1" title="${escHtml(r.infraction)}">
               ${escHtml(r.infraction.substring(0, 60))}${r.infraction.length > 60 ? '…' : ''}
             </span>`
          : '';
        return `
          <tr class="${escHtml(r.css_class)}" data-code="${escHtml(r.code)}">
            <td class="text-nowrap text-muted small">${escHtml(r.date)}</td>
            <td class="text-nowrap fw-semibold">${escHtml(r.heure)}</td>
            <td class="fw-bold font-mono">${escHtml(r.indicatif)}</td>
            <td class="text-muted small font-mono">${escHtml(r.icao24)}</td>
            <td class="text-end">${fmtAlt(r.altitude_m)}</td>
            <td class="text-end">${fmtVal(r.vitesse_kmh, ' km/h')}</td>
            <td class="text-end">${fmtVal(r.cap_deg, '°')}</td>
            <td class="small">${escHtml(r.pays || '—')}</td>
            <td>${r.badge}${infrText}</td>
          </tr>`;
      }).join('');

      const hint = document.getElementById('refresh-hint');
      if (hint) {
        const now = new Date();
        hint.innerHTML = `<i class="bi bi-check-circle text-success me-1"></i>
          Actualisé à ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      }
    })
    .catch(() => {
      const hint = document.getElementById('refresh-hint');
      if (hint) hint.innerHTML = '<i class="bi bi-wifi-off text-danger me-1"></i>Erreur réseau';
    });
}

function escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtAlt(v) {
  return v != null ? v.toLocaleString('fr-FR') + '\u202fm' : '—';
}

function fmtVal(v, suffix) {
  return v != null ? v + suffix : '—';
}

function pad(n) {
  return String(n).padStart(2, '0');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.btn-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      window.RASPALERT = window.RASPALERT || {};
      window.RASPALERT.activeFilter = btn.dataset.filter;
      updateTable();
    });
  });

  document.querySelectorAll('.col-sortable').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      if (SORT.col === th.dataset.col) {
        SORT.dir *= -1;
      } else {
        SORT.col = th.dataset.col;
        SORT.dir = 1;
      }
      updateSortHeaders();
      updateTable();
    });
  });

  updateStatus();
  updateTable();

  setInterval(updateStatus, 15000);
  setInterval(updateTable,  30000);
});
