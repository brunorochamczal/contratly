// ═══════════════════════════════════════════
//  STATE & CONFIG
// ═══════════════════════════════════════════
const API = window.location.origin + '/api';
let token = localStorage.getItem('token');
let currentUser = null;
let contracts = [];
let users = [];
let charts = {};
let selectedDecision = 'renew';

// ═══════════════════════════════════════════
//  API HELPERS
// ═══════════════════════════════════════════
async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(API + path, {
    method, headers,
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Erro na requisição');
  return data;
}

const get = (p) => api('GET', p);
const post = (p, b) => api('POST', p, b);
const put = (p, b) => api('PUT', p, b);
const del = (p) => api('DELETE', p);

// ═══════════════════════════════════════════
//  AUTH
// ═══════════════════════════════════════════
async function doLogin() {
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('login-btn-text');
  const err = document.getElementById('login-error');

  btn.innerHTML = '<span class="spinner"></span>';
  err.style.display = 'none';

  try {
    const data = await post('/auth/login', { email, password });
    token = data.token;
    currentUser = data.user;
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(currentUser));
    initApp();
  } catch (e) {
    err.textContent = e.message;
    err.style.display = 'block';
    btn.textContent = 'Entrar';
  }
}

function doLogout() {
  token = null;
  currentUser = null;
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  document.getElementById('app').classList.remove('visible');
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('login-btn-text').textContent = 'Entrar';
}

async function initApp() {
  try {
    if (!currentUser && token) {
      currentUser = await get('/auth/me');
    }
  } catch { doLogout(); return; }

  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').classList.add('visible');

  // Setup sidebar
  const av = document.getElementById('sidebar-avatar');
  av.textContent = currentUser.name.charAt(0).toUpperCase();
  document.getElementById('sidebar-username').textContent = currentUser.name;
  document.getElementById('sidebar-role').textContent = currentUser.role;

  // Admin sections
  if (currentUser.role === 'admin') {
    document.getElementById('admin-section').style.display = 'block';
    document.getElementById('nav-users').style.display = currentUser.role === 'admin' ? 'flex' : 'none';
    document.getElementById('nav-audit').style.display = 'flex';
  }

  // Load initial data
  await loadUsers();
  loadDashboard();
}

// ═══════════════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════════════
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const page = document.getElementById(`page-${name}`);
  if (page) page.classList.add('active');

  const nav = document.querySelector(`[data-page="${name}"]`);
  if (nav) nav.classList.add('active');

  const loaders = {
    dashboard: loadDashboard,
    contracts: loadContracts,
    alerts: loadAlerts,
    renewals: loadRenewals,
    users: loadUsers,
    audit: loadAudit,
    reports: () => {},
  };
  if (loaders[name]) loaders[name]();
}

