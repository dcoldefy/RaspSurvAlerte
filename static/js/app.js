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
      dot.className = 'status-dot ' + dotClass;
      const sourceLabel = data.source === 'opensky' ? 'OpenSky' : 'FlightRadar24';
      text.textContent = sourceLabel;
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
      if (bdAlt)    bdAlt.textContent    = nAlt;
      if (bdNuit)   bdNuit.textContent   = nNuit;
      if (bdDouble) bdDouble.textContent = nDouble;

      const filtered = sortRows(activeFilter === 'tous'
        ? rows
        : rows.filter(r => {
            if (activeFilter === 'ALT')      return r.code === 'ALT';
            if (activeFilter === 'NUIT')     return r.code === 'NUIT';
            if (activeFilter === 'ALT+NUIT') return r.code === 'ALT+NUIT';
            return true;
          }));

      // Pré-passe : totaux par jour (rows triées du plus récent au plus ancien)
      const dayTotal = {}, dayInfrTotal = {};
      rows.forEach(r => {
        dayTotal[r.date] = (dayTotal[r.date] || 0) + 1;
        if (r.code) dayInfrTotal[r.date] = (dayInfrTotal[r.date] || 0) + 1;
      });
      // Rang chronologique : rang = total - position_depuis_le_haut + 1
      const dayCur = {}, dayInfrCur = {};
      rows.forEach(r => {
        dayCur[r.date] = (dayCur[r.date] || 0) + 1;
        if (r.code) dayInfrCur[r.date] = (dayInfrCur[r.date] || 0) + 1;
        r._rank     = dayTotal[r.date] - dayCur[r.date] + 1;
        r._rankInfr = r.code ? dayInfrTotal[r.date] - dayInfrCur[r.date] + 1 : 0;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="12" class="text-center text-muted py-5">
              <i class="bi bi-radar fs-2 d-block mb-2 opacity-25"></i>
              Aucun vol correspondant au filtre actuel
            </td>
          </tr>`;
        return;
      }

      tbody.innerHTML = filtered.map(r => {
        const dcHtml  = r._rankInfr > 0
          ? `${r._rank}<br><span class="text-danger fw-semibold">${r._rankInfr}</span>`
          : `${r._rank}`;
        // [TEST] colonne taux vertical
        const tm = r.taux_montee;
        const tmHtml = tm == null ? '—'
          : tm > 0  ? `<span class="text-success">↑ ${tm}</span>`
          : tm < 0  ? `<span class="text-danger">↓ ${Math.abs(tm)}</span>`
          : '→ 0';
        const tmClass = tm == null ? '' : tm > 0 ? ' row-montee' : tm < 0 ? ' row-descente' : '';
        return `
          <tr class="${escHtml(r.css_class)}${tmClass}" data-code="${escHtml(r.code)}"
              data-date="${escHtml(r.date)}" data-heure="${escHtml(r.heure)}"
              data-indicatif="${escHtml(r.indicatif)}" data-icao24="${escHtml(r.icao24)}"
              data-altitude="${r.altitude_m != null ? r.altitude_m : ''}">
            <td class="text-nowrap text-muted small">${escHtml(r.date)}</td>
            <td class="text-nowrap fw-semibold">${escHtml(r.heure)}</td>
            <td class="fw-bold font-mono">${escHtml(r.indicatif)}</td>
            <td class="text-muted small font-mono">${escHtml(r.icao24)}</td>
            <td class="text-end">${fmtAlt(r.altitude_m)}</td>
            <td class="text-end">${fmtDist(r.distance_km)}</td>
            <td class="text-center small">${tmHtml}</td>
            <td class="text-center small">${dcHtml}</td>
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

let ctxMenu      = null;
let modalEl      = null;
let ctxVolData   = null;
let destinataires    = [];  // chargés au démarrage
let selectedDestId   = '';
let pleinteMode      = 'courrier';  // 'courrier' | 'email'

function hideCtxMenu() {
  if (ctxMenu) ctxMenu.style.display = 'none';
}

function showCtxMenu(e, tr) {
  if (!ctxMenu) return;
  const code   = tr.dataset.code || '';
  const altRaw = tr.dataset.altitude;
  ctxVolData = {
    date:       tr.dataset.date      || '',
    heure:      tr.dataset.heure     || '',
    indicatif:  tr.dataset.indicatif || '',
    icao24:     tr.dataset.icao24    || '',
    code:       code,
    altitude_m: altRaw !== '' && altRaw != null ? parseFloat(altRaw) : null,
  };

  document.getElementById('ctx-vol-ref').textContent =
    ctxVolData.indicatif || ctxVolData.icao24 || '—';

  const hasCourrier = destinataires.some(d => d.adresse && d.adresse.trim());
  const hasEmail    = destinataires.some(d => d.email   && d.email.trim());
  const ctxCourrier = document.getElementById('ctx-plainte-courrier');
  const ctxEmail    = document.getElementById('ctx-plainte-email');
  const ctxSep      = ctxMenu.querySelector('.ctx-sep');
  if (ctxCourrier) ctxCourrier.style.display = (code && hasCourrier) ? '' : 'none';
  if (ctxEmail)    ctxEmail.style.display    = (code && hasEmail)    ? '' : 'none';
  if (ctxSep)      ctxSep.style.display      = (code && (hasCourrier || hasEmail)) ? '' : 'none';

  const x = Math.min(e.clientX, window.innerWidth  - 240);
  const y = Math.min(e.clientY, window.innerHeight - 120);
  ctxMenu.style.left    = x + 'px';
  ctxMenu.style.top     = y + 'px';
  ctxMenu.style.display = 'block';
  e.preventDefault();
}

function ouvrirModalPlainte(mode) {
  pleinteMode = mode;
  const filtered = mode === 'email'
    ? destinataires.filter(d => d.email   && d.email.trim())
    : destinataires.filter(d => d.adresse && d.adresse.trim());
  selectedDestId = filtered.length ? filtered[0].id : '';

  const title = document.getElementById('modal-plainte-title');
  const btn   = document.getElementById('btn-gen-plainte');
  if (mode === 'email') {
    if (title) title.innerHTML = '<i class="bi bi-envelope-fill me-2"></i>Plainte par email';
    if (btn)   btn.innerHTML   = '<i class="bi bi-send me-1"></i>Ouvrir dans ma messagerie';
  } else {
    if (title) title.innerHTML = '<i class="bi bi-envelope-paper-fill me-2"></i>Plainte par courrier';
    if (btn)   btn.innerHTML   = '<i class="bi bi-download me-1"></i>Télécharger le PDF';
  }

  renderDestinataireRadios(filtered);
  new bootstrap.Modal(modalEl).show();
}

function renderDestinataireRadios(list) {
  const container = document.getElementById('dest-radio-list');
  if (!container) return;
  if (!list || !list.length) {
    container.innerHTML =
      '<div class="text-muted small fst-italic">Aucun destinataire configuré — ajoutez-en dans les Réglages.</div>';
    updateDestApercu(list || []);
    return;
  }
  container.innerHTML = list.map(d => `
    <div class="form-check mb-2">
      <input class="form-check-input" type="radio" name="dest-radio"
             id="dest-${d.id}" value="${escHtml(d.id)}" ${d.id === selectedDestId ? 'checked' : ''}>
      <label class="form-check-label" for="dest-${d.id}">
        <span class="fw-semibold">${escHtml(d.label)}</span><br>
        <span class="text-muted small">${escHtml(d.nom)}</span>
      </label>
    </div>`).join('');

  container.querySelectorAll('input[name="dest-radio"]').forEach(rb => {
    rb.addEventListener('change', () => {
      selectedDestId = rb.value;
      updateDestApercu(list);
    });
  });
  updateDestApercu(list);
}

function updateDestApercu(list) {
  const apercu = document.getElementById('dest-apercu');
  if (!apercu) return;
  const d = (list || destinataires).find(x => x.id === selectedDestId);
  if (!d) { apercu.style.display = 'none'; return; }
  if (pleinteMode === 'email') {
    apercu.textContent = d.email || '';
  } else {
    const addrLine = d.adresse ? '  ·  ' + d.adresse.replace('\n', ', ') : '';
    apercu.textContent = d.nom + addrLine;
  }
  apercu.style.display = 'block';
}

function genererPlainte() {
  if (!ctxVolData) return;
  const btn = document.getElementById('btn-gen-plainte');
  btn.disabled = true;

  if (pleinteMode === 'email') {
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Préparation…';
    fetch('/api/plainte/email', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ vol: ctxVolData, destinataire_id: selectedDestId }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(j => { throw new Error(j.error || 'Erreur serveur'); });
        return r.json();
      })
      .then(({ to, subject, body }) => {
        const mailto = `mailto:${encodeURIComponent(to)}`
          + `?subject=${encodeURIComponent(subject)}`
          + `&body=${encodeURIComponent(body)}`;
        window.location.href = mailto;
        bootstrap.Modal.getInstance(modalEl)?.hide();
      })
      .catch(err => alert('Erreur : ' + err.message))
      .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-send me-1"></i>Ouvrir dans ma messagerie';
      });

  } else {
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Génération…';
    fetch('/api/plainte', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ vol: ctxVolData, destinataire_id: selectedDestId }),
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
      .catch(err => alert('Erreur : ' + err.message))
      .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-download me-1"></i>Télécharger le PDF';
      });
  }
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

    document.getElementById('ctx-plainte-courrier')?.addEventListener('click', () => {
      hideCtxMenu();
      ouvrirModalPlainte('courrier');
    });

    document.getElementById('ctx-plainte-email')?.addEventListener('click', () => {
      hideCtxMenu();
      ouvrirModalPlainte('email');
    });
  }

  if (modalEl) {
    document.getElementById('btn-gen-plainte')?.addEventListener('click', genererPlainte);
  }

  // Pré-chargement des destinataires pour le menu contextuel
  fetch('/api/destinataires')
    .then(r => r.json())
    .then(data => { destinataires = data; })
    .catch(() => {});

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
