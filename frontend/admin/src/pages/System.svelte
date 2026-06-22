<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPost, apiPut, showToast } from '../stores/auth.js';

  let system = null;
  let loading = true;
  // Each entry mirrors the pinned GET /admin/api/env shape:
  //   { key, value, masked, is_secret, has_value }
  // For secrets, `value` always arrives empty (the real secret is never sent).
  // `input` holds whatever the admin types; for secrets it stays "" unless edited.
  let envEntries = [];
  let envContent = '';
  let savingEnv = false;
  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let savingPassword = false;
  let showRebootConfirm = false;
  let viewMode = 'structured'; // 'structured' or 'raw'

  // Build the raw-view textarea. Secrets are NEVER injected in clear text:
  // they show their masked (info-only) representation as a comment so the admin
  // can see they exist, but that line is not re-submitted as a value.
  function entriesToRawView() {
    return envEntries.map(e => {
      if (e.is_secret) {
        const shown = e.has_value ? (e.masked || '********') : '(non défini)';
        return `# ${e.key}=${shown}  (secret, non éditable ici — utiliser la vue Structure)`;
      }
      return `${e.key}=${e.value ?? ''}`;
    }).join('\n');
  }

  onMount(async () => {
    const data = await apiGet('/admin/api/system');
    if (data) system = data;
    const envData = await apiGet('/admin/api/env');
    if (envData && Array.isArray(envData.env)) {
      envEntries = envData.env.map(e => ({
        key: e.key,
        value: e.value || '',          // secrets arrive as ""
        masked: e.masked || '',
        is_secret: !!e.is_secret,
        has_value: !!e.has_value,
        // `input` is the editable buffer. Non-secret: prefilled with real value.
        // Secret: always starts empty (write-only) — never holds the real secret.
        input: e.is_secret ? '' : (e.value || ''),
      }));
      envContent = entriesToRawView();
    }
    loading = false;
  });

  async function restartBackend() {
    const res = await apiPost('/admin/api/system/restart-backend', {});
    if (res.ok) {
      showToast('Backend en cours de redemarrage...', 'success');
    } else {
      showToast('Erreur lors du redemarrage', 'error');
    }
  }

  async function rebootPi() {
    showRebootConfirm = false;
    const res = await apiPost('/admin/api/system/reboot', {});
    if (res.ok) {
      showToast('Redemarrage du Pi en cours...', 'success');
    } else {
      showToast('Erreur lors du redemarrage', 'error');
    }
  }

  async function saveEnv() {
    savingEnv = true;
    // Build the payload from the structured entries (the raw view is read-only
    // for secrets and is only a mirror, so we never derive the payload from it).
    // Pinned PUT contract: an entry with is_secret=true AND value="" is IGNORED
    // (the on-disk secret is preserved). So for a secret we send a non-empty
    // `value` ONLY when the admin actually typed a new one; otherwise value="".
    const payload = envEntries.map(e => {
      if (e.is_secret) {
        const typed = (e.input || '').trim();
        return {
          key: e.key,
          is_secret: true,
          // typed something -> new secret; nothing typed -> "" -> preserved
          value: typed ? e.input : '',
        };
      }
      return { key: e.key, is_secret: false, value: e.input ?? '' };
    });
    const res = await apiPut('/admin/api/env', { entries: payload });
    savingEnv = false;
    if (res.ok) {
      // Reflect newly-saved secrets locally: a typed secret now "has_value",
      // and the input is cleared back to write-only empty state.
      envEntries = envEntries.map(e => {
        if (e.is_secret && (e.input || '').trim()) {
          return { ...e, input: '', value: '', has_value: true };
        }
        if (!e.is_secret) {
          return { ...e, value: e.input ?? '', has_value: !!(e.input && e.input.length) };
        }
        return e;
      });
      envContent = entriesToRawView();
      showToast('Fichier .env sauvegarde', 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }

  function switchViewMode(mode) {
    if (mode === viewMode) return;
    // Refresh the raw view from the structured entries (secrets stay masked,
    // never in clear text). The raw view is display-only for secrets.
    if (mode === 'raw') {
      envContent = entriesToRawView();
    }
    viewMode = mode;
  }

  async function changePassword() {
    if (!currentPassword) {
      showToast('Veuillez entrer le mot de passe actuel', 'error');
      return;
    }
    if (!newPassword || newPassword.length < 4) {
      showToast('Le mot de passe doit faire au moins 4 caracteres', 'error');
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast('Les mots de passe ne correspondent pas', 'error');
      return;
    }
    savingPassword = true;
    const res = await apiPost('/admin/api/password', { current: currentPassword, new: newPassword });
    savingPassword = false;
    if (res.ok) {
      showToast('Mot de passe modifie', 'success');
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
    } else {
      showToast('Erreur lors du changement', 'error');
    }
  }

  function formatUptime(seconds) {
    if (!seconds) return '-';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}j ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }
</script>

<div class="page">
  <h1 class="page-title">Systeme</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <!-- System Info -->
    <div class="card">
      <h2 class="section-title">Informations systeme</h2>
      {#if system}
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Hostname</span>
            <span class="info-value">{system.hostname || '-'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">IP</span>
            <span class="info-value">{system.ip || '-'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">CPU Temp</span>
            <span class="info-value">{system.cpu_temp != null ? `${system.cpu_temp.toFixed(1)} C` : '-'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">RAM</span>
            <span class="info-value">{system.memory?.percent != null ? `${system.memory.percent.toFixed(0)}%` : '-'} ({system.memory?.used_mb || '-'} / {system.memory?.total_mb || '-'} MB)</span>
          </div>
          <div class="info-item">
            <span class="info-label">Disque</span>
            <span class="info-value">{system.disk?.percent != null ? `${system.disk.percent.toFixed(0)}%` : '-'} ({system.disk?.used_gb || '-'} / {system.disk?.total_gb || '-'} GB)</span>
          </div>
          <div class="info-item">
            <span class="info-label">Uptime</span>
            <span class="info-value">{formatUptime(system.uptime?.seconds)}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Python</span>
            <span class="info-value">{system.python_version || '-'}</span>
          </div>
          <div class="info-item">
            <span class="info-label">OS</span>
            <span class="info-value">{system.os_version || '-'}</span>
          </div>
        </div>
      {:else}
        <p style="color: #888;">Informations non disponibles.</p>
      {/if}
    </div>

    <!-- Actions -->
    <div class="card">
      <h2 class="section-title">Actions</h2>
      <div class="actions-row">
        <button class="btn-action" on:click={restartBackend}>
          Redemarrer le backend
        </button>
        <button class="btn-action btn-danger" on:click={() => showRebootConfirm = true}>
          Redemarrer le Pi
        </button>
      </div>

      {#if showRebootConfirm}
        <div class="confirm-box">
          <p>Etes-vous sur de vouloir redemarrer le Raspberry Pi ?</p>
          <div class="confirm-actions">
            <button class="btn-action btn-danger" on:click={rebootPi}>Confirmer</button>
            <button class="btn-action" on:click={() => showRebootConfirm = false}>Annuler</button>
          </div>
        </div>
      {/if}
    </div>

    <!-- Env Editor -->
    <div class="card">
      <div class="env-header">
        <h2 class="section-title" style="margin-bottom: 0;">Variables d'environnement (.env)</h2>
        <div class="view-toggle">
          <button class="toggle-btn" class:active={viewMode === 'structured'} on:click={() => switchViewMode('structured')}>
            Structure
          </button>
          <button class="toggle-btn" class:active={viewMode === 'raw'} on:click={() => switchViewMode('raw')}>
            Brut
          </button>
        </div>
      </div>

      {#if viewMode === 'structured'}
        <div class="env-structured">
          {#each envEntries as entry, i}
            <div class="env-row">
              <div class="env-key">{entry.key}</div>
              <div class="env-value-row">
                {#if entry.is_secret}
                  <!-- WRITE-ONLY: the real secret is never sent to the front.
                       The input stays empty; typing here sets a NEW secret.
                       Leaving it empty preserves the on-disk value. -->
                  <input
                    type="password"
                    class="env-input"
                    bind:value={envEntries[i].input}
                    placeholder={entry.has_value ? '(inchangé)' : '(non défini)'}
                    autocomplete="new-password"
                  />
                  <span class="secret-badge" title="Valeur masquée. Laisser vide pour conserver le secret actuel.">
                    secret{entry.has_value ? ' • défini' : ' • vide'}
                  </span>
                {:else}
                  <input
                    type="text"
                    class="env-input"
                    bind:value={envEntries[i].input}
                    placeholder="(vide)"
                  />
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="form-group">
          <!-- Raw view is read-only: secrets are shown masked (info only) and are
               never re-submitted from here. Editing happens in the Structure view. -->
          <textarea class="env-editor" bind:value={envContent} rows="15" spellcheck="false" readonly></textarea>
          <p class="env-raw-note">Vue brute en lecture seule. Les secrets sont masqués et non modifiables ici — utilisez la vue Structure.</p>
        </div>
      {/if}

      <button class="btn-save" on:click={saveEnv} disabled={savingEnv}>
        {savingEnv ? 'Sauvegarde...' : 'Sauvegarder .env'}
      </button>
    </div>

    <!-- Password Change -->
    <div class="card">
      <h2 class="section-title">Changer le mot de passe</h2>
      <div class="form-group">
        <label class="form-label" for="current_password">Mot de passe actuel</label>
        <input id="current_password" type="password" bind:value={currentPassword} placeholder="Mot de passe actuel" />
      </div>
      <div class="form-group">
        <label class="form-label" for="new_password">Nouveau mot de passe</label>
        <input id="new_password" type="password" bind:value={newPassword} placeholder="Minimum 4 caracteres" />
      </div>
      <div class="form-group">
        <label class="form-label" for="confirm_password">Confirmer le mot de passe</label>
        <input id="confirm_password" type="password" bind:value={confirmPassword} placeholder="Retapez le mot de passe" />
      </div>
      <button class="btn-save" on:click={changePassword} disabled={savingPassword}>
        {savingPassword ? 'Modification...' : 'Modifier le mot de passe'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 700px; }

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

  .info-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .info-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .info-label {
    font-size: 11px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .info-value {
    font-size: 14px;
    color: #f0f0f0;
    font-family: 'JetBrains Mono', monospace;
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

  .btn-danger {
    border-color: rgba(255, 107, 107, 0.3);
    color: #ff6b6b;
  }

  .btn-danger:hover {
    border-color: #ff6b6b;
  }

  .confirm-box {
    margin-top: 16px;
    padding: 16px;
    background: rgba(255, 107, 107, 0.08);
    border: 1px solid rgba(255, 107, 107, 0.2);
    border-radius: 8px;
  }

  .confirm-box p {
    margin-bottom: 12px;
    font-size: 14px;
    color: #ff6b6b;
  }

  .confirm-actions {
    display: flex;
    gap: 8px;
  }

  /* Env editor */
  .env-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .view-toggle {
    display: flex;
    gap: 2px;
    background: #0a0a0f;
    border-radius: 6px;
    padding: 2px;
  }

  .toggle-btn {
    background: none;
    border: none;
    color: #666;
    padding: 5px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    transition: background 0.15s, color 0.15s;
  }

  .toggle-btn.active {
    background: #1a1a24;
    color: #f0f0f0;
  }

  .toggle-btn:hover:not(.active) {
    color: #888;
  }

  .env-structured {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 16px;
    max-height: 500px;
    overflow-y: auto;
  }

  .env-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
  }

  .env-key {
    font-size: 12px;
    color: #6c63ff;
    font-family: 'JetBrains Mono', monospace;
    min-width: 200px;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .env-value-row {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;
  }

  .env-input {
    background: #0a0a0f;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    width: 100%;
    min-width: 0;
  }

  .env-input:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .secret-badge {
    flex-shrink: 0;
    font-size: 10px;
    color: #888;
    background: rgba(108, 99, 255, 0.12);
    border: 1px solid rgba(108, 99, 255, 0.25);
    border-radius: 4px;
    padding: 3px 6px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    white-space: nowrap;
    font-family: 'Inter', sans-serif;
  }

  .env-raw-note {
    margin-top: 8px;
    font-size: 12px;
    color: #777;
  }

  .form-group { margin-bottom: 20px; }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  input[type="password"] {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  input:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .env-editor {
    background: #0a0a0f;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
    width: 100%;
    font-family: 'JetBrains Mono', monospace;
    resize: vertical;
    min-height: 200px;
    line-height: 1.6;
  }

  .env-editor:focus {
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

  @media (max-width: 768px) {
    .info-grid {
      grid-template-columns: 1fr;
    }

    .env-row {
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    .env-key {
      min-width: 0;
    }

    .env-value-row {
      width: 100%;
    }
  }
</style>