// ═══════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════
async function loadDashboard() {
  try {
    const data = await get('/dashboard');
    const s = data.stats;

    document.getElementById('stat-total').textContent = s.total;
    document.getElementById('stat-critical').textContent = s.critical;
    document.getElementById('stat-alerts').textContent = s.pending_alerts;
    document.getElementById('stat-monthly').textContent = formatMoney(s.monthly_value);

    // Update badges
    if (s.pending_alerts > 0) {
      const b = document.getElementById('badge-alerts');
      b.textContent = s.pending_alerts;
      b.style.display = 'inline-block';
    }

    // Critical contracts table
    const tbody = document.getElementById('critical-table-body');
    if (data.critical_contracts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-muted)">
        <div>✅ Nenhum contrato crítico no momento</div>
      </td></tr>`;
    } else {
      tbody.innerHTML = data.critical_contracts.map(c => `
        <tr class="${c.urgency === 'critical' ? 'critical-row' : ''}" onclick="openContractDetail('${c.id}')">
          <td><span class="text-mono" style="color:var(--accent);font-size:12px">${c.code}</span></td>
          <td><strong>${c.title}</strong></td>
          <td>${c.counterparty_name}</td>
          <td class="text-mono">${formatDate(c.end_date)}</td>
          <td><span class="urgency-${c.urgency}">${c.days_until_expiry}d</span></td>
          <td class="money">${c.value_monthly ? formatMoney(c.value_monthly) + '/mês' : '—'}</td>
          <td>${statusBadge(c.status)}</td>
        </tr>
      `).join('');
    }

    // Charts
    renderTimelineChart(data.monthly_expirations);
    renderTypesChart(data.by_type);

  } catch (e) { showToast(e.message, 'error'); }
}

function renderTimelineChart(data) {
  const ctx = document.getElementById('chart-timeline').getContext('2d');
  if (charts.timeline) charts.timeline.destroy();

  const today = new Date();
  const colors = data.map((_, i) => {
    if (i === 0) return 'rgba(239,68,68,0.8)';
    if (i <= 1) return 'rgba(249,115,22,0.7)';
    if (i <= 2) return 'rgba(234,179,8,0.6)';
    return 'rgba(37,99,235,0.5)';
  });

  charts.timeline = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: 'Contratos',
        data: data.map(d => d.count),
        backgroundColor: colors,
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        backgroundColor: '#111827', borderColor: '#1e2d3d', borderWidth: 1,
        titleColor: '#f0f6fc', bodyColor: '#8b949e',
      }},
      scales: {
        x: { grid: { color: 'rgba(30,45,61,0.5)' }, ticks: { color: '#8b949e', font: { size: 11 } } },
        y: { grid: { color: 'rgba(30,45,61,0.5)' }, ticks: { color: '#8b949e', stepSize: 1 } }
      }
    }
  });
}

function renderTypesChart(data) {
  const ctx = document.getElementById('chart-types').getContext('2d');
  if (charts.types) charts.types.destroy();

  const typeLabels = {
    service: 'Serviços', supply: 'Fornecimento', lease: 'Locação',
    nda: 'NDA', sla: 'SLA', partnership: 'Parceria', other: 'Outro'
  };
  const palette = ['#2563eb','#7c3aed','#db2777','#ea580c','#16a34a','#0891b2','#78716c'];

  charts.types = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: data.map(d => typeLabels[d.type] || d.type),
      datasets: [{
        data: data.map(d => d.count),
        backgroundColor: palette,
        borderColor: '#111827',
        borderWidth: 2,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8b949e', font: { size: 11 }, padding: 10, boxWidth: 10 } },
        tooltip: { backgroundColor: '#111827', borderColor: '#1e2d3d', borderWidth: 1, titleColor: '#f0f6fc', bodyColor: '#8b949e' }
      }
    }
  });
}

// ═══════════════════════════════════════════
//  CONTRACTS
// ═══════════════════════════════════════════
async function loadContracts() {
  const search = document.getElementById('search-input')?.value || '';
  const status = document.getElementById('filter-status')?.value || '';
  const type = document.getElementById('filter-type')?.value || '';
  const sort = document.getElementById('filter-sort')?.value || 'end_date';

  let qs = `?sort=${sort}`;
  if (search) qs += `&search=${encodeURIComponent(search)}`;
  if (status) qs += `&status=${status}`;
  if (type) qs += `&type=${type}`;

  try {
    const data = await get(`/contracts${qs}`);
    contracts = data.contracts;
    document.getElementById('contracts-count').textContent =
      `${data.total} contratos encontrados`;

    renderContractsTable(contracts);
  } catch (e) { showToast(e.message, 'error'); }
}

let filterTimer;
function filterContracts() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(loadContracts, 300);
}

function renderContractsTable(list) {
  const tbody = document.getElementById('contracts-table-body');
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="10"><div class="empty-state">
      <div class="empty-icon">📄</div>
      <h3>Nenhum contrato encontrado</h3>
      <p>Tente ajustar os filtros ou crie um novo contrato.</p>
    </div></td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(c => `
    <tr onclick="openContractDetail('${c.id}')">
      <td><span class="text-mono" style="color:var(--accent);font-size:11px">${c.code}</span></td>
      <td>
        <div style="font-weight:500;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.title}</div>
        ${c.is_confidential ? '<span style="font-size:10px;color:var(--orange)">🔒 Confidencial</span>' : ''}
      </td>
      <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.counterparty_name}</td>
      <td><span class="badge badge-type">${typeLabel(c.contract_type)}</span></td>
      <td class="text-mono">${c.end_date ? formatDate(c.end_date) : '—'}</td>
      <td><span class="urgency-${c.urgency}">${
        c.days_until_expiry !== null ?
          (c.days_until_expiry < 0 ? `${Math.abs(c.days_until_expiry)}d vencido` : `${c.days_until_expiry}d`)
          : '—'
      }</span></td>
      <td class="money">${c.value_monthly ? formatMoney(c.value_monthly) : '—'}</td>
      <td>${statusBadge(c.status)}</td>
      <td>${(c.tags||[]).map(t => `<span class="tag" style="background:${t.color}22;color:${t.color}">${t.name}</span>`).join('')}</td>
      <td>
        <button class="btn btn-ghost btn-sm btn-icon" onclick="event.stopPropagation();openEditContract('${c.id}')">✏️</button>
      </td>
    </tr>
  `).join('');
}

async function openContractDetail(id) {
  try {
    const c = await get(`/contracts/${id}`);
    document.getElementById('detail-title').textContent = c.title;
    document.getElementById('detail-code').textContent = c.code;

    const body = document.getElementById('detail-body');
    const days = c.days_until_expiry;
    const daysText = days !== null ? (days < 0 ? `${Math.abs(days)} dias vencido` : `${days} dias`) : '—';

    body.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;">
        ${statusBadge(c.status)}
        <span class="badge badge-type">${typeLabel(c.contract_type)}</span>
        ${c.is_confidential ? '<span class="badge" style="background:var(--orange-bg);color:var(--orange)">🔒 Confidencial</span>' : ''}
        ${(c.tags||[]).map(t => `<span class="tag" style="background:${t.color}22;color:${t.color}">${t.name}</span>`).join('')}
      </div>

      <div class="detail-grid">
        <div class="detail-field"><div class="detail-label">Contraparte</div><div class="detail-value">${c.counterparty_name}</div></div>
        <div class="detail-field"><div class="detail-label">CNPJ/CPF</div><div class="detail-value">${c.counterparty_doc || '—'}</div></div>
        <div class="detail-field"><div class="detail-label">Vigência</div><div class="detail-value">${formatDate(c.start_date)} → ${c.end_date ? formatDate(c.end_date) : 'Indeterminado'}</div></div>
        <div class="detail-field"><div class="detail-label">Dias Restantes</div><div class="detail-value urgency-${c.urgency}" style="font-weight:700;font-size:18px">${daysText}</div></div>
        <div class="detail-field"><div class="detail-label">Valor Total</div><div class="detail-value money">${c.value_total ? formatMoney(c.value_total) : '—'}</div></div>
        <div class="detail-field"><div class="detail-label">Valor Mensal</div><div class="detail-value money large">${c.value_monthly ? formatMoney(c.value_monthly) : '—'}</div></div>
        <div class="detail-field"><div class="detail-label">Renovação</div><div class="detail-value">${renewalLabel(c.renewal_type)} · ${c.renewal_notice_days}d aviso</div></div>
        <div class="detail-field"><div class="detail-label">Responsável</div><div class="detail-value">${c.responsible?.name || '—'}</div></div>
        <div class="detail-field"><div class="detail-label">Departamento</div><div class="detail-value">${c.department || '—'}</div></div>
        <div class="detail-field"><div class="detail-label">E-mail Contraparte</div><div class="detail-value">${c.counterparty_email || '—'}</div></div>
      </div>

      ${c.description ? `<div class="form-section-title">Descrição / Objeto</div><p style="color:var(--text-secondary);font-size:13px;margin-bottom:20px;line-height:1.6">${c.description}</p>` : ''}

      <div class="form-section-title">Alertas Configurados (${(c.alerts||[]).length})</div>
      ${(c.alerts||[]).length === 0 ? '<p style="color:var(--text-muted);font-size:13px">Nenhum alerta configurado</p>' :
        `<div style="display:flex;flex-direction:column;gap:6px">` +
        (c.alerts||[]).map(a => `
          <div class="alert-item ${a.priority}" style="margin-bottom:0">
            <span class="alert-icon">${alertIcon(a.priority)}</span>
            <div class="alert-body">
              <div class="alert-title">${a.title}</div>
              <div class="alert-meta">Disparo: ${formatDate(a.trigger_date)} · Evento: ${formatDate(a.event_date)}</div>
            </div>
            <span class="badge ${alertBadgeClass(a.status)}">${alertStatusLabel(a.status)}</span>
          </div>
        `).join('') + `</div>`
      }
    `;

    document.getElementById('detail-footer').innerHTML = `
      <button class="btn btn-ghost" onclick="closeModal('detail-modal')">Fechar</button>
      <button class="btn btn-ghost" onclick="closeModal('detail-modal');openEditContract('${c.id}')">✏️ Editar</button>
      <button class="btn btn-success" onclick="closeModal('detail-modal');openRenewal('${c.id}')">🔄 Renovação</button>
      ${currentUser.role === 'admin' ? `<button class="btn btn-danger" onclick="deleteContract('${c.id}')">🗑 Excluir</button>` : ''}
    `;

    openModal('detail-modal');
  } catch (e) { showToast(e.message, 'error'); }
}

