<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  let config = {
    sleep_hour_start: 23,
    sleep_hour_end: 7,
    quiet_hour_start: 22,
    quiet_hour_end: 8,
    night_volume: 30,
    day_volume: 80,
    brightness_max: 200,
  };
  let loading = true;
  let saving = false;

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data && data.screen) {
      config = { ...config, ...data.screen };
    }
    loading = false;
  });

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/screen', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration ecran sauvegardee', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }

  async function screenOff() {
    const res = await apiPost('/admin/api/screen/off', {});
    if (res.ok) {
      showToast('Ecran eteint', 'success');
    } else {
      showToast('Erreur', 'error');
    }
  }

  async function screenOn() {
    const res = await apiPost('/admin/api/screen/on', {});
    if (res.ok) {
      showToast('Ecran allume', 'success');
    } else {
      showToast('Erreur', 'error');
    }
  }

  function formatHour(h) {
    return `${String(h).padStart(2, '0')}:00`;
  }
</script>

<div class="page">
  <h1 class="page-title">Ecran & Horaires</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <h2 class="section-title">Actions rapides</h2>
      <div class="actions-row">
        <button class="btn-action" on:click={screenOff}>Eteindre ecran maintenant</button>
        <button class="btn-action btn-on" on:click={screenOn}>Allumer ecran maintenant</button>
      </div>
    </div>

    <div class="card">
      <h2 class="section-title">Horaires ecran</h2>

      <div class="form-group">
        <label class="form-label" for="sleep_start">
          Extinction auto : {formatHour(config.sleep_hour_start)}
        </label>
        <input id="sleep_start" type="range" bind:value={config.sleep_hour_start} min="0" max="23" step="1" />
        <div class="range-labels">
          <span>00:00</span>
          <span>23:00</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="sleep_end">
          Reveil auto : {formatHour(config.sleep_hour_end)}
        </label>
        <input id="sleep_end" type="range" bind:value={config.sleep_hour_end} min="0" max="23" step="1" />
        <div class="range-labels">
          <span>00:00</span>
          <span>23:00</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2 class="section-title">Horaires volume</h2>

      <div class="form-group">
        <label class="form-label" for="quiet_start">
          Mode nuit debut : {formatHour(config.quiet_hour_start)}
        </label>
        <input id="quiet_start" type="range" bind:value={config.quiet_hour_start} min="0" max="23" step="1" />
        <div class="range-labels">
          <span>00:00</span>
          <span>23:00</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="quiet_end">
          Mode nuit fin : {formatHour(config.quiet_hour_end)}
        </label>
        <input id="quiet_end" type="range" bind:value={config.quiet_hour_end} min="0" max="23" step="1" />
        <div class="range-labels">
          <span>00:00</span>
          <span>23:00</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="night_volume">
          Volume nuit : {config.night_volume}%
        </label>
        <input id="night_volume" type="range" bind:value={config.night_volume} min="0" max="100" step="5" />
        <div class="range-labels">
          <span>0%</span>
          <span>100%</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="day_volume">
          Volume jour : {config.day_volume}%
        </label>
        <input id="day_volume" type="range" bind:value={config.day_volume} min="0" max="100" step="5" />
        <div class="range-labels">
          <span>0%</span>
          <span>100%</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2 class="section-title">Luminosite</h2>

      <div class="form-group">
        <label class="form-label" for="brightness_max">
          Luminosite maximale : {config.brightness_max}
        </label>
        <input id="brightness_max" type="range" bind:value={config.brightness_max} min="0" max="255" step="5" />
        <div class="range-labels">
          <span>0 (eteint)</span>
          <span>255 (max)</span>
        </div>
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

  .section-title {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 20px;
    color: #ccc;
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
    margin-bottom: 16px;
  }

  .actions-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }

  .btn-action {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: border-color 0.15s;
  }

  .btn-action:hover {
    border-color: #6c63ff;
  }

  .btn-on {
    border-color: rgba(74, 222, 128, 0.3);
    color: #4ade80;
  }

  .btn-on:hover {
    border-color: #4ade80;
  }

  .form-group { margin-bottom: 20px; }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  input[type="range"] {
    width: 100%;
    accent-color: #6c63ff;
  }

  .range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #666;
    margin-top: 4px;
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
