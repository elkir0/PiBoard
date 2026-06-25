<script>
  import { onMount } from 'svelte';
  import { apiDelete, apiGet, apiPost, apiUpload, showToast } from '../stores/auth.js';

  export let onBack = () => {};

  let loading = true;
  let jobs = [];
  let activeJob = null;
  let modelStatus = null;
  let creating = false;
  let packaging = false;
  let recordingKind = null;
  let countdown = 0;
  let uploadFile = null;
  let uploading = false;
  let installing = false;
  let restarting = false;
  let packageUrl = '';
  let positiveLabel = 'normal';
  let backgroundLabel = 'salon calme';
  let negativeLabel = 'terminal';

  const categories = [
    {
      kind: 'positive',
      title: 'Wakeword',
      target: 20,
      duration: 3,
      labelField: 'positive',
      action: 'Enregistrer terminator',
      hint: 'Varier distance, volume et intonation.',
    },
    {
      kind: 'background',
      title: 'Bruit de fond',
      target: 6,
      duration: 6,
      labelField: 'background',
      action: 'Enregistrer la piece',
      hint: 'Salon calme, musique, TV, ventilation, voix loin du micro.',
    },
    {
      kind: 'negative',
      title: 'Faux declencheurs',
      target: 12,
      duration: 3,
      labelField: 'negative',
      action: 'Enregistrer un negatif',
      hint: 'Mots proches ou commandes courantes qui ne doivent pas reveiller.',
    },
  ];

  const negativeSuggestions = [
    'terminal',
    'terminer',
    'terminus',
    'ordinateur',
    'generateur',
    'exterminateur',
    'mets la musique',
    'arrete la musique',
  ];

  $: canPackage = activeJob && count('positive') >= 3 && count('background') >= 1;
  $: currentDownloadUrl = packageUrl || activeJob?.package?.download_url || '';
  $: installed = activeJob?.status === 'installed' || !!activeJob?.installed;

  function samples(kind) {
    return activeJob?.samples?.[kind] || [];
  }

  function count(kind) {
    return samples(kind).length;
  }

  function progress(kind, target) {
    return Math.min(100, Math.round((count(kind) / target) * 100));
  }

  function labelFor(kind) {
    if (kind === 'positive') return positiveLabel;
    if (kind === 'background') return backgroundLabel;
    return negativeLabel;
  }

  async function loadAll(preferId = null) {
    const [status, list] = await Promise.all([
      apiGet('/admin/api/wakeword/model-status'),
      apiGet('/admin/api/wakeword/jobs'),
    ]);
    if (status) modelStatus = status;
    if (list) {
      jobs = list.jobs || [];
      activeJob = jobs.find(j => j.id === preferId) || jobs[0] || null;
      packageUrl = activeJob?.package?.download_url || '';
    }
    if (!activeJob) await createJob();
    loading = false;
  }

  async function refreshJob() {
    if (!activeJob) return;
    const data = await apiGet(`/admin/api/wakeword/jobs/${activeJob.id}`);
    if (data) {
      activeJob = data;
      packageUrl = activeJob?.package?.download_url || packageUrl;
    }
    const status = await apiGet('/admin/api/wakeword/model-status');
    if (status) modelStatus = status;
  }

  async function createJob() {
    creating = true;
    const res = await apiPost('/admin/api/wakeword/jobs', { wakeword: 'terminator' });
    creating = false;
    if (res.ok && res.data) {
      activeJob = res.data;
      packageUrl = '';
      await loadAll(activeJob.id);
    } else {
      showToast('Impossible de creer le dossier wakeword', 'error');
    }
  }

  async function selectJob(jobId) {
    const data = await apiGet(`/admin/api/wakeword/jobs/${jobId}`);
    if (data) {
      activeJob = data;
      packageUrl = activeJob?.package?.download_url || '';
    }
  }

  async function record(kind, duration) {
    if (!activeJob || recordingKind) return;
    recordingKind = kind;
    countdown = 3;
    for (let i = 3; i > 0; i--) {
      countdown = i;
      await new Promise(r => setTimeout(r, 1000));
    }
    countdown = 0;
    const res = await apiPost(`/admin/api/wakeword/jobs/${activeJob.id}/record`, {
      kind,
      duration_s: duration,
      label: labelFor(kind),
    });
    recordingKind = null;
    if (res.ok && res.data) {
      activeJob = res.data.job;
      const sample = res.data.sample;
      showToast(sample.good ? `Echantillon OK (RMS ${sample.rms})` : `Echantillon faible (RMS ${sample.rms})`, sample.good ? 'success' : 'error');
    } else {
      showToast('Erreur pendant l enregistrement', 'error');
    }
  }

  async function deleteSample(kind, filename) {
    if (!activeJob) return;
    const res = await apiDelete(`/admin/api/wakeword/jobs/${activeJob.id}/samples/${kind}/${encodeURIComponent(filename)}`);
    if (res.ok) {
      showToast('Echantillon supprime', 'success');
      await refreshJob();
    } else {
      showToast('Suppression impossible', 'error');
    }
  }

  async function buildPackage() {
    if (!activeJob) return;
    packaging = true;
    const res = await apiPost(`/admin/api/wakeword/jobs/${activeJob.id}/package`, {});
    packaging = false;
    if (res.ok && res.data) {
      packageUrl = res.data.download_url;
      showToast('Pack Mac pret', 'success');
      await refreshJob();
    } else {
      showToast('Generation du pack impossible', 'error');
    }
  }

  function onUploadChange(event) {
    uploadFile = event.currentTarget.files?.[0] || null;
  }

  async function uploadModel() {
    if (!activeJob || !uploadFile) return;
    uploading = true;
    const res = await apiUpload(`/admin/api/wakeword/jobs/${activeJob.id}/upload`, uploadFile);
    uploading = false;
    if (res.ok && res.data) {
      activeJob = res.data.job;
      showToast('Modele ONNX valide', 'success');
      await refreshJob();
    } else {
      showToast('Modele ONNX refuse', 'error');
    }
  }

  async function installModel(activate = true) {
    if (!activeJob) return;
    installing = true;
    const res = await apiPost(`/admin/api/wakeword/jobs/${activeJob.id}/install`, { activate });
    installing = false;
    if (res.ok) {
      showToast(activate ? 'V2 installee et selectionnee' : 'V2 installee', 'success');
      await refreshJob();
    } else {
      showToast('Installation impossible', 'error');
    }
  }

  async function restartBackend() {
    restarting = true;
    const res = await apiPost('/admin/api/system/restart-backend', {});
    restarting = false;
    if (res.ok) showToast('Backend en cours de redemarrage...', 'success');
    else showToast('Redemarrage impossible', 'error');
  }

  onMount(() => loadAll());