function openNewContract() {
  document.getElementById('contract-id').value = '';
  document.getElementById('contract-modal-title').textContent = 'Novo Contrato';
  clearContractForm();
  // Set today as default start date
  document.getElementById('f-start').value = new Date().toISOString().split('T')[0];
  openModal('contract-modal');
}

async function openEditContract(id) {
  try {
    const c = await get(`/contracts/${id}`);
    document.getElementById('contract-id').value = c.id;
    document.getElementById('contract-modal-title').textContent = 'Editar Contrato';

    document.getElementById('f-title').value = c.title || '';
    document.getElementById('f-type').value = c.contract_type || 'service';
    document.getElementById('f-department').value = c.department || '';
    document.getElementById('f-counterparty').value = c.counterparty_name || '';
    document.getElementById('f-doc').value = c.counterparty_doc || '';
    document.getElementById('f-email').value = c.counterparty_email || '';
    document.getElementById('f-start').value = c.start_date || '';
    document.getElementById('f-end').value = c.end_date || '';
    document.getElementById('f-renewal').value = c.renewal_type || 'manual';
    document.getElementById('f-notice').value = c.renewal_notice_days || 30;
    document.getElementById('f-value-total').value = c.value_total || '';
    document.getElementById('f-value-monthly').value = c.value_monthly || '';
    document.getElementById('f-responsible').value = c.responsible_id || '';
    document.getElementById('f-confidential').value = String(c.is_confidential);
    document.getElementById('f-description').value = c.description || '';
    document.getElementById('f-notes').value = c.internal_notes || '';

    openModal('contract-modal');
  } catch (e) { showToast(e.message, 'error'); }
}

