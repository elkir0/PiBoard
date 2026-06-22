<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  let config = {
    format: 'bestvideo[height<=720][vcodec^=avc]+bestaudio/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
    search_limit: 5,
    search_timeout_s: 15,
    vlc_volume: 256,
    network_cache_ms: 5000,
    stop_timeout_s: 3,
  };
  let loading = true;
  let saving = false;

  // Cookies state
  let cookieStatus = null;
  let uploading = false;
  let cookieText = '';

  const formatPresets = [
    { label: '360p', value: 'bestvideo[height<=360][vcodec^=avc]+bestaudio/best' },
    { label: '480p', value: 'bestvideo[height<=480][vcodec^=avc]+bestaudio/best' },
    { label: '720p', value: 'bestvideo[height<=720][vcodec^=avc]+bestaudio/best' },
  ];

  onMount(async () => {
    const [data, cookies] = await Promise.all([
      apiGet('/admin/api/config'),
      apiGet('/admin/api/youtube/cookies'),
    ]);
    if (data && data.youtube) {
      config = { ...config, ...data.youtube };
    }
    cookieStatus = cookies;
    loading = false;
  });

  function applyPreset(preset) {
    config.format = preset.value;
  }

  async function save() {
    saving = true;
    const res = await apiPut('/admin/api/config/youtube', config);
    saving = false;
    if (res.ok) {
      showToast('Configuration YouTube sauvegardee', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }

  async function uploadCookies() {
    if (!cookieText.trim()) {
      showToast('Collez le contenu du fichier cookies.txt', 'error');
      return;
    }
    uploading = true;
    try {
      const base = import.meta.env.DEV ? 'http://localhost:8000' : '';
      const res = await fetch(`${base}/admin/api/youtube/cookies`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'text/plain' },
        body: cookieText,
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Cookies installes (${data.youtube_cookies} cookies YouTube)`, 'success');
        cookieStatus = await apiGet('/admin/api/youtube/cookies');
        cookieText = '';
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Erreur upload', 'error');
      }
    } catch (e) {
      showToast('Erreur de connexion', 'error');
    }
    uploading = false;
  }

  async function deleteCookies() {
    try {
      const base = import.meta.env.DEV ? 'http://localhost:8000' : '';
      const res = await fetch(`${base}/admin/api/youtube/cookies`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        showToast('Cookies supprimes', 'success');
        cookieStatus = { exists: false, lines: 0, youtube_cookies: 0 };
      }
    } catch (e) {
      showToast('Erreur', 'error');
    }
  }

  function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { cookieText = reader.result; };
    reader.readAsText(file);
  }
</script>

<div class="page">
  <h1 class="page-title">YouTube</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <!-- Cookies section -->
    <div class="card cookies-card">
      <h2 class="section-title">Cookies YouTube</h2>

      {#if cookieStatus && cookieStatus.exists}
        <div class="cookie-status ok">
          <span class="status-dot ok"></span>
          <span>Cookies actifs — {cookieStatus.youtube_cookies} cookies YouTube ({cookieStatus.size_kb} KB)</span>
          <button class="btn-delete" on:click={deleteCookies}>Supprimer</button>
        </div>
      {:else}
        <div class="cookie-status warning">
          <span class="status-dot warning"></span>
          <span>Pas de cookies — YouTube peut bloquer les videos</span>
        </div>
      {/if}

      <details class="tuto">
        <summary>Comment obtenir les cookies ?</summary>
        <div class="tuto-content">
          <p><strong>Sur votre ordinateur :</strong></p>
          <ol>
            <li>Connectez-vous a <a href="https://youtube.com" target="_blank">youtube.com</a> avec votre compte Google</li>
            <li>Installez l'extension <strong>"Get cookies.txt LOCALLY"</strong> pour <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank">Chrome</a> ou <a href="https://addons.mozilla.org/fr/firefox/addon/cookies-txt/" target="_blank">Firefox</a></li>
            <li>Allez sur youtube.com, cliquez sur l'extension, puis <strong>"Export"</strong></li>
            <li>Ouvrez le fichier telecharge (cookies.txt) et copiez tout le contenu</li>
            <li>Collez-le dans la zone ci-dessous et cliquez "Installer"</li>
          </ol>
          <p class="tuto-alt"><strong>Alternative (terminal) :</strong></p>
          <code class="tuto-code">yt-dlp --cookies-from-browser chrome --cookies cookies.txt --skip-download "https://youtube.com"</code>
          <p class="tuto-note">Puis copiez le contenu de cookies.txt ci-dessous.</p>
        </div>
      </details>

      <div class="cookie-upload">
        <div class="upload-row">
          <label class="file-btn">
            <input type="file" accept=".txt" on:change={handleFile} hidden />
            Choisir un fichier
          </label>
          <span class="upload-or">ou collez le contenu :</span>
        </div>
        <textarea
          class="cookie-textarea"
          bind:value={cookieText}
          placeholder="# Netscape HTTP Cookie File&#10;.youtube.com ..."
          rows="6"
        ></textarea>
        <button class="btn-upload" on:click={uploadCookies} disabled={uploading || !cookieText.trim()}>
          {uploading ? 'Installation...' : 'Installer les cookies'}
        </button>
      </div>
    </div>

    <!-- Config section -->
    <div class="card">
      <h2 class="section-title">Configuration</h2>

      <div class="form-group">
        <label class="form-label" for="format">Format video</label>
        <input id="format" type="text" bind:value={config.format} />
        <div class="presets">
          {#each formatPresets as preset}
            <button class="preset-btn" on:click={() => applyPreset(preset)}>{preset.label}</button>
          {/each}
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="search_limit">Limite resultats de recherche</label>
        <select id="search_limit" bind:value={config.search_limit}>
          <option value={3}>3</option>
          <option value={5}>5</option>
          <option value={8}>8</option>
          <option value={10}>10</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="search_timeout_s">Timeout recherche</label>
        <select id="search_timeout_s" bind:value={config.search_timeout_s}>
          <option value={10}>10 secondes</option>
          <option value={15}>15 secondes</option>
          <option value={20}>20 secondes</option>
          <option value={30}>30 secondes</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="vlc_volume">
          Volume VLC : {config.vlc_volume}
        </label>
        <input id="vlc_volume" type="range" bind:value={config.vlc_volume} min="0" max="512" step="10" />
        <div class="range-labels">
          <span>0</span>
          <span>512</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="network_cache_ms">Cache reseau (tampon AirPlay)</label>
        <select id="network_cache_ms" bind:value={config.network_cache_ms}>
          <option value={3000}>Faible latence (3s)</option>
          <option value={5000}>Normal (5s)</option>
          <option value={8000}>Stable (8s)</option>
          <option value={10000}>Max stabilite (10s)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="stop_timeout_s">Timeout arret</label>
        <select id="stop_timeout_s" bind:value={config.stop_timeout_s}>
          <option value={3}>3 secondes</option>
          <option value={5}>5 secondes</option>
          <option value={10}>10 secondes</option>
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
    color: #f0f0f0;
    margin-bottom: 16px;
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
    margin-bottom: 20px;
  }

  .cookies-card {
    border-color: rgba(108, 99, 255, 0.15);
  }

  /* Cookie status */
  .cookie-status {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
  }
  .cookie-status.ok {
    background: rgba(74, 222, 128, 0.08);
    color: #4ade80;
  }
  .cookie-status.warning {
    background: rgba(255, 170, 68, 0.08);
    color: #ffaa44;
  }
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .status-dot.ok { background: #4ade80; }
  .status-dot.warning { background: #ffaa44; }

  .btn-delete {
    margin-left: auto;
    background: none;
    border: 1px solid rgba(255, 107, 107, 0.3);
    color: #ff6b6b;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
  }

  /* Tutorial */
  .tuto {
    margin-bottom: 16px;
  }
  .tuto summary {
    cursor: pointer;
    color: #6c63ff;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 0;
  }
  .tuto-content {
    padding: 12px 0 4px;
    font-size: 13px;
    color: #aaa;
    line-height: 1.6;
  }
  .tuto-content ol {
    padding-left: 20px;
    margin: 8px 0;
  }
  .tuto-content li {
    margin-bottom: 6px;
  }
  .tuto-content a {
    color: #6c63ff;
    text-decoration: none;
  }
  .tuto-content a:hover {
    text-decoration: underline;
  }
  .tuto-content strong {
    color: #f0f0f0;
  }
  .tuto-alt {
    margin-top: 12px;
  }
  .tuto-code {
    display: block;
    background: #1a1a24;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    color: #b0abff;
    margin: 6px 0;
    word-break: break-all;
  }
  .tuto-note {
    font-size: 12px;
    color: #666;
    margin-top: 4px;
  }

  /* Upload area */
  .cookie-upload {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .upload-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .file-btn {
    background: #1a1a24;
    border: 1px solid #333;
    color: #888;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
  }
  .file-btn:hover {
    border-color: #6c63ff;
    color: #6c63ff;
  }
  .upload-or {
    font-size: 12px;
    color: #555;
  }

  .cookie-textarea {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 12px;
    font-family: monospace;
    resize: vertical;
    min-height: 80px;
  }
  .cookie-textarea:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .btn-upload {
    background: #6c63ff;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    align-self: flex-start;
  }
  .btn-upload:hover { opacity: 0.9; }
  .btn-upload:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Form (existing) */
  .form-group { margin-bottom: 20px; }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  input[type="text"], select {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  input:focus, select:focus {
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

  .presets {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }

  .preset-btn {
    background: #1a1a24;
    border: 1px solid #333;
    color: #888;
    padding: 4px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.15s, color 0.15s;
  }

  .preset-btn:hover {
    border-color: #6c63ff;
    color: #6c63ff;
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