</script>

<div class="page">
  <div class="page-header">
    <div>
      <h1 class="page-title">Configurer le Wakeword</h1>
      <p class="page-subtitle">LiveKit V2 pour le modele terminator</p>
    </div>
    <button class="btn-secondary" on:click={onBack}>Retour</button>
  </div>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else if !activeJob}
    <section class="card">
      <h2>Dossier wakeword indisponible</h2>
      <p>La creation automatique a echoue. Relancez la creation ou verifiez les logs backend.</p>
      <button class="btn-primary retry-btn" on:click={createJob} disabled={creating}>
        {creating ? 'Creation...' : 'Creer un dossier'}
      </button>
    </section>
  {:else}
    <div class="status-strip">
      <div>
        <span class="status-label">Modele actif</span>
        <strong>{modelStatus?.active || 'terminator_v1'}</strong>
      </div>
      <div>
        <span class="status-label">V2 sur le Pi</span>
        <strong class:ok={modelStatus?.v2_exists}>{modelStatus?.v2_exists ? 'installee' : 'absente'}</strong>
      </div>
      <div>
        <span class="status-label">Dossier</span>
        <select bind:value={activeJob.id} on:change={(e) => selectJob(e.currentTarget.value)}>
          {#each jobs as job}
            <option value={job.id}>{job.id} · {job.status}</option>
          {/each}
        </select>
      </div>
      <button class="btn-secondary" on:click={createJob} disabled={creating}>
        {creating ? 'Creation...' : 'Nouveau dossier'}
      </button>
    </div>

    <div class="grid">
      {#each categories as category}
        <section class="card">
          <div class="card-head">
            <div>
              <h2>{category.title}</h2>
              <p>{category.hint}</p>
            </div>
            <div class="count">{count(category.kind)} / {category.target}</div>
          </div>

          <div class="meter"><span style="width: {progress(category.kind, category.target)}%"></span></div>

          <div class="record-row">
            {#if category.kind === 'positive'}
              <input aria-label="label positif" bind:value={positiveLabel} />
            {:else if category.kind === 'background'}
              <input aria-label="label bruit de fond" bind:value={backgroundLabel} />
            {:else}
              <select aria-label="label negatif" bind:value={negativeLabel}>
                {#each negativeSuggestions as item}
                  <option value={item}>{item}</option>
                {/each}
              </select>
            {/if}
            <button class="btn-record" on:click={() => record(category.kind, category.duration)} disabled={!!recordingKind}>
              {#if recordingKind === category.kind}
                {countdown > 0 ? `${countdown}...` : 'Enregistrement...'}
              {:else}
                {category.action}
              {/if}
            </button>
          </div>

          <div class="sample-list">
            {#if samples(category.kind).length === 0}
              <div class="empty">Aucun echantillon</div>
            {:else}
              {#each samples(category.kind) as sample}
                <div class="sample-row" class:bad={!sample.good}>
                  <span class="sample-name">{sample.label || sample.file}</span>
                  <span class="sample-meta">RMS {sample.rms} · {sample.duration_s}s</span>
                  <button class="btn-icon" title="Supprimer" on:click={() => deleteSample(category.kind, sample.file)}>x</button>
                </div>
              {/each}
            {/if}
          </div>
        </section>
      {/each}
    </div>

    <section class="card transfer-card">
      <div class="transfer-step">
        <span class="step-num">1</span>
        <div>
          <h2>Preparer le pack Mac</h2>
          <p>Minimum technique: 3 wakewords et 1 bruit de fond. Pour un bon modele, viser les compteurs ci-dessus.</p>
        </div>
        <button class="btn-primary" on:click={buildPackage} disabled={!canPackage || packaging}>
          {packaging ? 'Preparation...' : 'Construire le pack'}
        </button>
      </div>

      {#if currentDownloadUrl}
        <div class="url-box">
          <span>{currentDownloadUrl}</span>
          <a class="btn-secondary" href={currentDownloadUrl}>Telecharger</a>
        </div>
      {/if}

      <div class="transfer-step">
        <span class="step-num">2</span>
        <div>
          <h2>Recevoir le modele entraine</h2>
          <p>Uploader le fichier `terminator_livekit_v2.onnx` produit sur le Mac.</p>
        </div>
        <div class="upload-row">
          <input type="file" accept=".onnx" on:change={onUploadChange} />
          <button class="btn-primary" on:click={uploadModel} disabled={!uploadFile || uploading}>
            {uploading ? 'Validation...' : 'Uploader ONNX'}
          </button>
        </div>
      </div>

      <div class="transfer-step">
        <span class="step-num">3</span>
        <div>
          <h2>Installer et activer V2</h2>
          <p>Le fichier V1 reste en place. Apres activation, redemarrer le backend pour charger le nouveau modele.</p>
        </div>
        <div class="install-actions">
          <button class="btn-primary" on:click={() => installModel(true)} disabled={installing || !activeJob?.upload}>
            {installing ? 'Installation...' : 'Installer + activer V2'}
          </button>
          {#if installed}
            <button class="btn-secondary" on:click={restartBackend} disabled={restarting}>
              {restarting ? 'Redemarrage...' : 'Redemarrer backend'}
            </button>
          {/if}
        </div>
      </div>
    </section>
  {/if}
</div>

<style>
  .page {
    max-width: 1120px;
  }

  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 20px;
  }

  .page-title {
    font-size: 24px;
    font-weight: 700;
    margin: 0 0 4px;
  }

  .page-subtitle {
    margin: 0;
    color: #888;
    font-size: 13px;
  }

  .loading {
    color: #888;
    padding: 40px;
    text-align: center;
  }

  .status-strip {
    display: grid;
    grid-template-columns: 1fr 1fr 2fr auto;
    gap: 12px;
    align-items: end;
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
  }

  .status-label {
    display: block;
    color: #777;
    font-size: 11px;
    margin-bottom: 4px;
    text-transform: uppercase;
  }

  strong {
    color: #f0f0f0;
    font-size: 14px;
  }

  strong.ok {
    color: #4ade80;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }

  .card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
  }

  .card-head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    min-height: 76px;
  }

  h2 {
    margin: 0 0 6px;
    color: #ddd;
    font-size: 16px;
    font-weight: 650;
  }

  p {
    margin: 0;
    color: #85858d;
    font-size: 12px;
    line-height: 1.45;
  }

  .count {
    color: #6c63ff;
    font-weight: 700;
    white-space: nowrap;
  }

  .meter {
    height: 6px;
    background: #1a1a24;
    border-radius: 999px;
    overflow: hidden;
    margin: 10px 0 16px;
  }

  .meter span {
    display: block;
    height: 100%;
    background: #6c63ff;
    border-radius: inherit;
    transition: width 0.2s ease;
  }

  .record-row {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin-bottom: 14px;
  }

  .sample-list {
    display: grid;
    gap: 6px;
    max-height: 260px;
    overflow: auto;
  }

  .empty {
    color: #666;
    font-size: 13px;
    padding: 10px 0;
  }

  .sample-row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 8px;
    align-items: center;
    padding: 8px;
    background: #171720;
    border-radius: 8px;
  }

  .sample-row.bad {
    opacity: 0.55;
  }

  .sample-name {
    color: #ddd;
    font-size: 12px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sample-meta {
    color: #888;
    font-size: 11px;
    white-space: nowrap;
  }

  .transfer-card {
    margin-top: 16px;
    display: grid;
    gap: 16px;
  }

  .transfer-step {
    display: grid;
    grid-template-columns: 34px minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
  }

  .step-num {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: #1a1a24;
    color: #6c63ff;
    font-weight: 700;
  }

  .url-box {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
    background: #09090f;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 12px;
  }

  .url-box span {
    color: #ddd;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .upload-row,
  .install-actions {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: flex-end;
  }

  input,
  select {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 13px;
    min-width: 0;
    font-family: 'Inter', sans-serif;
  }

  input:focus,
  select:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .btn-primary,
  .btn-secondary,
  .btn-record {
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    white-space: nowrap;
    transition: opacity 0.15s, background 0.15s;
  }

  .btn-primary {
    background: #6c63ff;
    color: white;
    padding: 10px 16px;
  }

  .btn-secondary {
    background: #1a1a24;
    color: #e6e6ef;
    border: 1px solid rgba(255,255,255,0.08);
    padding: 9px 14px;
    text-decoration: none;
  }

  .btn-record {
    background: #ef4444;
    color: white;
    padding: 10px 14px;
  }

  button:hover,
  a:hover {
    opacity: 0.9;
  }

  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .btn-icon {
    background: none;
    border: none;
    color: #777;
    cursor: pointer;
    padding: 4px;
  }

  .btn-icon:hover {
    color: #f87171;
  }

  .retry-btn {
    margin-top: 16px;
  }

  @media (max-width: 1100px) {
    .grid {
      grid-template-columns: 1fr;
    }

    .status-strip,
    .transfer-step {
      grid-template-columns: 1fr;
    }

    .upload-row,
    .install-actions {
      justify-content: flex-start;
      flex-wrap: wrap;
    }
  }
</style>
