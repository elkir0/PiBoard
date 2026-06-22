<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  let config = {
    sample_rate: 16000,
    channels: 1,
    chunk_size: 512,
    error_threshold: 5,
    pipewire_volume: 45000,
    output_sink: '',
  };
  let loading = true;
  let saving = false;
  let savingSink = false;
  let needsRestart = false;
  let restarting = false;
  let sinks = [];

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data && data.audio) {
      config = { ...config, ...data.audio };
    }
    const s = await apiGet('/admin/api/audio/sinks');
    if (s && s.sinks) sinks = s.sinks;
    loading = false;
  });

  async function saveSink() {
    savingSink = true;
    const res = await apiPut('/admin/api/config/audio/output_sink', { value: config.output_sink });
    savingSink = false;
    showToast(res.ok ? 'Sortie audio enregistree' : 'Erreur', res.ok ? 'success' : 'error');
  }

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/audio', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration audio sauvegardee', 'success');
      needsRestart = true;
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }

  async function restartBackend() {
    restarting = true;
    const res = await apiPost('/admin/api/system/restart-backend', {});
    restarting = false;
    if (res.ok) {
      showToast('Backend en cours de redemarrage...', 'success');
      needsRestart = false;
    } else {
      showToast('Erreur lors du redemarrage', 'error');
    }
  }
</script>

<div class="page">
  <h1 class="page-title">Audio & Micro</h1>

  {#if needsRestart}
    <div class="restart-banner">
      Les modifications audio necessitent un redemarrage du backend pour prendre effet.
      <button class="btn-restart" on:click={restartBackend} disabled={restarting}>
        {restarting ? 'Redemarrage...' : 'Redemarrer le backend'}
      </button>
    </div>
  {/if}

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <h2 class="section-title">Sortie audio</h2>
      <div class="form-group">
        <label class="form-label" for="output_sink">Enceinte / sortie</label>
        <select id="output_sink" bind:value={config.output_sink}>
          <option value="">Auto (Devialet)</option>
          {#each sinks as s}
            <option value={s.name}>{s.label}{s.is_default ? ' — active' : ''}</option>
          {/each}
        </select>
      </div>
      <button class="btn-save" on:click={saveSink} disabled={savingSink}>
        {savingSink ? 'Sauvegarde...' : 'Appliquer la sortie'}
      </button>
    </div>

    <div class="card">
      <h2 class="section-title">Capture micro (avance)</h2>
      <div class="form-group">
        <label class="form-label" for="sample_rate">Taux d'echantillonnage (Hz)</label>
        <select id="sample_rate" bind:value={config.sample_rate}>
          <option value={8000}>8 000 Hz</option>
          <option value={16000}>16 000 Hz (recommande)</option>
          <option value={22050}>22 050 Hz</option>
          <option value={44100}>44 100 Hz</option>
          <option value={48000}>48 000 Hz</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="channels">Canaux</label>
        <select id="channels" bind:value={config.channels}>
          <option value={1}>1 (Mono)</option>
          <option value={2}>2 (Stereo)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="chunk_size">Taille chunk (samples)</label>
        <select id="chunk_size" bind:value={config.chunk_size}>
          <option value={256}>256</option>
          <option value={512}>512 (recommande)</option>
          <option value={1024}>1 024</option>
          <option value={2048}>2 048</option>
          <option value={4096}>4 096</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="error_threshold">Seuil d'erreur (max erreurs consecutives)</label>
        <input id="error_threshold" type="number" bind:value={config.error_threshold} min="1" max="50" />
      </div>

      <div class="form-group">
        <label class="form-label" for="pipewire_volume">
          Volume PipeWire TTS : {config.pipewire_volume}
        </label>
        <input id="pipewire_volume" type="range" bind:value={config.pipewire_volume} min="0" max="65536" step="1000" />
        <div class="range-labels">
          <span>0</span>
          <span>65536</span>
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

  .loading {
    color: #888;
    padding: 40px;
    text-align: center;
  }

  .restart-banner {
    background: rgba(251, 191, 36, 0.1);
    border: 1px solid rgba(251, 191, 36, 0.3);
    color: #fbbf24;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
  }

  .card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 16px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
    color: #ccc;
  }

  .form-group {
    margin-bottom: 20px;
  }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  input[type="number"], select {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  input[type="number"]:focus, select:focus {
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

  .btn-restart {
    display: block;
    margin-top: 10px;
    background: rgba(251, 191, 36, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.4);
    padding: 8px 18px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: opacity 0.15s;
  }

  .btn-restart:hover { opacity: 0.9; }
  .btn-restart:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
