<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, showToast } from '../stores/auth.js';

  let config = {
    // Défauts = identité PI-Board (doivent matcher config_manager.py / PBTheme).
    accent_color: '#7C6FFF',
    bg_color: '#060610',
    swipe_threshold_px: 50,
    page_transition_ms: 300,
    clock_update_ms: 1000,
  };
  let loading = true;
  let saving = false;

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data && data.ui) {
      config = { ...config, ...data.ui };
    }
    loading = false;
  });

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/ui', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration interface sauvegardee', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }
</script>

<div class="page">
  <h1 class="page-title">Interface</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <div class="form-group">
        <label class="form-label" for="accent_color">Couleur d'accent</label>
        <div class="color-row">
          <input id="accent_color" type="color" bind:value={config.accent_color} class="color-input" />
          <input type="text" bind:value={config.accent_color} class="color-text" />
          <div class="color-preview" style="background: {config.accent_color}"></div>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="bg_color">Couleur de fond</label>
        <div class="color-row">
          <input id="bg_color" type="color" bind:value={config.bg_color} class="color-input" />
          <input type="text" bind:value={config.bg_color} class="color-text" />
          <div class="color-preview" style="background: {config.bg_color}"></div>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="swipe_threshold_px">Seuil swipe</label>
        <select id="swipe_threshold_px" bind:value={config.swipe_threshold_px}>
          <option value={40}>40 px</option>
          <option value={50}>50 px (par defaut)</option>
          <option value={60}>60 px</option>
          <option value={80}>80 px</option>
          <option value={100}>100 px</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="page_transition_ms">Transition page</label>
        <select id="page_transition_ms" bind:value={config.page_transition_ms}>
          <option value={200}>200 ms (rapide)</option>
          <option value={300}>300 ms (par defaut)</option>
          <option value={400}>400 ms</option>
          <option value={500}>500 ms (lent)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="clock_update_ms">Mise a jour horloge</label>
        <select id="clock_update_ms" bind:value={config.clock_update_ms}>
          <option value={5000}>5 secondes</option>
          <option value={10000}>10 secondes</option>
          <option value={30000}>30 secondes</option>
          <option value={60000}>60 secondes</option>
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

  .color-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .color-input {
    width: 44px;
    height: 36px;
    border: 1px solid #333;
    border-radius: 6px;
    background: #1a1a24;
    cursor: pointer;
    padding: 2px;
  }

  .color-text {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    font-family: 'JetBrains Mono', monospace;
    width: 120px;
  }

  .color-text:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .color-preview {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.1);
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