function clearContractForm() {
  ['f-title','f-department','f-counterparty','f-doc','f-email','f-end',
   'f-value-total','f-value-monthly','f-description','f-notes'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('f-type').value = 'service';
  document.getElementById('f-renewal').value = 'manual';
  document.getElementById('f-notice').value = '30';
  document.getElementById('f-confidential').value = 'false';
  document.getElementById('f-responsible').value = '';
}

async function saveContract() {
  const id = document.getElementById('contract-id').value;
  const btn = document.getElementById('save-contract-btn');

  const data = {
    title: document.getElementById('f-title').value.trim(),
    contract_type: document.getElementById('f-type').value,
    department: document.getElementById('f-department').value.trim(),
    counterparty_name: document.getElementById('f-counterparty').value.trim(),
    counterparty_doc: document.getElementById('f-doc').value.trim(),
    counterparty_email: document.getElementById('f-email').value.trim(),
    start_date: document.getElementById('f-start').value,
    end_date: document.getElementById('f-end').value || null,
    renewal_type: document.getElementById('f-renewal').value,
    renewal_notice_days: parseInt(document.getElementById('f-notice').value),
    value_total: document.getElementById('f-value-total').value || null,
    value_monthly: document.getElementById('f-value-monthly').value || null,
    responsible_id: document.getElementById('f-responsible').value || null,
    is_confidential: document.getElementById('f-confidential').value === 'true',
    description: document.getElementById('f-description').value.trim(),
    internal_notes: document.getElementById('f-notes').value.trim(),
  };

  if (!data.title || !data.counterparty_name || !data.start_date) {
    showToast('Preencha os campos obrigatórios (título, contraparte, início)', 'error');
    return;
  }

  btn.innerHTML = '<span class="spinner"></span> Salvando...';
  btn.disabled = true;

  try {
    if (id) {
      await put(`/contracts/${id}`, data);
      showToast('Contrato atualizado com sucesso!', 'success');
    } else {
      await post('/contracts', data);
      showToast('Contrato criado com sucesso! Alertas automáticos configurados.', 'success');
    }
    closeModal('contract-modal');
    loadContracts();
    loadDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btn.innerHTML = 'Salvar Contrato';
    btn.disabled = false;
  }
}

async function deleteContract(id) {
  if (!confirm('Tem certeza que deseja excluir este contrato? Esta ação não pode ser desfeita.')) return;
  try {
    await del(`/contracts/${id}`);
    showToast('Contrato excluído', 'info');
    closeModal('detail-modal');
    loadContracts();
    loadDashboard();
  } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════
//  ALERTS
// ═══════════════════════════════════════════
async function loadAlerts() {
  const status = document.getElementById('alert-filter')?.value || '';
  const priority = document.getElementById('alert-priority')?.value || '';

  let qs = '?';
  if (status) qs += `status=${status}&`;
  if (priority) qs += `priority=${priority}`;

  try {
    const alerts = await get(`/alerts${qs}`);
    const container = document.getElementById('alerts-list');

    if (!alerts.length) {
      container.innerHTML = `<div class="empty-state">
        <div class="empty-icon">🔔</div>
        <h3>Nenhum alerta</h3>
        <p>Todos os contratos estão dentro do prazo ou os alertas foram resolvidos.</p>
      </div>`;
      return;
    }

    container.innerHTML = alerts.map(a => `
      <div class="alert-item ${a.priority}" onclick="ackAlert('${a.id}', this)">
        <span class="alert-icon">${alertIcon(a.priority)}</span>
        <div class="alert-body">
          <div class="alert-title">${a.title}</div>
          <div class="alert-meta">
            <strong>${a.contract_title}</strong> · ${a.counterparty || ''}
          </div>
          <div class="alert-meta" style="margin-top:2px">
            Vencimento: <span class="text-mono">${formatDate(a.event_date)}</span>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div><span class="badge ${alertBadgeClass(a.status)}">${alertStatusLabel(a.status)}</span></div>
          <div class="alert-time" style="margin-top:4px">${a.trigger_date}</div>
          ${a.status !== 'acknowledged' ? `<button class="btn btn-success btn-sm" style="margin-top:6px" onclick="event.stopPropagation();ackAlert('${a.id}', this)">✓ Resolver</button>` : ''}
        </div>
      </div>
    `).join('');
  } catch (e) { showToast(e.message, 'error'); }
}

async function ackAlert(id, el) {
  try {
    await post(`/alerts/${id}/acknowledge`);
    showToast('Alerta marcado como resolvido', 'success');
    loadAlerts();
    loadDashboard();
  } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════
//  RENEWALS
// ═══════════════════════════════════════════
async function loadRenewals() {
  try {
    // Load renewals by fetching all contracts and their renewals
    const cData = await get('/contracts?per_page=100');
    const tbody = document.getElementById('renewals-body');
    let allRenewals = [];

    for (const c of cData.contracts.slice(0, 20)) {
      try {
        const renewals = await get(`/contracts/${c.id}/renewals`);
        renewals.forEach(r => r._contract_title = c.title);
        allRenewals = allRenewals.concat(renewals);
      } catch {}
    }

    if (!allRenewals.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
        <div class="empty-icon">🔄</div>
        <h3>Sem renovações registradas</h3>
        <p>As renovações aparecerão aqui quando você as registrar.</p>
      </div></td></tr>`;
      return;
    }

    const decisionLabels = { renew: '✅ Renovado', renegotiate: '🤝 Renegociado', terminate: '❌ Encerrado', replace: '🔄 Substituído' };
    const decisionColors = { renew: 'badge-active', renegotiate: 'badge-type', terminate: 'badge-expired', replace: 'badge-renewed' };

    tbody.innerHTML = allRenewals.map(r => `
      <tr>
        <td>${r._contract_title || '—'}</td>
        <td class="text-mono">#${r.renewal_number}</td>
        <td><span class="badge ${decisionColors[r.decision]}">${decisionLabels[r.decision]}</span></td>
        <td class="text-mono">${r.new_start_date || '—'} → ${r.new_end_date || '—'}</td>
        <td class="money">${r.new_value ? formatMoney(r.new_value) : '—'}</td>
        <td>${r.decision_user || '—'}</td>
        <td class="text-mono">${formatDate(r.created_at?.split('T')[0])}</td>
      </tr>
    `).join('');
  } catch (e) { showToast(e.message, 'error'); }
}

function openRenewal(contractId) {
  document.getElementById('renewal-contract-id').value = contractId;
  selectedDecision = 'renew';
  document.querySelectorAll('.decision-btn').forEach(b => b.classList.remove('selected'));
  document.querySelector('.decision-btn[data-v="renew"]').classList.add('selected');

  // Default new dates (1 year from today)
  const today = new Date();
  const nextYear = new Date(today);
  nextYear.setFullYear(nextYear.getFullYear() + 1);
  document.getElementById('r-start').value = today.toISOString().split('T')[0];
  document.getElementById('r-end').value = nextYear.toISOString().split('T')[0];
  document.getElementById('r-value').value = '';
  document.getElementById('r-notes').value = '';

  openModal('renewal-modal');
}

function selectDecision(v) {
  selectedDecision = v;
  document.querySelectorAll('.decision-btn').forEach(b => {
    b.classList.toggle('selected', b.dataset.v === v);
  });
}

async function saveRenewal() {
  const contractId = document.getElementById('renewal-contract-id').value;
  const data = {
    decision: selectedDecision,
    new_start_date: document.getElementById('r-start').value || null,
    new_end_date: document.getElementById('r-end').value || null,
    new_value: document.getElementById('r-value').value || null,
    notes: document.getElementById('r-notes').value,
  };
  try {
    await post(`/contracts/${contractId}/renewals`, data);
    showToast('Decisão de renovação registrada!', 'success');
    closeModal('renewal-modal');
    loadContracts();
    loadDashboard();
  } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════
//  USERS
// ═══════════════════════════════════════════
async function loadUsers() {
  try {
    users = await get('/users');

    // Populate responsible dropdown
    const sel = document.getElementById('f-responsible');
    if (sel) {
      sel.innerHTML = '<option value="">Selecionar...</option>' +
        users.map(u => `<option value="${u.id}">${u.name} (${u.department || u.role})</option>`).join('');
    }

    const tbody = document.getElementById('users-body');
    if (!tbody) return;

    const roleLabels = { admin: 'Administrador', legal: 'Jurídico', manager: 'Gestor', viewer: 'Visualizador' };
    const roleColors = { admin: 'var(--red)', legal: 'var(--purple)', manager: 'var(--accent)', viewer: 'var(--text-muted)' };

    tbody.innerHTML = users.map(u => `
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:10px">
            <div class="user-avatar" style="font-size:13px">${u.name.charAt(0)}</div>
            <strong>${u.name}</strong>
          </div>
        </td>
        <td class="text-mono" style="font-size:12px">${u.email}</td>
        <td><span style="color:${roleColors[u.role]}">${roleLabels[u.role]}</span></td>
        <td>${u.department || '—'}</td>
        <td>${u.is_active ? '<span class="badge badge-active">Ativo</span>' : '<span class="badge badge-cancelled">Inativo</span>'}</td>
        <td>
          <button class="btn btn-ghost btn-sm" onclick="openEditUser('${u.id}')">Editar</button>
        </td>
      </tr>
    `).join('');
  } catch {}
}

function openNewUser() {
  document.getElementById('u-id').value = '';
  document.getElementById('user-modal-title').textContent = 'Novo Usuário';
  ['u-name','u-email','u-dept','u-pass'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('u-role').value = 'viewer';
  openModal('user-modal');
}

function openEditUser(id) {
  const user = users.find(u => u.id === id);
  if (!user) return;
  document.getElementById('u-id').value = user.id;
  document.getElementById('user-modal-title').textContent = 'Editar Usuário';
  document.getElementById('u-name').value = user.name;
  document.getElementById('u-email').value = user.email;
  document.getElementById('u-role').value = user.role;
  document.getElementById('u-dept').value = user.department || '';
  document.getElementById('u-pass').value = '';
  openModal('user-modal');
}

async function saveUser() {
  const id = document.getElementById('u-id').value;
  const data = {
    name: document.getElementById('u-name').value.trim(),
    email: document.getElementById('u-email').value.trim(),
    role: document.getElementById('u-role').value,
    department: document.getElementById('u-dept').value.trim(),
    password: document.getElementById('u-pass').value,
  };
  if (!data.name || !data.email) { showToast('Preencha nome e e-mail', 'error'); return; }
  if (!id && !data.password) { showToast('Informe a senha', 'error'); return; }
  try {
    if (id) { await put(`/users/${id}`, data); showToast('Usuário atualizado', 'success'); }
    else { await post('/users', data); showToast('Usuário criado!', 'success'); }
    closeModal('user-modal');
    loadUsers();
  } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════
//  AUDIT
// ═══════════════════════════════════════════
async function loadAudit() {
  try {
    const logs = await get('/audit');
    const tbody = document.getElementById('audit-body');

    const actionColors = {
      'LOGIN': 'var(--green)', 'CREATE_CONTRACT': 'var(--accent)',
      'UPDATE_CONTRACT': 'var(--yellow)', 'DELETE_CONTRACT': 'var(--red)',
      'CREATE_RENEWAL': 'var(--purple)',
    };

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td><span style="color:${actionColors[l.action]||'var(--text-secondary)'};font-family:var(--font-mono);font-size:11px">${l.action}</span></td>
        <td><span class="text-mono" style="font-size:11px">${l.entity_type || '—'}</span></td>
        <td>${l.user || 'Sistema'}</td>
        <td class="text-mono" style="font-size:11px;color:var(--text-muted)">${l.ip_address || '—'}</td>
        <td class="text-mono" style="font-size:11px;color:var(--text-muted)">${l.created_at ? new Date(l.created_at).toLocaleString('pt-BR') : '—'}</td>
      </tr>
    `).join('');
  } catch (e) { showToast(e.message, 'error'); }
}

// ═══════════════════════════════════════════
//  REPORTS
// ═══════════════════════════════════════════
async function genReport(type) {
  const out = document.getElementById('report-output');
  out.innerHTML = '<div style="text-align:center;padding:20px"><div class="spinner" style="margin:0 auto"></div></div>';

  try {
    const data = await get('/contracts?per_page=200');
    const contracts = data.contracts;
    const today = new Date();

    let html = '';

    if (type === 'expiring') {
      const d30 = contracts.filter(c => c.days_until_expiry !== null && c.days_until_expiry >= 0 && c.days_until_expiry <= 30);
      const d60 = contracts.filter(c => c.days_until_expiry !== null && c.days_until_expiry > 30 && c.days_until_expiry <= 60);
      const d90 = contracts.filter(c => c.days_until_expiry !== null && c.days_until_expiry > 60 && c.days_until_expiry <= 90);

      html = `
        <div class="card">
          <div style="font-family:var(--font-display);font-size:20px;font-weight:800;margin-bottom:4px">📅 Relatório de Vencimentos</div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:24px">Gerado em ${today.toLocaleString('pt-BR')}</div>
          ${reportSection('🚨 Vencendo em 30 dias', d30, 'red')}
          ${reportSection('⚠️ Vencendo entre 30-60 dias', d60, 'orange')}
          ${reportSection('📋 Vencendo entre 60-90 dias', d90, 'yellow')}
        </div>`;
    } else if (type === 'portfolio') {
      const active = contracts.filter(c => ['active','expiring'].includes(c.status));
      html = `
        <div class="card">
          <div style="font-family:var(--font-display);font-size:20px;font-weight:800;margin-bottom:4px">📊 Portfólio Contratual Ativo</div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:24px">${active.length} contratos · Gerado em ${today.toLocaleString('pt-BR')}</div>
          ${reportSection('Contratos Ativos', active, 'accent')}
        </div>`;
    } else {
      html = `<div class="card"><p style="color:var(--text-secondary)">Relatório em desenvolvimento.</p></div>`;
    }

    // Adiciona botão de imprimir/exportar PDF
    out.innerHTML = html + `
      <div style="margin-top:20px;display:flex;gap:10px;justify-content:flex-end">
        <button class="btn btn-primary" onclick="printReport()">
          🖨️ Gerar PDF / Imprimir
        </button>
        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('report-output').innerHTML=''">
          ✕ Fechar
        </button>
      </div>`;
  } catch (e) { out.innerHTML = ''; showToast(e.message, 'error'); }
}

function printReport() {
  // Aplica estilos de impressão inline para tema claro
  const style = document.createElement('style');
  style.id = 'print-override';
  style.textContent = `
    @media print {
      body { background: #fff !important; color: #000 !important; }
      .sidebar, .page-header .page-actions, #toast-container { display: none !important; }
      .main { margin-left: 0 !important; }
      .page { display: block !important; padding: 0 !important; }
      .page:not(#page-reports) { display: none !important; }
      .card { background: #fff !important; border: 1px solid #ddd !important; color: #000 !important; box-shadow: none !important; }
      table { color: #000 !important; }
      th, td { color: #000 !important; border-color: #ddd !important; }
      h3 { color: #333 !important; }
      .btn { display: none !important; }
      #report-output .btn { display: none !important; }
      * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  `;
  document.head.appendChild(style);
  window.print();
  setTimeout(() => {
    const s = document.getElementById('print-override');
    if (s) s.remove();
  }, 1500);
}

function reportSection(title, list, color) {
  if (!list.length) return `<div style="margin-bottom:20px"><h3 style="color:var(--${color});font-size:14px;margin-bottom:8px">${title} (0)</h3><p style="color:var(--text-muted);font-size:13px">Nenhum contrato neste período.</p></div>`;
  return `
    <div style="margin-bottom:28px">
      <h3 style="color:var(--${color});font-size:14px;margin-bottom:12px;font-family:var(--font-display)">${title} (${list.length})</h3>
      <table style="width:100%;border-collapse:collapse">
        <thead><tr>
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">Código</th>
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">Contrato</th>
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">Contraparte</th>
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">Vencimento</th>
          <th style="text-align:right;padding:8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">Valor/mês</th>
        </tr></thead>
        <tbody>${list.map(c => `
          <tr style="border-bottom:1px solid rgba(30,45,61,0.5)">
            <td style="padding:8px;font-family:var(--font-mono);font-size:11px;color:var(--accent)">${c.code}</td>
            <td style="padding:8px;font-size:13px">${c.title}</td>
            <td style="padding:8px;font-size:13px">${c.counterparty_name}</td>
            <td style="padding:8px;font-family:var(--font-mono);font-size:12px">${formatDate(c.end_date)}</td>
            <td style="padding:8px;font-family:var(--font-mono);font-size:12px;text-align:right">${c.value_monthly ? formatMoney(c.value_monthly) : '—'}</td>
          </tr>
        `).join('')}</tbody>
      </table>
    </div>`;
}

// ═══════════════════════════════════════════
//  MODAL HELPERS
// ═══════════════════════════════════════════
function openModal(id) {
  document.getElementById(id).classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.body.style.overflow = '';
}

// Close on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeModal(overlay.id);
  });
});

