<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  export let onConfigureWakeword = () => {};

  let wakeword = {
    engine: 'livekit',
    name: 'terminator',
    livekit_model: 'terminator_v1',
    threshold: 0.42,
    cooldown_s: 10,
  };

  let stt = {
    language: 'fr',
    listen_duration_s: 7,
    rms_threshold: 200,
  };

  let tts = {
    provider: 'gateway',
    model: 'voxtral-mini-tts-latest',
    voice: 'en_paul_neutral',
    piper_voice_path: '/home/piboard/piboard/voices/fr_FR-siwis-medium.onnx',
  };

  let llm = {
    model: 'mistral-small-latest',
    max_tokens: 200,
    system_prompt: '',
  };

  let loading = true;
  let savingWakeword = false;
  let savingStt = false;
  let savingTts = false;
  let savingLlm = false;

  // Hotword training state
  let hotwordSamples = [];
  let hotwordInfo = {};
  let recording = false;
  let generating = false;
  let recordingCountdown = 0;
  let loadingSamples = false;

  const rmsPresets = [
    { label: 'Tres sensible', value: 300 },
    { label: 'Normal', value: 500 },
    { label: 'Bruyant', value: 800 },
    { label: 'Tres bruyant', value: 1200 },
  ];

  async function loadHotwordSamples() {
    loadingSamples = true;
    const data = await apiGet('/admin/api/hotword/samples');
    if (data) {
      hotwordSamples = data.samples || [];
      hotwordInfo = data;
    }
    loadingSamples = false;
  }

  async function recordSample() {
    recording = true;
    recordingCountdown = 3;

    // Countdown
    for (let i = 3; i > 0; i--) {
      recordingCountdown = i;
      await new Promise(r => setTimeout(r, 1000));
    }
    recordingCountdown = 0;

    showToast('Parlez maintenant !', 'success');
    const res = await apiPost('/admin/api/hotword/record', { duration_s: 3 });
    recording = false;

    if (res.ok && res.data) {
      const d = res.data;
      if (d.good) {
        showToast(`Echantillon enregistre (RMS=${d.rms})`, 'success');
      } else {
        showToast(`Trop faible (RMS=${d.rms}), reessayez plus fort`, 'error');
      }
      await loadHotwordSamples();
    } else {
      showToast('Erreur enregistrement', 'error');
    }
  }

  async function deleteSample(filename) {
    try {
      const base = import.meta.env.DEV ? 'http://localhost:8000' : '';
      const r = await fetch(`${base}/admin/api/hotword/sample/${encodeURIComponent(filename)}`, {
        method: 'DELETE', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      if (r.ok) {
        showToast('Echantillon supprime', 'success');
      } else {
        showToast('Erreur suppression', 'error');
      }
    } catch (e) {
      showToast('Erreur suppression', 'error');
    } finally {
      await loadHotwordSamples();
    }
  }

  async function deleteAllSamples() {
    try {
      const base = import.meta.env.DEV ? 'http://localhost:8000' : '';
      const r = await fetch(`${base}/admin/api/hotword/samples`, {
        method: 'DELETE', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      if (r.ok) {
        showToast('Tous les echantillons supprimes', 'success');
      } else {
        showToast('Erreur suppression', 'error');
      }
    } catch (e) {
      showToast('Erreur suppression', 'error');
    } finally {
      await loadHotwordSamples();
    }
  }

  async function generateReference() {
    generating = true;
    const res = await apiPost('/admin/api/hotword/generate', {});
    generating = false;

    if (res.ok && res.data) {
      showToast(`Reference generee (${res.data.embeddings_count} embeddings). Redemarrez le backend.`, 'success');
      await loadHotwordSamples();
    } else {
      showToast('Erreur generation reference', 'error');
    }
  }

  async function restartBackend() {
    const res = await apiPost('/admin/api/system/restart-backend', {});
    if (res.ok) {
      showToast('Backend en cours de redemarrage...', 'success');
    } else {
      showToast('Erreur lors du redemarrage', 'error');
    }
  }

  onMount(async () => {
    const data = await apiGet('/admin/api/config');
    if (data) {
      if (data.wakeword) wakeword = { ...wakeword, ...data.wakeword };
      if (data.stt) stt = { ...stt, ...data.stt };
      if (data.tts) tts = { ...tts, ...data.tts };
      if (data.llm) llm = { ...llm, ...data.llm };
    }
    loading = false;
    await loadHotwordSamples();
  });

  async function saveSection(section, sectionData, setLoading) {
    setLoading(true);
    const res = await apiPut(`/admin/api/config/${section}`, sectionData);
    setLoading(false);
    if (res.ok) {
      showToast(`Section "${section}" sauvegardee`, 'success');
    } else {
      showToast('Erreur lors de la sauvegarde', 'error');
    }
  }
</script>

<div class="page">
  <h1 class="page-title">Commandes vocales</h1>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <!-- Wake Word -->
    <div class="card">
      <h2 class="section-title">Mot de reveil</h2>

      <div class="form-group">
        <label class="form-label" for="ww_engine">Moteur</label>
        <select id="ww_engine" bind:value={wakeword.engine}>
          <option value="livekit">livekit-wakeword (V3, terminator)</option>
          <option value="oww">openWakeWord (modeles pre-entraines)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="ww_model">Mot-reveil</label>
        <select id="ww_model" bind:value={wakeword.name}>
          <option value="terminator">terminator</option>
          <option value="hey_jarvis">hey_jarvis</option>
          <option value="alexa">alexa</option>
          <option value="hey_mycroft">hey_mycroft</option>
        </select>
      </div>

      {#if wakeword.engine === 'livekit'}
        <div class="form-group">
          <label class="form-label" for="ww_livekit_model">Modele LiveKit</label>
          <select id="ww_livekit_model" bind:value={wakeword.livekit_model}>
            <option value="terminator_v1">Terminator v1</option>
            <option value="terminator_v2">Terminator v2</option>
          </select>
          <p class="hint">V2 utilise terminator_livekit_v2.onnx ; si le fichier est absent, le backend retombe sur V1.</p>
        </div>
        <button class="btn-trainer" on:click={onConfigureWakeword}>
          Configurer le Wakeword
        </button>
      {/if}

      <div class="form-group">
        <label class="form-label" for="ww_threshold">
          Seuil de detection : {wakeword.threshold.toFixed(2)}
        </label>
        <input id="ww_threshold" type="range" bind:value={wakeword.threshold} min="0.3" max="0.95" step="0.01" />
        <div class="range-labels">
          <span>0.30 (sensible)</span>
          <span>0.95 (strict)</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="ww_cooldown">Cooldown</label>
        <select id="ww_cooldown" bind:value={wakeword.cooldown_s}>
          <option value={5}>5 secondes</option>
          <option value={8}>8 secondes</option>
          <option value={10}>10 secondes</option>
          <option value={15}>15 secondes</option>
          <option value={20}>20 secondes</option>
        </select>
      </div>

      <button class="btn-save" on:click={() => saveSection('wakeword', wakeword, v => savingWakeword = v)} disabled={savingWakeword}>
        {savingWakeword ? 'Sauvegarde...' : 'Sauvegarder'}
      </button>
    </div>

    <!-- Hotword Training (EWN only) -->
    {#if wakeword.engine === 'ewn'}
    <div class="card">
      <h2 class="section-title">Entrainement vocal</h2>
      <p class="help-text">
        Enregistrez votre voix disant "{wakeword.name}" pour personnaliser la detection.
        Minimum 3 echantillons, idealement 5+.
      </p>

      <!-- Samples list -->
      <div class="samples-list">
        {#if loadingSamples}
          <div class="loading-small">Chargement...</div>
        {:else if hotwordSamples.length === 0}
          <div class="empty-state">Aucun echantillon enregistre</div>
        {:else}
          {#each hotwordSamples as sample, i}
            <div class="sample-row" class:sample-bad={!sample.good}>
              <div class="sample-info">
                <span class="sample-num">#{i + 1}</span>
                <div class="sample-bar-wrap">
                  <div class="sample-bar" style="width: {Math.min(100, sample.rms / 50)}%"
                       class:bar-good={sample.good} class:bar-bad={!sample.good}></div>
                </div>
                <span class="sample-rms">RMS {sample.rms}</span>
              </div>
              <button class="btn-delete-sample" on:click={() => deleteSample(sample.name)}>x</button>
            </div>
          {/each}
          <div class="samples-summary">
            {hotwordInfo.good_count || 0}/{hotwordInfo.sample_count || 0} valides
            {#if hotwordInfo.has_reference}
              — Reference active
            {/if}
          </div>
        {/if}
      </div>

      <!-- Record button -->
      <div class="training-actions">
        <button class="btn-record" on:click={recordSample} disabled={recording}>
          {#if recording}
            {#if recordingCountdown > 0}
              {recordingCountdown}...
            {:else}
              Parlez !
            {/if}
          {:else}
            Enregistrer "{wakeword.name}"
          {/if}
        </button>

        {#if hotwordSamples.length >= 3}
          <button class="btn-generate" on:click={generateReference} disabled={generating}>
            {generating ? 'Generation...' : 'Generer reference'}
          </button>
        {/if}
      </div>

      <!-- Actions -->
      <div class="training-footer">
        {#if hotwordSamples.length > 0}
          <button class="btn-text-danger" on:click={deleteAllSamples}>
            Supprimer tous les echantillons
          </button>
        {/if}
        {#if hotwordInfo.has_reference}
          <button class="btn-text" on:click={restartBackend}>
            Redemarrer le backend
          </button>
        {/if}
      </div>
    </div>
    {/if}

    <!-- STT -->
    <div class="card">
      <h2 class="section-title">Reconnaissance vocale (STT)</h2>

      <div class="form-group">
        <label class="form-label" for="stt_lang">Langue</label>
        <select id="stt_lang" bind:value={stt.language}>
          <option value="fr">Francais</option>
          <option value="en">English</option>
          <option value="es">Espanol</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="stt_duration">Duree d'ecoute</label>
        <select id="stt_duration" bind:value={stt.listen_duration_s}>
          <option value={5}>5 secondes</option>
          <option value={7}>7 secondes</option>
          <option value={8}>8 secondes</option>
          <option value={10}>10 secondes</option>
          <option value={12}>12 secondes</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label" for="stt_rms">Sensibilite micro</label>
        <select id="stt_rms" bind:value={stt.rms_threshold}>
          {#each rmsPresets as preset}
            <option value={preset.value}>{preset.label} ({preset.value})</option>
          {/each}
        </select>
      </div>

      <button class="btn-save" on:click={() => saveSection('stt', stt, v => savingStt = v)} disabled={savingStt}>
        {savingStt ? 'Sauvegarde...' : 'Sauvegarder'}
      </button>
    </div>

    <!-- TTS -->
    <div class="card">
      <h2 class="section-title">Synthese vocale (TTS)</h2>

      <div class="form-group">
        <label class="form-label" for="tts_provider">Moteur</label>
        <select id="tts_provider" bind:value={tts.provider}>
          <option value="gateway">Voxtral local (Mac mini) — gratuit</option>
          <option value="voxtral">Voxtral cloud (Mistral)</option>
          <option value="piper">Piper local (voix FR)</option>
        </select>
      </div>

      {#if tts.provider === 'voxtral' || tts.provider === 'gateway'}
        <div class="form-group">
          <label class="form-label" for="tts_voice">Voix (Voxtral)</label>
          <select id="tts_voice" bind:value={tts.voice}>
            <option value="en_paul_neutral">Paul (neutre)</option>
            <option value="fr_female">FR femme (Mac mini)</option>
          </select>
        </div>
      {/if}

      {#if tts.provider === 'piper'}
        <div class="form-group">
          <label class="form-label" for="tts_piper">Modele Piper (.onnx) — redemarrage requis</label>
          <input id="tts_piper" type="text" bind:value={tts.piper_voice_path} />
        </div>
      {/if}

      <button class="btn-save" on:click={() => saveSection('tts', tts, v => savingTts = v)} disabled={savingTts}>
        {savingTts ? 'Sauvegarde...' : 'Sauvegarder'}
      </button>
    </div>

    <!-- LLM -->
    <div class="card">
      <h2 class="section-title">Intelligence artificielle (LLM)</h2>

      <div class="form-group">
        <label class="form-label" for="llm_model">Modele</label>
        <select id="llm_model" bind:value={llm.model}>
          <option value="mistral-small-latest">Mistral Small</option>
          <option value="ministral-8b-latest">Ministral 8B (rapide)</option>
          <option value="mistral-large-latest">Mistral Large</option>
        </select>
        <p class="hint">Uniquement des modeles Mistral (le backend V3 utilise l'API Mistral).
          Le choix local/cloud (cerveau) et le moteur STT se reglent dans Systeme &rarr; .env.</p>
      </div>

      <div class="form-group">
        <label class="form-label" for="llm_tokens">Tokens max</label>
        <input id="llm_tokens" type="number" bind:value={llm.max_tokens} min="50" max="4096" step="50" />
      </div>

      <div class="form-group">
        <label class="form-label" for="llm_prompt">Prompt systeme</label>
        <textarea id="llm_prompt" bind:value={llm.system_prompt} rows="5" placeholder="Instructions pour l'assistant..."></textarea>
      </div>

      <button class="btn-save" on:click={() => saveSection('llm', llm, v => savingLlm = v)} disabled={savingLlm}>
        {savingLlm ? 'Sauvegarde...' : 'Sauvegarder'}
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

  .hint {
    font-size: 12px;
    color: #888;
    margin-top: 6px;
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

  input[type="number"], select, textarea {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  textarea {
    resize: vertical;
    min-height: 80px;
  }

  input:focus, select:focus, textarea:focus {
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

  .btn-trainer {
    width: 100%;
    background: #1a1a24;
    color: #f0f0f0;
    border: 1px solid rgba(108,99,255,0.45);
    padding: 11px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    margin: -4px 0 20px;
  }

  .btn-trainer:hover { border-color: #6c63ff; }

  /* Hotword training */
  .help-text {
    font-size: 13px;
    color: #888;
    margin-bottom: 16px;
    line-height: 1.5;
  }

  .samples-list { margin-bottom: 16px; }

  .loading-small, .empty-state {
    color: #666;
    font-size: 13px;
    padding: 12px 0;
    text-align: center;
  }

  .sample-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }

  .sample-bad { opacity: 0.5; }

  .sample-info {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
  }

  .sample-num {
    font-size: 12px;
    color: #666;
    width: 24px;
  }

  .sample-bar-wrap {
    flex: 1;
    height: 6px;
    background: #1a1a24;
    border-radius: 3px;
    overflow: hidden;
  }

  .sample-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
  }

  .bar-good { background: #4ade80; }
  .bar-bad { background: #f87171; }

  .sample-rms {
    font-size: 11px;
    color: #888;
    width: 60px;
    text-align: right;
  }

  .btn-delete-sample {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    font-size: 14px;
    padding: 4px 8px;
  }

  .btn-delete-sample:hover { color: #f87171; }

  .samples-summary {
    font-size: 12px;
    color: #888;
    padding: 8px 0 0;
  }

  .training-actions {
    display: flex;
    gap: 10px;
    margin-bottom: 12px;
  }

  .btn-record {
    background: #ef4444;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: opacity 0.15s;
    min-width: 160px;
  }

  .btn-record:hover { opacity: 0.9; }
  .btn-record:disabled { opacity: 0.6; cursor: not-allowed; }

  .btn-generate {
    background: #22c55e;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    transition: opacity 0.15s;
  }

  .btn-generate:hover { opacity: 0.9; }
  .btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }

  .training-footer {
    display: flex;
    gap: 16px;
    padding-top: 8px;
  }

  .btn-text-danger, .btn-text {
    background: none;
    border: none;
    font-size: 12px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    padding: 4px 0;
  }

  .btn-text-danger { color: #f87171; }
  .btn-text-danger:hover { text-decoration: underline; }
  .btn-text { color: #6c63ff; }
  .btn-text:hover { text-decoration: underline; }

  input[type="text"] {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }
</style>
