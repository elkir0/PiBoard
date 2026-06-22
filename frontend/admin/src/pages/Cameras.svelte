<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, showToast } from '../stores/auth.js';

  let config = {
    snapshot_width: 1280,
    snapshot_height: 720,
    stream_width: 640,
    stream_height: 360,
    stream_refresh_s: 0.5,
    grid_refresh_ms: 5000,
    auth_timeout_s: 10,
  };
  let loading = true;
  let saving = false;

  // Resolution presets
  let snapshotResolution = '640x360';
  let streamResolution = '640x360';

  const snapshotPresets = [
    { label: 'Basse (320x180)', value: '320x180' },
    { label: 'Moyenne (640x360)', value: '640x360' },
    { label: 'Haute (960x540)', value: '960x540' },
  ];

  const streamPresets = [
    { label: 'Moyenne (640x360)', value: '640x360' },
    { label: 'HD (1280x720)', value: '1280x720' },
    { label: 'Full HD (1920x1080)', value: '1920x1080' },
  ];

  const gridRefreshPresets = [
    { label: '1 seconde', value: 1000 },
    { label: '1.5 secondes', value: 1500 },
    { label: '2 secondes', value: 2000 },
    { label: '3 secondes', value: 3000 },
    { label: '5 secondes', value: 5000 },
  ];

  const authTimeoutPresets = [
    { label: '30 minutes', value: 1800 },
    { label: '1 heure', value: 3600 },
    { label: '2 heures', value: 7200 },
    { label: '4 heures', value: 14400 },
  ];

  function detectSnapshotPreset() {
    const key = `${config.snapshot_width}x${config.snapshot_height}`;
    return snapshotPresets.some(p => p.value === key) ? key : '640x360';
  }

  function detectStreamPreset() {
    const key = `${config.stream_width}x${config.stream_height}`;
    return streamPresets.some(p => p.value === key) ? key : '640x360';
  }

  function applySnapshotResolution() {
    const [w, h] = snapshotResolution.split('x').map(Number);
    config.snapshot_width = w;
    config.snapshot_height = h;
  }

  function applyStreamResolution() {
    const [w, h] = streamResolution.split('x').map(Number);
    config.stream_width = w;
    config.stream_height = h;
  }

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data && data.cameras) {
      config = { ...config, ...data.cameras };
    }
    snapshotResolution = detectSnapshotPreset();
    streamResolution = detectStreamPreset();
    loading = false;
  });

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/cameras', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration cameras sauvegardee', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }
</script>

<div class="page">
  <h1 class="page-title">Cameras</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <h2 class="section-title">Snapshot</h2>

      <div class="form-group">
        <label class="form-label" for="snapshot_res">Resolution snapshot</label>
        <select id="snapshot_res" bind:value={snapshotResolution} on:change={applySnapshotResolution}>
          {#each snapshotPresets as preset}
            <option value={preset.value}>{preset.label}</option>
          {/each}
        </select>
      </div>
    </div>

    <div class="card">
      <h2 class="section-title">Stream</h2>

      <div class="form-group">
        <label class="form-label" for="stream_res">Resolution stream</label>
        <select id="stream_res" bind:value={streamResolution} on:change={applyStreamResolution}>
          {#each streamPresets as preset}
            <option value={preset.value}>{preset.label}</option>
          {/each}
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="stream_refresh_s">
          Rafraichissement stream : {config.stream_refresh_s}s
        </label>
        <input id="stream_refresh_s" type="range" bind:value={config.stream_refresh_s} min="0.1" max="5" step="0.1" />
        <div class="range-labels">
          <span>0.1s (rapide)</span>
          <span>5s (lent)</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2 class="section-title">Grille & Authentification</h2>

      <div class="form-group">
        <label class="form-label" for="grid_refresh_ms">Rafraichissement grille</label>
        <select id="grid_refresh_ms" bind:value={config.grid_refresh_ms}>
          {#each gridRefreshPresets as preset}
            <option value={preset.value}>{preset.label}</option>
          {/each}
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="auth_timeout_s">Timeout authentification</label>
        <select id="auth_timeout_s" bind:value={config.auth_timeout_s}>
          {#each authTimeoutPresets as preset}
            <option value={preset.value}>{preset.label}</option>
          {/each}
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