// ESC key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => closeModal(m.id));
  }
});

// ═══════════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════════
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type]}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateY(10px)'; toast.style.transition = '0.3s'; setTimeout(() => toast.remove(), 300); }, 3500);
}

// ═══════════════════════════════════════════
//  FORMATTERS
// ═══════════════════════════════════════════
function formatDate(d) {
  if (!d) return '—';
  const parts = d.split('T')[0].split('-');
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

function formatMoney(v) {
  if (!v) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
}

function statusBadge(s) {
  const map = {
    active: ['badge-active', 'Ativo'],
    expiring: ['badge-expiring', 'Vencendo'],
    expired: ['badge-expired', 'Vencido'],
    draft: ['badge-draft', 'Rascunho'],
    cancelled: ['badge-cancelled', 'Cancelado'],
    renewed: ['badge-renewed', 'Renovado'],
  };
  const [cls, label] = map[s] || ['badge-draft', s];
  return `<span class="badge ${cls}">${label}</span>`;
}

function typeLabel(t) {
  const m = { service: 'Serviço', supply: 'Fornecimento', lease: 'Locação', nda: 'NDA', sla: 'SLA', partnership: 'Parceria', other: 'Outro' };
  return m[t] || t;
}

function renewalLabel(t) {
  const m = { manual: 'Manual', automatic: 'Automática', none: 'Sem renovação' };
  return m[t] || t;
}

function alertIcon(p) {
  return { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' }[p] || '🔵';
}

function alertBadgeClass(s) {
  return { pending: 'badge-expiring', sent: 'badge-type', acknowledged: 'badge-active', snoozed: 'badge-draft', dismissed: 'badge-cancelled' }[s] || 'badge-draft';
}

function alertStatusLabel(s) {
  return { pending: 'Pendente', sent: 'Enviado', acknowledged: 'Resolvido', snoozed: 'Adiado', dismissed: 'Ignorado' }[s] || s;
}

// ═══════════════════════════════════════════
//  BOOT
// ═══════════════════════════════════════════
document.getElementById('login-email').addEventListener('keydown', e => e.key === 'Enter' && document.getElementById('login-password').focus());
document.getElementById('login-password').addEventListener('keydown', e => e.key === 'Enter' && doLogin());

// Check existing session
if (token) {
  try {
    currentUser = JSON.parse(localStorage.getItem('user'));
    if (currentUser) initApp();
    else doLogout();
  } catch { doLogout(); }
}
