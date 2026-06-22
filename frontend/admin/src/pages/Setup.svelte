<script>
  import { onMount } from 'svelte';
  import { apiGet, apiPut, apiPost, showToast } from '../stores/auth.js';

  // Appelé quand le wizard se termine ou est ignoré (App.svelte referme).
  export let onClose = () => {};

  const STEPS = ['Bienvenue', 'Langue', 'Lieu', 'Audio', 'Musique', 'Voix & IA', 'Maison & extras', 'Apparence', 'Récapitulatif'];

  let step = 0;
  let loading = true;
  let saving = false;
  let prefilled = false;  // vrai seulement si config + env ont bien été chargés

  // --- config.json ---
  let locale = 'fr';
  let accentColor = '#7C6FFF';
  let bgColor = '#060610';
  let outputSink = '';
  let sinks = [];

  // --- .env (non-secrets prérenseignés ; secrets vides = préservés) ---
  let city = '', lat = '', lon = '';
  let geoResults = [], geoSearching = false;

  let musicProvider = 'radio', musicLibraryDir = '';
  let deezerArl = '', spotifyId = '', spotifySecret = '';
  let deezerWasSet = false, spotifyWasSet = false;

  let sttMode = 'vosk', llmProvider = 'gateway', ttsProvider = 'gateway';
  let gatewayUrl = '', nemotronUrl = '';
  let gatewayToken = '', mistralKey = '';
  let gatewayTokenWasSet = false, mistralWasSet = false;

  let homeProvider = 'lite', haUrl = '', haToken = '', haTokenWasSet = false;
  let devialetIp = '';
  let unifiHost = '', unifiMac = '', unifiUser = '', unifiPass = '';
  let unifiPassWasSet = false;

  onMount(async () => {
    const cfg = await apiGet('/admin/api/config');
    if (cfg) {
      locale = cfg.ui?.locale ?? locale;
      accentColor = cfg.ui?.accent_color ?? accentColor;
      bgColor = cfg.ui?.bg_color ?? bgColor;
      outputSink = cfg.audio?.output_sink ?? '';
    }
    const env = await apiGet('/admin/api/env');
    if (env && env.env) {
      const m = {};
      for (const e of env.env) m[e.key] = e;
      const val = (k) => (m[k]?.value ?? '');
      const had = (k) => !!(m[k]?.has_value);
      city = val('WEATHER_CITY'); lat = val('WEATHER_LAT'); lon = val('WEATHER_LON');
      musicProvider = val('MUSIC_PROVIDER') || 'radio';
      musicLibraryDir = val('MUSIC_LIBRARY_DIR');
      deezerWasSet = had('DEEZER_ARL'); spotifyWasSet = had('SPOTIFY_CLIENT_ID');
      sttMode = val('STT_MODE') || 'vosk';
      llmProvider = val('LLM_PROVIDER') || 'gateway';
      ttsProvider = val('TTS_PROVIDER') || 'gateway';
      gatewayUrl = val('GATEWAY_URL'); nemotronUrl = val('NEMOTRON_ASR_URL');
      gatewayTokenWasSet = had('GATEWAY_TOKEN'); mistralWasSet = had('MISTRAL_API_KEY');
      homeProvider = val('HOME_PROVIDER') || 'lite'; haUrl = val('HA_URL');
      haTokenWasSet = had('HA_TOKEN');
      devialetIp = val('DEVIALET_IP');
      unifiHost = val('UNIFI_HOST'); unifiMac = val('UNIFI_MAC');
      unifiPassWasSet = had('UNIFI_PASS');
    }
    const sk = await apiGet('/admin/api/audio/sinks');
    if (sk && sk.sinks) sinks = sk.sinks;
    // On n'autorise l'enregistrement QUE si l'état courant a bien été lu : sinon les
    // champs gardent leurs valeurs par défaut et Enregistrer écraserait la vraie config.
    prefilled = !!cfg && !!(env && env.env);
    loading = false;
  });

  // Coordonnées : tolère la virgule décimale (48,85) et valide les bornes.
  const normNum = (s) => (s || '').trim().replace(',', '.');
  function coordsValid() {
    if (lat.trim() === '' && lon.trim() === '') return true;  // vide = météo non réglée
    const la = parseFloat(normNum(lat)), lo = parseFloat(normNum(lon));
    return Number.isFinite(la) && la >= -90 && la <= 90 &&
           Number.isFinite(lo) && lo >= -180 && lo <= 180;
  }

  async function geocode() {
    if (!city.trim()) return;
    geoSearching = true; geoResults = [];
    try {
      const r = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=6&language=${locale}`);
      const j = await r.json();
      geoResults = j.results || [];
      if (!geoResults.length) showToast('Aucune ville trouvée', 'error');
    } catch (e) {
      showToast('Recherche impossible (hors-ligne ?) — saisis les coordonnées', 'error');
    }
    geoSearching = false;
  }
  function pickCity(c) {
    city = c.name;
    lat = (Math.round(c.latitude * 10000) / 10000).toString();
    lon = (Math.round(c.longitude * 10000) / 10000).toString();
    geoResults = [];
  }

  function next() { if (step < STEPS.length - 1) step++; }
  function back() { if (step > 0) step--; }

  // Un secret n'est envoyé QUE si l'utilisateur a saisi quelque chose
  // (vide = préservé côté serveur, jamais effacé). On le marque is_secret.
  function secretEntry(key, value) {
    return { key, value: value || '', is_secret: true };
  }

  async function finish(restart) {
    // Garde-fou : si la config n'a pas pu être lue, ne JAMAIS écrire (on écraserait
    // la vraie config avec les valeurs par défaut des champs).
    if (!prefilled) { showToast('Configuration non chargée — réessaie', 'error'); return; }
    if (!coordsValid()) {
      showToast('Coordonnées invalides (latitude -90..90, longitude -180..180)', 'error');
      step = 2; return;
    }
    lat = normNum(lat); lon = normNum(lon);
    saving = true;
    const entries = [
      { key: 'WEATHER_CITY', value: city },
      { key: 'WEATHER_LAT', value: lat },
      { key: 'WEATHER_LON', value: lon },
      { key: 'MUSIC_PROVIDER', value: musicProvider },
      { key: 'MUSIC_LIBRARY_DIR', value: musicLibraryDir },
      secretEntry('DEEZER_ARL', deezerArl),
      secretEntry('SPOTIFY_CLIENT_ID', spotifyId),
      secretEntry('SPOTIFY_CLIENT_SECRET', spotifySecret),
      { key: 'STT_MODE', value: sttMode },
      { key: 'NEMOTRON_ASR_URL', value: nemotronUrl },
      { key: 'LLM_PROVIDER', value: llmProvider },
      { key: 'TTS_PROVIDER', value: ttsProvider },
      { key: 'GATEWAY_URL', value: gatewayUrl },
      secretEntry('GATEWAY_TOKEN', gatewayToken),
      secretEntry('MISTRAL_API_KEY', mistralKey),
      { key: 'HOME_PROVIDER', value: homeProvider },
      { key: 'HA_URL', value: haUrl },
      secretEntry('HA_TOKEN', haToken),
      { key: 'DEVIALET_IP', value: devialetIp },
      { key: 'UNIFI_HOST', value: unifiHost },
      secretEntry('UNIFI_USER', unifiUser),
      secretEntry('UNIFI_PASS', unifiPass),
      { key: 'UNIFI_MAC', value: unifiMac },
    ];
    // Écritures séquentielles, chacune vérifiée. setup_complete est écrit EN DERNIER
    // et UNIQUEMENT si tout le reste a réussi — sinon on n'efface pas le « à faire »
    // (le wizard pourra se rouvrir) et l'utilisateur garde une config cohérente.
    const r1 = await apiPut('/admin/api/env', { entries });
    if (!r1.ok) { saving = false; showToast('Erreur lors de l\'enregistrement (.env)', 'error'); return; }
    const r2 = await apiPut('/admin/api/config/ui', { locale, accent_color: accentColor, bg_color: bgColor });
    const r3 = await apiPut('/admin/api/config/audio', { output_sink: outputSink });
    if (!r2.ok || !r3.ok) { saving = false; showToast('Erreur lors de l\'enregistrement (apparence/audio)', 'error'); return; }
    const r4 = await apiPut('/admin/api/config/system', { setup_complete: true });
    saving = false;
    if (!r4.ok) { showToast('Réglages enregistrés, mais statut non sauvé — réessaie', 'error'); return; }
    if (restart) {
      await apiPost('/admin/api/system/restart-backend', {});
      showToast('Configuration enregistrée — redémarrage…', 'success');
    } else {
      showToast('Configuration enregistrée', 'success');
    }
    onClose();
  }

  async function skip() {
    const r = await apiPut('/admin/api/config/system', { setup_complete: true });
    if (!r.ok) { showToast('Impossible d\'enregistrer — réessaie', 'error'); return; }
    onClose();
  }
</script>

<div class="wizard">
  <div class="wiz-head">
    <div class="wiz-brand">pi</div>
    <div class="wiz-steps">
      {#each STEPS as s, i}
        <span class="dot {i === step ? 'on' : ''} {i < step ? 'done' : ''}"></span>
      {/each}
    </div>
    <button class="link" on:click={skip}>Passer</button>
  </div>

  {#if loading}
    <div class="loading">Chargement…</div>
  {:else if !prefilled}
    <div class="wiz-body">
      <h1>Connexion impossible</h1>
      <p class="lead">Impossible de lire la configuration actuelle du backend. Vérifie qu'il répond,
        puis réessaie — par sécurité l'assistant n'enregistre rien tant que l'état n'est pas chargé.</p>
    </div>
    <div class="wiz-foot">
      <button class="btn ghost" on:click={skip}>Fermer</button>
      <button class="btn primary" on:click={() => location.reload()}>Réessayer</button>
    </div>
  {:else}
    <div class="wiz-body">
      <p class="wiz-step-label">Étape {step + 1} / {STEPS.length} — {STEPS[step]}</p>

      {#if step === 0}
        <h1>Bienvenue sur PiBoard 👋</h1>
        <p class="lead">Ce petit assistant configure l'essentiel en quelques étapes : langue, lieu pour
          la météo, sortie audio, musique, voix et quelques intégrations optionnelles. Tout est
          modifiable plus tard. Rien n'est obligatoire — laisse vide pour désactiver une fonction.</p>

      {:else if step === 1}
        <h1>Langue</h1>
        <div class="choices">
          <button class="choice {locale === 'fr' ? 'sel' : ''}" on:click={() => locale = 'fr'}>🇫🇷 Français</button>
          <button class="choice {locale === 'en' ? 'sel' : ''}" on:click={() => locale = 'en'}>🇬🇧 English</button>
        </div>

      {:else if step === 2}
        <h1>Où es-tu ? <span class="opt">(météo)</span></h1>
        <div class="form-group">
          <label class="form-label" for="city">Ville</label>
          <div class="row">
            <input id="city" bind:value={city} placeholder="Paris, Tokyo, …" on:keydown={(e) => e.key === 'Enter' && geocode()} />
            <button class="btn" on:click={geocode} disabled={geoSearching}>{geoSearching ? '…' : 'Chercher'}</button>
          </div>
          {#if geoResults.length}
            <div class="geo-list">
              {#each geoResults as c}
                <button class="geo-item" on:click={() => pickCity(c)}>
                  {c.name}{c.admin1 ? ', ' + c.admin1 : ''} <span class="muted">{c.country} · {c.latitude.toFixed(2)}, {c.longitude.toFixed(2)}</span>
                </button>
              {/each}
            </div>
          {/if}
        </div>
        <div class="grid2">
          <div class="form-group"><label class="form-label" for="lat">Latitude</label><input id="lat" bind:value={lat} placeholder="48.85" /></div>
          <div class="form-group"><label class="form-label" for="lon">Longitude</label><input id="lon" bind:value={lon} placeholder="2.35" /></div>
        </div>
        <p class="form-hint">Météo via Open-Meteo (gratuit, sans clé). Cherche ta ville ou saisis les coordonnées.</p>

      {:else if step === 3}
        <h1>Sortie audio</h1>
        <div class="form-group">
          <label class="form-label" for="sink">Haut-parleur</label>
          <select id="sink" bind:value={outputSink}>
            <option value="">Automatique (Devialet si présent)</option>
            {#each sinks as s}<option value={s.name}>{s.label}</option>{/each}
          </select>
        </div>
        <p class="form-hint">N'importe quelle sortie PipeWire : AirPlay, HDMI, Bluetooth… « Automatique » convient dans la plupart des cas.</p>

      {:else if step === 4}
        <h1>Musique</h1>
        <div class="form-group">
          <label class="form-label" for="mp">Source</label>
          <select id="mp" bind:value={musicProvider}>
            <option value="radio">Radio internet (gratuit, sans compte) — recommandé</option>
            <option value="local">Bibliothèque locale</option>
            <option value="spotify">Spotify</option>
            <option value="deezer">Deezer (opt-in, ARL perso)</option>
          </select>
        </div>
        {#if musicProvider === 'local'}
          <div class="form-group"><label class="form-label" for="mld">Dossier de musique</label><input id="mld" bind:value={musicLibraryDir} placeholder="~/Music" /></div>
        {:else if musicProvider === 'deezer'}
          <div class="form-group">
            <label class="form-label" for="arl">ARL Deezer {#if deezerWasSet}<span class="set">déjà défini</span>{/if}</label>
            <input id="arl" type="password" bind:value={deezerArl} placeholder={deezerWasSet ? '•••••• (laisser vide = inchangé)' : 'colle ton ARL'} />
            <p class="form-hint">⚠️ Zone grise des CGU Deezer — usage perso. Ton ARL reste sur l'appareil.</p>
          </div>
        {:else if musicProvider === 'spotify'}
          <div class="grid2">
            <div class="form-group"><label class="form-label" for="sid">Client ID {#if spotifyWasSet}<span class="set">défini</span>{/if}</label><input id="sid" type="password" bind:value={spotifyId} placeholder={spotifyWasSet ? '••••••' : ''} /></div>
            <div class="form-group"><label class="form-label" for="ssec">Client Secret</label><input id="ssec" type="password" bind:value={spotifySecret} placeholder="••••••" /></div>
          </div>
        {/if}

      {:else if step === 5}
        <h1>Voix & IA</h1>
        <p class="lead">Tout peut tourner en local et gratuitement, ou basculer sur le cloud. Laisse les
          réglages par défaut si tu débutes.</p>
        <div class="grid2">
          <div class="form-group">
            <label class="form-label" for="stt">Reconnaissance (STT)</label>
            <select id="stt" bind:value={sttMode}>
              <option value="vosk">Vosk — local, hors-ligne (défaut)</option>
              <option value="nemotron">Nemotron ASR (serveur LAN)</option>
              <option value="voxtral">Voxtral (cloud Mistral)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="llm">Cerveau (LLM)</label>
            <select id="llm" bind:value={llmProvider}>
              <option value="gateway">Passerelle locale (Ollama, gratuit)</option>
              <option value="mistral">Mistral (cloud)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="tts">Synthèse (TTS)</label>
            <select id="tts" bind:value={ttsProvider}>
              <option value="gateway">Passerelle locale (gratuit)</option>
              <option value="piper">Piper — local hors-ligne</option>
              <option value="voxtral">Voxtral (cloud)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="gw">URL passerelle LAN</label>
            <input id="gw" bind:value={gatewayUrl} placeholder="http://192.168.x.x:8765" />
          </div>
        </div>
        {#if sttMode === 'nemotron'}
          <div class="form-group"><label class="form-label" for="nemo">URL Nemotron ASR</label><input id="nemo" bind:value={nemotronUrl} placeholder="http://192.168.x.x:8766" /></div>
        {/if}
        {#if llmProvider === 'mistral' || ttsProvider === 'voxtral' || sttMode === 'voxtral'}
          <div class="form-group">
            <label class="form-label" for="mk">Clé API Mistral {#if mistralWasSet}<span class="set">définie</span>{/if}</label>
            <input id="mk" type="password" bind:value={mistralKey} placeholder={mistralWasSet ? '•••••• (inchangé)' : 'sk-…'} />
          </div>
        {/if}

      {:else if step === 6}
        <h1>Maison & extras <span class="opt">(optionnel)</span></h1>
        <div class="form-group">
          <label class="form-label" for="hp">Domotique</label>
          <select id="hp" bind:value={homeProvider}>
            <option value="lite">Drivers intégrés (Shelly / Kasa)</option>
            <option value="homeassistant">Home Assistant</option>
          </select>
        </div>
        {#if homeProvider === 'homeassistant'}
          <div class="grid2">
            <div class="form-group"><label class="form-label" for="hau">URL Home Assistant</label><input id="hau" bind:value={haUrl} placeholder="http://homeassistant.local:8123" /></div>
            <div class="form-group"><label class="form-label" for="hat">Jeton HA {#if haTokenWasSet}<span class="set">défini</span>{/if}</label><input id="hat" type="password" bind:value={haToken} placeholder={haTokenWasSet ? '••••••' : 'jeton longue durée'} /></div>
          </div>
        {/if}
        <div class="form-group"><label class="form-label" for="dev">Devialet Phantom (IP/hostname)</label><input id="dev" bind:value={devialetIp} placeholder="vide = pas de Devialet" /></div>
        <div class="grid2">
          <div class="form-group"><label class="form-label" for="uh">Caméras — hôte UniFi</label><input id="uh" bind:value={unifiHost} placeholder="vide = pas de caméras" /></div>
          <div class="form-group"><label class="form-label" for="um">UniFi MAC (auto-découverte)</label><input id="um" bind:value={unifiMac} placeholder="optionnel" /></div>
          <div class="form-group"><label class="form-label" for="uu">UniFi utilisateur</label><input id="uu" bind:value={unifiUser} placeholder="" /></div>
          <div class="form-group"><label class="form-label" for="up">UniFi mot de passe {#if unifiPassWasSet}<span class="set">défini</span>{/if}</label><input id="up" type="password" bind:value={unifiPass} placeholder={unifiPassWasSet ? '••••••' : ''} /></div>
        </div>

      {:else if step === 7}
        <h1>Apparence</h1>
        <div class="grid2">
          <div class="form-group">
            <label class="form-label" for="ac">Couleur d'accent</label>
            <div class="row"><input id="ac" type="color" bind:value={accentColor} class="swatch" /><input bind:value={accentColor} class="hex" /></div>
          </div>
          <div class="form-group">
            <label class="form-label" for="bc">Couleur de fond</label>
            <div class="row"><input id="bc" type="color" bind:value={bgColor} class="swatch" /><input bind:value={bgColor} class="hex" /></div>
          </div>
        </div>
        <div class="preview" style="background: {bgColor};">
          <span style="color: {accentColor};">●</span> Aperçu du thème
        </div>

      {:else if step === 8}
        <h1>C'est prêt ✨</h1>
        <ul class="recap">
          <li><b>Langue</b> : {locale === 'fr' ? 'Français' : 'English'}</li>
          <li><b>Météo</b> : {city || '—'} {lat && lon ? `(${lat}, ${lon})` : ''}</li>
          <li><b>Audio</b> : {outputSink ? (sinks.find(s => s.name === outputSink)?.label || outputSink) : 'Automatique'}</li>
          <li><b>Musique</b> : {musicProvider}</li>
          <li><b>Voix</b> : STT {sttMode} · LLM {llmProvider} · TTS {ttsProvider}</li>
          <li><b>Domotique</b> : {homeProvider}{devialetIp ? ' · Devialet' : ''}{unifiHost ? ' · caméras' : ''}</li>
        </ul>
        <p class="form-hint">Certains réglages (voix, musique, intégrations) ne s'appliquent qu'après un
          redémarrage de l'assistant.</p>
      {/if}
    </div>

    <div class="wiz-foot">
      <button class="btn ghost" on:click={back} disabled={step === 0}>Retour</button>
      {#if step < STEPS.length - 1}
        <button class="btn primary" on:click={next}>Continuer</button>
      {:else}
        <button class="btn" on:click={() => finish(false)} disabled={saving}>Enregistrer</button>
        <button class="btn primary" on:click={() => finish(true)} disabled={saving}>
          {saving ? 'Enregistrement…' : 'Enregistrer & redémarrer'}
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .wizard { max-width: 760px; margin: 0 auto; }
  .wiz-head { display: flex; align-items: center; gap: 16px; margin-bottom: 18px; }
  .wiz-brand { width: 40px; height: 40px; border-radius: 11px; background: linear-gradient(135deg, #7C6FFF, #4F46E5);
    color: #fff; font-weight: 800; display: flex; align-items: center; justify-content: center; }
  .wiz-steps { display: flex; gap: 7px; flex: 1; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: #2a2a3a; transition: background .2s; }
  .dot.on { background: #7C6FFF; transform: scale(1.25); }
  .dot.done { background: #4F46E5; }
  .link { background: none; border: none; color: #9aa; cursor: pointer; font-size: 14px; }
  .link:hover { color: #ccd; }

  .wiz-body { background: #16161f; border: 1px solid #26263a; border-radius: 16px; padding: 28px; min-height: 320px; }
  .wiz-step-label { color: #7C6FFF; font-size: 13px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; margin: 0 0 10px; }
  .wiz-body h1 { font-size: 26px; margin: 0 0 14px; color: #f0f0f5; }
  .opt { color: #777; font-size: 16px; font-weight: 400; }
  .lead { color: #b8b8c8; line-height: 1.55; margin: 0 0 18px; }

  .choices { display: flex; gap: 14px; }
  .choice { flex: 1; padding: 22px; border-radius: 12px; border: 2px solid #2a2a3a; background: #1c1c28;
    color: #ddd; font-size: 18px; cursor: pointer; transition: border-color .15s, background .15s; }
  .choice.sel { border-color: #7C6FFF; background: #221f3a; }

  .form-group { margin-bottom: 16px; }
  .form-label { display: block; font-size: 13px; font-weight: 600; color: #aab; margin-bottom: 6px; }
  .set { color: #34D399; font-size: 12px; font-weight: 600; margin-left: 6px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .row { display: flex; gap: 8px; }
  input, select { width: 100%; box-sizing: border-box; padding: 11px 13px; border-radius: 9px;
    background: #11111a; border: 1px solid #2c2c40; color: #eee; font-size: 15px; }
  input:focus, select:focus { outline: none; border-color: #7C6FFF; }
  .swatch { width: 52px; padding: 4px; flex: 0 0 auto; }
  .hex { font-family: monospace; }
  .form-hint { color: #888; font-size: 13px; line-height: 1.45; margin: 6px 0 0; }

  .geo-list { margin-top: 8px; border: 1px solid #2c2c40; border-radius: 9px; overflow: hidden; }
  .geo-item { display: block; width: 100%; text-align: left; padding: 10px 13px; background: #14141e;
    color: #ddd; border: none; border-bottom: 1px solid #21212e; cursor: pointer; font-size: 14px; }
  .geo-item:hover { background: #1e1e2c; }
  .muted { color: #777; font-size: 12px; }

  .preview { margin-top: 12px; padding: 22px; border-radius: 12px; border: 1px solid #2a2a3a;
    color: #ddd; font-weight: 600; }

  .recap { list-style: none; padding: 0; margin: 0 0 16px; }
  .recap li { padding: 9px 0; border-bottom: 1px solid #21212e; color: #ccd; }
  .recap b { color: #9b8cff; }

  .wiz-foot { display: flex; gap: 10px; justify-content: flex-end; margin-top: 18px; }
  .btn { padding: 11px 22px; border-radius: 10px; border: 1px solid #2c2c40; background: #1c1c28;
    color: #ddd; font-size: 15px; font-weight: 600; cursor: pointer; }
  .btn:hover { background: #24243400; border-color: #3a3a55; }
  .btn:disabled { opacity: .45; cursor: default; }
  .btn.primary { background: linear-gradient(135deg, #7C6FFF, #5b50e0); border-color: transparent; color: #fff; }
  .btn.ghost { background: transparent; }
  .loading { padding: 40px; text-align: center; color: #888; }
</style>
