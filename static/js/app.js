/* ── RaspSurAlert — app.js ──────────────────────────────────────── */

'use strict';

/* ── Tri colonnes ─────────────────────────────────────────────────── */

const SORT = { col: 'heure', dir: -1 }; // dir : 1=asc, -1=desc — défaut : plus récent en premier

const NUM_COLS = new Set(['altitude_m', 'distance_km', 'vitesse_kmh', 'cap_deg']);

function sortRows(rows) {
  if (!SORT.col) return rows;
  const col = SORT.col;
  return [...rows].sort((a, b) => {
    let va = a[col], vb = b[col];
    if (col === 'date' || col === 'heure') {
      // DD/MM/YYYY → YYYYMMDD ; pour heure, on combine date+heure pour éviter le mélange inter-jours
      const toISO = s => s ? s.split('/').reverse().join('') : '';
      va = toISO(a.date) + (a.heure || '');
      vb = toISO(b.date) + (b.heure || '');
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
    if (col === SORT.col) {
      th.dataset.arrow = SORT.dir === 1 ? '▲' : '▼';
    } else {
      delete th.dataset.arrow;
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
      let dotClass = 'status-ok';
      if (!data.status_ok) {
        dotClass = data.last_error_type === 'rate_limit' ? 'status-warn' : 'status-err';
      }
      dot.className    = 'status-dot ' + dotClass;
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
        sLast.textContent = rows[0].indicatif || '—';

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
            <td colspan="10" class="text-center text-muted py-5">
              <i class="bi bi-radar fs-2 d-block mb-2 opacity-25"></i>
              Aucun vol correspondant au filtre actuel
            </td>
          </tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(r => {
        return `
          <tr class="${escHtml(r.css_class)}" data-code="${escHtml(r.code)}"
              data-date="${escHtml(r.date)}" data-heure="${escHtml(r.heure)}"
              data-indicatif="${escHtml(r.indicatif)}" data-icao24="${escHtml(r.icao24)}">
            <td class="text-nowrap text-muted small">${escHtml(r.date)}</td>
            <td class="text-nowrap fw-semibold">${escHtml(r.heure)}</td>
            <td class="fw-bold font-mono">${escHtml(r.indicatif)}</td>
            <td class="text-muted small font-mono">${escHtml(r.icao24)}</td>
            <td class="text-end">${fmtAlt(r.altitude_m)}</td>
            <td class="text-end">${fmtDist(r.distance_km)}</td>
            <td class="text-end">${fmtVal(r.vitesse_kmh, ' km/h')}</td>
            <td class="text-end">${fmtVal(r.cap_deg, '°')}</td>
            <td class="small">${escHtml(r.pays || '—')}</td>
            <td>${r.badge}${buildInfrDetail(r)}</td>
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

function buildInfrDetail(r) {
  if (!r.code) return '';
  const parts = [];
  if (r.code === 'ALT' || r.code === 'ALT+NUIT') {
    parts.push(r.altitude_m != null ? fmtAlt(r.altitude_m) : '—');
  }
  if (r.code === 'NUIT' || r.code === 'ALT+NUIT') {
    parts.push(r.heure ? r.heure.substring(0, 5) : '—');
  }
  return parts.length
    ? ` <span class="infr-vals">${parts.join(' · ')}</span>`
    : '';
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

function fmtDist(v) {
  return v != null ? v.toLocaleString('fr-FR') + '\u202fkm' : '—';
}

function fmtVal(v, suffix) {
  return v != null ? v + suffix : '—';
}

function pad(n) {
  return String(n).padStart(2, '0');
}

/* ── Menu contextuel (clic droit) ─────────────────────────────────────── */

let ctxMenu    = null;
let modalEl    = null;
let ctxVolData = null;   // données du vol en cours
let destinataires = [];  // liste chargée depuis l'API
let selectedDest  = 0;

function hideCtxMenu() {
  if (ctxMenu) ctxMenu.style.display = 'none';
}

function showCtxMenu(e, tr) {
  if (!ctxMenu) return;
  const code = tr.dataset.code || '';

  ctxVolData = {
    date:      tr.dataset.date      || '',
    heure:     tr.dataset.heure     || '',
    indicatif: tr.dataset.indicatif || '',
    icao24:    tr.dataset.icao24    || '',
  };

  const ref = ctxVolData.indicatif || ctxVolData.icao24 || '—';
  document.getElementById('ctx-vol-ref').textContent = ref;

  // Afficher/masquer l'option Plainte selon infraction
  const ctxPlainte = document.getElementById('ctx-plainte');
  const ctxSep     = ctxMenu.querySelector('.ctx-sep');
  if (ctxPlainte) ctxPlainte.style.display = code ? '' : 'none';
  if (ctxSep)     ctxSep.style.display     = code ? '' : 'none';

  // Positionner le menu
  const x = Math.min(e.clientX, window.innerWidth  - 240);
  const y = Math.min(e.clientY, window.innerHeight - 120);
  ctxMenu.style.left    = x + 'px';
  ctxMenu.style.top     = y + 'px';
  ctxMenu.style.display = 'block';
  e.preventDefault();
}

function loadDestinataireList() {
  fetch('/api/destinataires')
    .then(r => r.json())
    .then(data => {
      destinataires = data;
      renderDestinataireRadios();
    })
    .catch(() => {
      document.getElementById('dest-radio-list').innerHTML =
        '<div class="text-danger small">Erreur de chargement.</div>';
    });
}

function renderDestinataireRadios() {
  const container = document.getElementById('dest-radio-list');
  if (!container) return;
  container.innerHTML = destinataires.map((d, i) => `
    <div class="form-check mb-2">
      <input class="form-check-input" type="radio" name="dest-radio"
             id="dest-${i}" value="${i}" ${i === selectedDest ? 'checked' : ''}>
      <label class="form-check-label" for="dest-${i}">
        <span class="fw-semibold">${escHtml(d.label)}</span><br>
        <span class="text-muted small">${escHtml(d.nom)} — ${escHtml(d.cp_ville)}</span>
      </label>
    </div>`).join('');

  container.querySelectorAll('input[name="dest-radio"]').forEach(rb => {
    rb.addEventListener('change', () => {
      selectedDest = parseInt(rb.value, 10);
      updateDestApercu();
    });
  });
  updateDestApercu();
}

function updateDestApercu() {
  const apercu = document.getElementById('dest-apercu');
  if (!apercu || !destinataires[selectedDest]) return;
  const d = destinataires[selectedDest];
  apercu.textContent = `${d.nom}  ·  ${d.adresse}  ·  ${d.cp_ville}`;
  apercu.style.display = 'block';
}

function genererPlainte() {
  if (!ctxVolData) return;
  const btn = document.getElementById('btn-gen-plainte');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Génération…';

  fetch('/api/plainte', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ vol: ctxVolData, destinataire_idx: selectedDest }),
  })
    .then(r => {
      if (!r.ok) return r.json().then(j => { throw new Error(j.error || 'Erreur serveur'); });
      return r.blob();
    })
    .then(blob => {
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      const ref  = (ctxVolData.indicatif || ctxVolData.icao24 || 'plainte').trim();
      const date = (ctxVolData.date || '').replace(/\//g, '');
      a.href     = url;
      a.download = `Plainte_${ref}_${date}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      bootstrap.Modal.getInstance(modalEl)?.hide();
    })
    .catch(err => {
      alert('Erreur : ' + err.message);
    })
    .finally(() => {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-download me-1"></i>Télécharger le PDF';
    });
}

document.addEventListener('DOMContentLoaded', () => {
  ctxMenu = document.getElementById('ctx-menu');
  modalEl = document.getElementById('modal-destinataire');

  // Initialisation menu contextuel
  if (ctxMenu) {
    document.addEventListener('click', hideCtxMenu);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCtxMenu(); });

    document.getElementById('ctx-fr24')?.addEventListener('click', () => {
      if (!ctxVolData) return;
      hideCtxMenu();
      const indicatif = ctxVolData.indicatif?.trim();
      const icao24    = ctxVolData.icao24?.trim().toLowerCase();
      let url;
      if (indicatif && indicatif !== '-') {
        url = `https://www.flightradar24.com/${encodeURIComponent(indicatif)}`;
      } else if (icao24) {
        url = `https://www.flightradar24.com/data/aircraft/${encodeURIComponent(icao24)}`;
      } else {
        url = 'https://www.flightradar24.com/';
      }
      window.open(url, '_blank', 'noopener');
    });

    document.getElementById('ctx-plainte')?.addEventListener('click', () => {
      hideCtxMenu();
      loadDestinataireList();
      new bootstrap.Modal(modalEl).show();
    });
  }

  if (modalEl) {
    document.getElementById('btn-gen-plainte')?.addEventListener('click', genererPlainte);
  }

  // Délégation clic droit sur le tbody (toutes les lignes de vol)
  document.getElementById('table-body')?.addEventListener('contextmenu', e => {
    const tr = e.target.closest('tr[data-date]');
    if (tr) showCtxMenu(e, tr);
  });

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

  // SSE — mise à jour instantanée dès qu'un scan se termine
  const evtSource = new EventSource('/api/stream');
  evtSource.onmessage = e => {
    if (e.data === 'update') {
      updateTable();
      updateStatus();
    }
  };
  // Fallback polling en cas de coupure SSE
  evtSource.onerror = () => {
    evtSource.close();
    setInterval(updateStatus, 15000);
    setInterval(updateTable,  30000);
  };

  // Keepalive status toutes les 15s (SSE ne couvre pas le statut du scanner)
  setInterval(updateStatus, 15000);
});
