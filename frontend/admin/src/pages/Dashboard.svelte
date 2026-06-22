<script>
  import { onMount, onDestroy } from 'svelte';
  import { apiGet } from '../stores/auth.js';

  let system = null;
  let loading = true;
  let interval;
  let lastUpdate = null;

  async function fetchSystem() {
    const data = await apiGet('/admin/api/system');
    if (data) {
      system = data;
      lastUpdate = new Date();
    }
    loading = false;
  }

  onMount(() => {
    fetchSystem();
    interval = setInterval(fetchSystem, 10000);
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
  });

  function formatUptime(seconds) {
    if (!seconds) return '-';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const parts = [];
    if (d > 0) parts.push(`${d} jour${d > 1 ? 's' : ''}`);
    if (h > 0) parts.push(`${h} heure${h > 1 ? 's' : ''}`);
    if (m > 0) parts.push(`${m} min`);
    return parts.join(', ') || '< 1 min';
  }

  function tempColor(temp) {
    if (!temp) return '#888';
    if (temp < 50) return '#4ade80';
    if (temp < 70) return '#fbbf24';
    return '#ff6b6b';
  }

  function usageColor(pct) {
    if (pct == null) return '#888';
    if (pct < 60) return '#4ade80';
    if (pct < 85) return '#fbbf24';
    return '#ff6b6b';
  }

  function serviceStatusColor(connected) {
    if (connected === true) return '#4ade80';
    if (connected === false) return '#ff6b6b';
    return '#fbbf24';
  }

  function serviceStatusLabel(connected) {
    if (connected === true) return 'Connecte';
    if (connected === false) return 'Deconnecte';
    return 'Inconnu';
  }

  function formatLastUpdate(date) {
    if (!date) return '-';
    return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
</script>

<div class="page">
  <div class="page-header">
    <h1 class="page-title">Tableau de bord</h1>
    {#if lastUpdate}
      <span class="last-update">Derniere mise a jour : {formatLastUpdate(lastUpdate)}</span>
    {/if}
  </div>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else if system}
    <div class="grid">
      <div class="card stat-card">
        <div class="stat-label">Temperature CPU</div>
        <div class="stat-value" style="color: {tempColor(system.cpu_temp)}">
          {system.cpu_temp != null ? `${system.cpu_temp.toFixed(1)} C` : '-'}
        </div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">RAM utilisee</div>
        <div class="stat-value" style="color: {usageColor(system.memory?.percent)}">
          {system.memory?.percent != null ? `${system.memory.percent.toFixed(0)}%` : '-'}
        </div>
        <div class="stat-detail">
          {#if system.memory?.used_mb != null && system.memory?.total_mb != null}
            {system.memory.used_mb} / {system.memory.total_mb} MB
          {/if}
        </div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Disque utilise</div>
        <div class="stat-value" style="color: {usageColor(system.disk?.percent)}">
          {system.disk?.percent != null ? `${system.disk.percent.toFixed(0)}%` : '-'}
        </div>
        <div class="stat-detail">
          {#if system.disk?.used_gb != null && system.disk?.total_gb != null}
            {system.disk.used_gb} / {system.disk.total_gb} GB
          {/if}
        </div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Uptime</div>
        <div class="stat-value uptime-value">{formatUptime(system.uptime?.seconds)}</div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Adresse IP</div>
        <div class="stat-value ip">{system.ip || '-'}</div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Hostname</div>
        <div class="stat-value ip">{system.hostname || '-'}</div>
      </div>
    </div>

    <h2 class="section-title">Statut des services</h2>
    <div class="grid">
      <div class="card stat-card">
        <div class="stat-label">Spotify</div>
        <div class="stat-value status-row">
          <span class="status-dot" style="background: {serviceStatusColor(system.spotify_connected)}"></span>
          <span style="color: {serviceStatusColor(system.spotify_connected)}">
            {serviceStatusLabel(system.spotify_connected)}
          </span>
        </div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Cameras</div>
        <div class="stat-value status-row">
          <span class="status-dot" style="background: {system.cameras_count > 0 ? '#4ade80' : '#ff6b6b'}"></span>
          <span style="color: {system.cameras_count > 0 ? '#4ade80' : '#ff6b6b'}">
            {system.cameras_count ?? 0} active{(system.cameras_count ?? 0) !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div class="card stat-card">
        <div class="stat-label">Mot de reveil</div>
        <div class="stat-value status-row">
          <span class="status-dot" style="background: {system.wakeword_model ? '#4ade80' : '#fbbf24'}"></span>
          <span class="ip" style="color: {system.wakeword_model ? '#4ade80' : '#fbbf24'}">
            {system.wakeword_model || 'Non configure'}
          </span>
        </div>
      </div>
    </div>
  {:else}
    <div class="card">
      <p style="color: #888;">Impossible de charger les informations systeme.</p>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 900px; }

  .page-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .page-title {
    font-size: 22px;
    font-weight: 700;
  }

  .last-update {
    font-size: 12px;
    color: #666;
    font-family: 'JetBrains Mono', monospace;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    margin: 24px 0 16px;
    color: #ccc;
  }

  .loading {
    color: #888;
    padding: 40px;
    text-align: center;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
  }

  .card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
  }

  .stat-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .stat-label {
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .stat-value {
    font-size: 24px;
    font-weight: 700;
    color: #f0f0f0;
  }

  .stat-value.uptime-value {
    font-size: 18px;
    font-weight: 600;
  }

  .stat-value.ip {
    font-size: 15px;
    font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
  }

  .stat-value.status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
  }

  .stat-value.status-row .ip {
    font-size: 14px;
    font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
  }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 6px currentColor;
  }

  .stat-detail {
    font-size: 12px;
    color: #666;
  }

  @media (max-width: 768px) {
    .grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
