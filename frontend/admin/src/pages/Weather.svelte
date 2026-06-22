<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, showToast } from '../stores/auth.js';

  let config = {
    timezone: 'America/Guadeloupe',
    forecast_days: 3,
    fetch_timeout_s: 10,
  };
  let loading = true;
  let saving = false;

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data && data.weather) {
      config = { ...config, ...data.weather };
    }
    loading = false;
  });

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/weather', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration meteo sauvegardee', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }
</script>

<div class="page">
  <h1 class="page-title">Meteo</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <div class="form-group">
        <label class="form-label" for="timezone">Fuseau horaire</label>
        <select id="timezone" bind:value={config.timezone}>
          <option value="America/Guadeloupe">America/Guadeloupe (AST)</option>
          <option value="America/Martinique">America/Martinique (AST)</option>
          <option value="Europe/Paris">Europe/Paris (CET)</option>
          <option value="Europe/London">Europe/London (GMT)</option>
          <option value="America/New_York">America/New_York (EST)</option>
          <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
          <option value="America/Cayenne">America/Cayenne (GFT)</option>
          <option value="Indian/Reunion">Indian/Reunion (RET)</option>
          <option value="Pacific/Noumea">Pacific/Noumea (NCT)</option>
          <option value="Pacific/Tahiti">Pacific/Tahiti (TAHT)</option>
          <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="forecast_days">Jours de prevision</label>
        <select id="forecast_days" bind:value={config.forecast_days}>
          <option value={2}>2 jours</option>
          <option value={3}>3 jours</option>
          <option value={4}>4 jours</option>
          <option value={5}>5 jours</option>
          <option value={7}>7 jours</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="fetch_timeout_s">Timeout requete</label>
        <select id="fetch_timeout_s" bind:value={config.fetch_timeout_s}>
          <option value={5}>5 secondes</option>
          <option value={10}>10 secondes</option>
          <option value={15}>15 secondes</option>
          <option value={30}>30 secondes</option>
        </select>
      </div>

      <button class="btn-save" on:click={save} disabled={saving}>
        {saving ? 'Sauvegarde...' : 'Sauvegarder'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 600px; }

  .page-title {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 24px;
  }

  .loading {
    color: #888;
    padding: 40px;
    text-align: center;
  }

  .card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 24px;
  }

  .form-group { margin-bottom: 20px; }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  select {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  select:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .btn-save {
    background: #6c63ff;
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: opacity 0.15s;
  }

  .btn-save:hover { opacity: 0.9; }
  .btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
