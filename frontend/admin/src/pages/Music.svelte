<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  let provider = 'deezer';
  let quality = 'FLAC';
  let arlMasked = '';     // affichage masque du token actuel
  let arlNew = '';        // nouveau token colle (vide = inchange)
  let hasArl = false;
  let status = '...';     // ok | auth_required | no_credentials | not_connected
  let loading = true;
  let saving = false;
  let restarting = false;

  const STATUS = {
    ok:            { txt: 'Connecte a Deezer', cls: 'ok' },
    auth_required: { txt: "Token ARL expire ou invalide — collez-en un nouveau", cls: 'err' },
    no_credentials:{ txt: 'Aucun token ARL configure', cls: 'warn' },
    not_connected: { txt: 'Non connecte', cls: 'warn' },
  };

  async function loadStatus() {
    try {
      const r = await fetch('/api/spotify/status');
      const d = await r.json();
      status = d.status || '?';
    } catch { status = '?'; }
  }

  onMount(async () => {
    const env = await apiGet('/admin/api/env');
    const map = {};
    (env?.env || []).forEach(e => { map[e.key] = e; });
    // Cles non secretes : value contient la vraie valeur.
    provider = map.MUSIC_PROVIDER?.value || 'deezer';
    quality = map.DEEZER_QUALITY?.value || 'FLAC';
    // Cle SECRETE (ARL) : la valeur en clair n'est JAMAIS renvoyee (value="").
    // On s'appuie uniquement sur has_value / masked, jamais sur value.
    arlMasked = map.DEEZER_ARL?.masked || '';
    hasArl = !!(map.DEEZER_ARL?.has_value);
    await loadStatus();
    loading = false;
  });

  async function refreshArl() {
    // Recharge l'etat ARL depuis le backend (source de verite) sans
    // jamais lire la valeur en clair : on n'utilise que masked / has_value.
    try {
      const env = await apiGet('/admin/api/env');
      const arl = (env?.env || []).find(e => e.key === 'DEEZER_ARL');
      arlMasked = arl?.masked || '';
      hasArl = !!(arl?.has_value);
    } catch { /* garde l'etat courant si la relecture echoue */ }
  }

  async function save() {
    saving = true;
    // Cles non secretes : envoyees normalement.
    const entries = [
      { key: 'MUSIC_PROVIDER', is_secret: false, value: provider },
      { key: 'DEEZER_QUALITY', is_secret: false, value: quality },
    ];
    // Cle SECRETE (contrat PUT pinne : une entree is_secret=true + value="" est
    // IGNOREE, le secret sur disque est preserve). On envoie donc DEEZER_ARL
    // avec value=nouveau token si l'admin en a saisi un, sinon value="".
    const newArl = arlNew.trim();
    entries.push({ key: 'DEEZER_ARL', is_secret: true, value: newArl ? arlNew : '' });
    const res = await apiPut('/admin/api/env', { entries });
    saving = false;
    if (res && res.ok) {
      showToast('Enregistre. Redemarrez le backend pour appliquer.', 'success');
      if (newArl) {
        arlNew = '';
        // Relit l'etat reel (masked/has_value) plutot que d'inventer un masque.
        await refreshArl();
      }
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }

  async function restart() {
    restarting = true;
    await apiPost('/admin/api/system/restart-backend', {});
    showToast('Redemarrage du backend... (~15s)', 'success');
    setTimeout(async () => { await loadStatus(); restarting = false; }, 16000);
  }
</script>

<div class="page">
  <h1 class="page-title">Musique</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="card">
      <div class="status-row {STATUS[status]?.cls || 'warn'}">
        <span class="dot"></span>
        <span>{STATUS[status]?.txt || ('Statut : ' + status)}</span>
      </div>

      <div class="form-group">
        <label class="form-label" for="provider">Source musicale</label>
        <select id="provider" bind:value={provider}>
          <option value="deezer">Deezer (recommande)</option>
          <option value="spotify">Spotify (necessite Premium + librespot)</option>
        </select>
        <div class="form-hint">Changer de source necessite un redemarrage du backend.</div>
      </div>

      {#if provider === 'deezer'}
        <div class="form-group">
          <label class="form-label" for="quality">Qualite audio Deezer</label>
          <select id="quality" bind:value={quality}>
            <option value="FLAC">FLAC sans perte (recommande)</option>
            <option value="MP3_320">MP3 320 kbps</option>
            <option value="MP3_128">MP3 128 kbps</option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label" for="arl">Token ARL Deezer {hasArl ? '(actuel : ' + arlMasked + ')' : ''}</label>
          <textarea id="arl" rows="3" bind:value={arlNew}
            placeholder={hasArl ? 'Collez un nouveau token pour le remplacer...' : 'Collez votre token ARL ici...'}></textarea>
          <div class="form-hint">
            deezer.com (connecte) &rarr; F12 &rarr; Application &rarr; Cookies &rarr; copiez la valeur du cookie <b>arl</b> (~192 caracteres).
          </div>
        </div>
      {/if}

      <div class="actions">
        <button class="btn-save" on:click={save} disabled={saving}>
          {saving ? 'Sauvegarde...' : 'Enregistrer'}
        </button>
        <button class="btn-restart" on:click={restart} disabled={restarting}>
          {restarting ? 'Redemarrage...' : 'Redemarrer le backend'}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 600px; }
  .page-title { font-size: 22px; font-weight: 700; margin-bottom: 24px; }
  .loading { color: #888; padding: 40px; text-align: center; }
  .card { background: #111118; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 24px; }
  .form-group { margin-bottom: 20px; }
  .form-label { font-size: 13px; color: #888; margin-bottom: 6px; display: block; }
  .form-hint { font-size: 11px; color: #666; margin-top: 4px; }
  select, textarea {
    background: #1a1a24; border: 1px solid #333; color: #f0f0f0;
    padding: 8px 12px; border-radius: 8px; font-size: 14px; width: 100%;
    font-family: 'Inter', sans-serif; box-sizing: border-box; resize: vertical;
  }
  select:focus, textarea:focus { border-color: #6c63ff; outline: none; }
  .status-row {
    display: flex; align-items: center; gap: 8px; font-size: 13px;
    padding: 10px 12px; border-radius: 8px; margin-bottom: 22px;
  }
  .status-row .dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .status-row.ok { background: rgba(34,197,94,0.12); color: #4ade80; }
  .status-row.ok .dot { background: #22c55e; }
  .status-row.err { background: rgba(239,68,68,0.12); color: #f87171; }
  .status-row.err .dot { background: #ef4444; }
  .status-row.warn { background: rgba(234,179,8,0.12); color: #facc15; }
  .status-row.warn .dot { background: #eab308; }
  .actions { display: flex; gap: 12px; flex-wrap: wrap; }
  .btn-save, .btn-restart {
    border: none; padding: 10px 24px; border-radius: 8px; cursor: pointer;
    font-size: 14px; font-family: 'Inter', sans-serif; font-weight: 500; transition: opacity 0.15s;
  }
  .btn-save { background: #6c63ff; color: white; }
  .btn-restart { background: #1a1a24; color: #f0f0f0; border: 1px solid #333; }
  .btn-save:hover, .btn-restart:hover { opacity: 0.9; }
  .btn-save:disabled, .btn-restart:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
