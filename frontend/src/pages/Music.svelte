<script>
  import { musicData, assistantState, transcript, volumeLevel, musicQueue, musicSearchResults, musicPlaylists, spotifyStatus, spotifyReauthUrl, spotifyAuthQr, sendWS } from '../stores/assistant.js';
  import VirtualKeyboard from '../components/VirtualKeyboard.svelte';

  import { onMount, onDestroy } from 'svelte';

  $: track = {
    title: $musicData.title || 'En attente...',
    artist: $musicData.artist || 'Dites "Terminator, mets de la musique"',
    album: $musicData.album || '',
    cover: $musicData.cover || null,
    playing: $musicData.playing || false,
    progress_ms: $musicData.progress_ms || 0,
    duration_ms: $musicData.duration_ms || 0,
  };

  $: progressPct = track.duration_ms > 0 ? Math.min(100, (track.progress_ms / track.duration_ms) * 100) : 0;

  function formatTime(ms) {
    if (!ms) return '0:00';
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  // Local progress interpolation — smooth bar without polling
  let progressInterval;
  let syncInterval;
  onMount(() => {
    // Advance progress locally every second when playing
    progressInterval = setInterval(() => {
      if (track.playing && track.duration_ms > 0) {
        musicData.update(d => ({
          ...d,
          progress_ms: Math.min((d.progress_ms || 0) + 1000, d.duration_ms || 0),
        }));
      }
    }, 1000);
    // Sync with server every 15s to correct drift
    syncInterval = setInterval(() => {
      if (track.playing) {
        sendWS({ type: 'music_progress' });
      }
    }, 15000);
  });
  onDestroy(() => { clearInterval(progressInterval); clearInterval(syncInterval); });

  const eqBars = 8;
  let showSearch = false;
  let showPlaylists = false;
  let searchQuery = '';
  let searchTimeout;

  function togglePlay() {
    // Optimistic UI — toggle immediately, server will confirm
    musicData.update(d => ({ ...d, playing: !d.playing }));
    sendWS({ type: 'music_play_pause' });
  }
  function nextTrack() {
    // Optimistic — show loading state
    musicData.update(d => ({ ...d, title: '...', artist: 'Chargement' }));
    sendWS({ type: 'music_next' });
  }
  function prevTrack() {
    musicData.update(d => ({ ...d, title: '...', artist: 'Chargement' }));
    sendWS({ type: 'music_prev' });
  }
  function refreshQueue() { sendWS({ type: 'music_queue' }); }

  let volumeTimeout;
  function onVolumeChange(e) {
    const vol = parseInt(e.target.value);
    volumeLevel.set(vol);
    clearTimeout(volumeTimeout);
    volumeTimeout = setTimeout(() => {
      sendWS({ type: 'music_volume', data: vol });
    }, 150);
  }

  function toggleSearch() {
    showSearch = !showSearch;
    showPlaylists = false;
    if (!showSearch) {
      searchQuery = '';
      musicSearchResults.set([]);
    }
  }

  function togglePlaylists() {
    showPlaylists = !showPlaylists;
    showSearch = false;
    if (showPlaylists) {
      sendWS({ type: 'music_playlists' });
    }
  }

  function playPlaylist(pl) {
    sendWS({ type: 'music_play_playlist', data: pl.uri });
    showPlaylists = false;
  }

  function triggerSearch() {
    clearTimeout(searchTimeout);
    if (searchQuery.length < 2) return;
    searchTimeout = setTimeout(() => {
      sendWS({ type: 'music_search', data: searchQuery });
    }, 400);
  }

  function onKeyboard(e) {
    const { action, char } = e.detail;
    if (action === 'char') {
      searchQuery += char;
    } else if (action === 'delete') {
      searchQuery = searchQuery.slice(0, -1);
    } else if (action === 'space') {
      searchQuery += ' ';
    }
    triggerSearch();
  }

  function playSearchResult(result) {
    sendWS({ type: 'music_play_uri', data: result.uri });
    showSearch = false;
    searchQuery = '';
    musicSearchResults.set([]);
  }

  // Queue is refreshed server-side after play/next/playlist commands
  // No client-side reactive polling needed

  let retrying = false;
  function retrySpotify() {
    retrying = true;
    sendWS({ type: 'spotify_retry' });
    setTimeout(() => { retrying = false; }, 5000);
  }

  // Spotify needs auth if no cache or no client
  $: spotifyNeedsAuth = $spotifyStatus === 'auth_required';
  $: spotifyShowBanner = $spotifyStatus !== 'ok' && $spotifyStatus !== 'loading' && !spotifyNeedsAuth;
</script>

<div class="music-page">
  {#if spotifyNeedsAuth}
    <!-- Spotify re-auth overlay -->
    <div class="spotify-qr-overlay">
      <div class="qr-card">
        <div class="qr-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
          </svg>
        </div>
        <h2 class="qr-title">Spotify deconnecte</h2>
        <p class="qr-subtitle">Appuyez pour reconnecter votre compte</p>
        <button class="qr-connect-btn" on:click={() => window.location.href = '/api/spotify/reauth'}>
          Connecter Spotify
        </button>
        <p class="qr-hint">Vous serez redirige vers Spotify pour autoriser l'acces. Utilisez le QR code Spotify pour vous connecter depuis votre telephone.</p>
        <button class="qr-retry" on:click={retrySpotify} disabled={retrying}>
          {retrying ? 'Verification...' : 'Deja connecte ? Verifier'}
        </button>
      </div>
    </div>
  {:else if spotifyShowBanner}
    <div class="spotify-recovery">
      <div class="recovery-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
          <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
        </svg>
      </div>
      <div class="recovery-text">
        {#if $spotifyStatus === 'no_credentials'}
          <span class="recovery-title">Spotify non configure</span>
          <span class="recovery-detail">Cles API manquantes dans .env</span>
        {:else}
          <span class="recovery-title">Spotify indisponible</span>
          <span class="recovery-detail">Connexion perdue</span>
        {/if}
      </div>
      <div class="recovery-actions">
        {#if $spotifyStatus !== 'no_credentials'}
          <button class="recovery-btn" on:click={retrySpotify} disabled={retrying}>
            {retrying ? 'Connexion...' : 'Reessayer'}
          </button>
        {/if}
      </div>
    </div>
  {/if}
  {#if showSearch}
    <!-- Search mode -->
    <div class="search-panel">
      <div class="search-bar">
        <div class="search-display">
          {#if searchQuery}
            <span class="search-text">{searchQuery}</span>
          {:else}
            <span class="search-placeholder">Rechercher un titre, artiste...</span>
          {/if}
          <span class="search-cursor"></span>
        </div>
        <button class="search-close" on:click={toggleSearch}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>
      <div class="search-results">
        {#each $musicSearchResults as result}
          <button class="search-item" on:click={() => playSearchResult(result)}>
            {#if result.cover}
              <img src={result.cover} alt="" class="search-cover" />
            {:else}
              <div class="search-cover-ph"></div>
            {/if}
            <div class="search-info">
              <span class="search-title">{result.title}</span>
              <span class="search-artist">{result.artist}</span>
            </div>
          </button>
        {/each}
      </div>
      <VirtualKeyboard on:key={onKeyboard} />
    </div>
  {:else if showPlaylists}
    <!-- Playlists mode -->
    <div class="playlists-panel">
      <div class="playlists-header">
        <span class="playlists-title">Mes playlists</span>
        <button class="search-close" on:click={togglePlaylists}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>
      <div class="playlists-list">
        {#each $musicPlaylists as pl}
          <button class="playlist-item" on:click={() => playPlaylist(pl)}>
            {#if pl.cover}
              <img src={pl.cover} alt="" class="playlist-cover" />
            {:else}
              <div class="playlist-cover-ph"></div>
            {/if}
            <div class="playlist-info">
              <span class="playlist-name">{pl.name}</span>
              <span class="playlist-count">{pl.tracks} titres</span>
            </div>
          </button>
        {/each}
        {#if $musicPlaylists.length === 0}
          <p class="playlists-empty">Chargement...</p>
        {/if}
      </div>
    </div>
  {:else}
    <!-- Normal player -->
    <div class="cover-zone">
      <div class="cover-container" class:idle={!track.cover}>
        {#if track.cover}
          <img src={track.cover} alt="Album" class="cover-art" loading="lazy" />
        {:else}
          <div class="cover-placeholder">
            <div class="vinyl" class:spinning={track.playing} class:breathing={!track.playing}>
              <div class="vinyl-groove vinyl-groove-1"></div>
              <div class="vinyl-groove vinyl-groove-2"></div>
              <div class="vinyl-groove vinyl-groove-3"></div>
              <div class="vinyl-inner">
                <div class="vinyl-label"></div>
              </div>
            </div>
            <p class="idle-text">En attente de musique...</p>
          </div>
        {/if}
        <div class="cover-glow" class:playing={track.playing}></div>
      </div>
    </div>

    <div class="info-zone">
      {#if track.cover}
        <div class="track-info">
          <h1 class="track-title">{track.title}</h1>
          <p class="track-artist">{track.artist}</p>
          {#if track.album}
            <p class="track-album">{track.album}</p>
          {/if}
        </div>
      {:else}
        <div class="track-info idle-info">
          <h1 class="track-title idle-title">{track.title}</h1>
          <p class="track-artist">{track.artist}</p>
        </div>
      {/if}

      <div class="equalizer" class:active={track.playing}>
        {#each Array(eqBars) as _, i}
          <div
            class="eq-bar"
            style="animation-delay: {i * 65}ms; animation-duration: {0.6 + (i % 5) * 0.15}s"
          ></div>
        {/each}
      </div>

      <div class="controls">
        <button class="control-btn prev-next-btn" aria-label="Precedent" on:click={prevTrack}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
          </svg>
        </button>
        <button class="control-btn play-btn" aria-label={track.playing ? 'Pause' : 'Play'} on:click={togglePlay}>
          {#if track.playing}
            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
            </svg>
          {:else}
            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
          {/if}
        </button>
        <button class="control-btn prev-next-btn" aria-label="Suivant" on:click={nextTrack}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
          </svg>
        </button>
        <button class="control-btn" aria-label="Recherche" on:click={toggleSearch}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
          </svg>
        </button>
        <button class="control-btn" aria-label="Playlists" on:click={togglePlaylists}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/>
          </svg>
        </button>
      </div>

      {#if track.duration_ms > 0}
        <div class="progress-bar">
          <span class="progress-time progress-current">{formatTime(track.progress_ms)}</span>
          <div class="progress-track">
            <div class="progress-fill" style="width: {progressPct}%">
              <span class="progress-dot"></span>
            </div>
          </div>
          <span class="progress-time progress-remaining">{formatTime(track.duration_ms)}</span>
        </div>
      {/if}

      <div class="volume-control">
        <svg class="vol-icon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
        </svg>
        <input
          type="range"
          min="0"
          max="100"
          value={$volumeLevel}
          on:input={onVolumeChange}
          class="vol-slider"
        />
        <span class="vol-value">{$volumeLevel}%</span>
      </div>

      {#if $musicQueue.length > 0}
        <div class="queue">
          <span class="queue-label">A suivre</span>
          <div class="queue-items">
            {#each $musicQueue.slice(0, 3) as q}
              <div class="queue-item">
                {#if q.cover}
                  <img src={q.cover} alt="" class="queue-cover" />
                {:else}
                  <div class="queue-cover-ph"></div>
                {/if}
                <div class="queue-text">
                  <span class="queue-title">{q.title}</span>
                  <span class="queue-artist">{q.artist}</span>
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .music-page {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: row;
    align-items: center;
    padding: 28px 32px 24px;
    gap: 36px;
  }

  /* ──── Cover zone ──── */
  .cover-zone {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cover-container {
    position: relative;
    width: 280px;
    height: 280px;
  }
  .cover-container.idle {
    width: 280px;
    height: 320px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cover-art {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 16px;
  }

  .cover-placeholder {
    width: 100%;
    height: 100%;
    border-radius: 16px;
    background: linear-gradient(145deg, #141420, #1a1a2e);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    border: 1px solid rgba(108, 99, 255, 0.1);
  }

  .idle-text {
    font-size: 13px;
    color: #555;
    letter-spacing: 0.5px;
    animation: idleFade 3s ease-in-out infinite;
  }

  @keyframes idleFade {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }

  /* Vinyl disc */
  .vinyl {
    width: 140px;
    height: 140px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
  .vinyl.spinning { animation: vinylSpin 20s linear infinite; }
  .vinyl.breathing { animation: vinylBreathe 4s ease-in-out infinite; }

  .vinyl-groove {
    position: absolute;
    border-radius: 50%;
    border: 1px solid rgba(108, 99, 255, 0.06);
  }
  .vinyl-groove-1 { width: 90%; height: 90%; }
  .vinyl-groove-2 { width: 72%; height: 72%; }
  .vinyl-groove-3 { width: 54%; height: 54%; }

  .vinyl-inner {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: #0a0a0f;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
  }

  .vinyl-label {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #6c63ff;
    opacity: 0.6;
  }

  @keyframes vinylSpin { to { transform: rotate(360deg); } }
  @keyframes vinylBreathe {
    0%, 100% { transform: scale(1); opacity: 0.7; }
    50% { transform: scale(1.04); opacity: 1; }
  }

  /* Ambient glow behind cover */
  .cover-glow {
    position: absolute;
    inset: -30px;
    border-radius: 40px;
    background: radial-gradient(circle, rgba(108,99,255,0.12) 0%, rgba(108,99,255,0.04) 50%, transparent 75%);
    z-index: -1;
    opacity: 0;
    transition: opacity 800ms ease;
  }
  .cover-glow.playing {
    opacity: 0.9;
  }

  /* ──── Info zone ──── */
  .info-zone {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 12px;
    min-width: 0;
  }

  .track-info { min-width: 0; }
  .idle-info { opacity: 0.6; }

  .track-title {
    font-size: 22px;
    font-weight: 700;
    color: #f0f0f0;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
  }
  .idle-title {
    font-size: 18px;
    font-weight: 600;
  }

  .track-artist {
    font-size: 15px;
    font-weight: 500;
    color: #aaa;
  }

  .track-album {
    font-size: 12px;
    color: #666;
    margin-top: 4px;
  }

  /* ──── Equalizer ──── */
  .equalizer {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 22px;
    opacity: 0.15;
    transition: opacity 500ms ease;
  }
  .equalizer.active { opacity: 1; }

  .eq-bar {
    width: 4px;
    height: 4px;
    border-radius: 2px;
    background: #6c63ff;
  }
  .equalizer.active .eq-bar {
    animation: eqBounce ease-in-out infinite alternate;
  }

  @keyframes eqBounce {
    0% { height: 4px; opacity: 0.35; }
    100% { height: 20px; opacity: 1; }
  }

  /* ──── Controls ──── */
  .controls { display: flex; align-items: center; gap: 14px; }

  .control-btn {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 8px;
    border-radius: 50%;
    transition: color 200ms ease, transform 100ms ease, opacity 100ms ease;
    -webkit-tap-highlight-color: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .control-btn:active { transform: scale(0.88); color: #f0f0f0; }

  .prev-next-btn {
    width: 44px;
    height: 44px;
    color: #aaa;
  }
  .prev-next-btn:active { color: #f0f0f0; }

  .play-btn {
    width: 56px;
    height: 56px;
    background: #6c63ff;
    border: none;
    color: #fff;
    transition: transform 100ms ease, opacity 100ms ease;
  }
  .play-btn:active {
    transform: scale(0.92);
    opacity: 0.85;
  }

  /* ──── Progress bar ──── */
  .progress-bar {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .progress-time {
    font-size: 11px;
    color: #666;
    min-width: 32px;
    font-variant-numeric: tabular-nums;
  }
  .progress-current { text-align: right; color: #aaa; }
  .progress-remaining { text-align: left; }

  .progress-track {
    flex: 1;
    height: 5px;
    border-radius: 3px;
    background: rgba(255,255,255,0.08);
    overflow: visible;
    position: relative;
  }

  .progress-fill {
    height: 100%;
    background: #6c63ff;
    border-radius: 3px;
    transition: width 1s linear;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .progress-dot {
    position: absolute;
    right: -5px;
    top: 50%;
    transform: translateY(-50%);
    width: 11px;
    height: 11px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid #6c63ff;
  }

  /* ──── Volume ──── */
  .volume-control {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .vol-icon { color: #888; flex-shrink: 0; }

  .vol-slider {
    -webkit-appearance: none;
    appearance: none;
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: rgba(255,255,255,0.1);
    outline: none;
  }
  .vol-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #6c63ff;
    cursor: pointer;
  }

  .vol-value {
    font-size: 11px;
    color: #888;
    min-width: 30px;
    text-align: right;
  }

  /* ──── Queue ──── */
  .queue {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 130px;
    overflow: hidden;
  }

  .queue-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #555;
    font-weight: 600;
  }

  .queue-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .queue-item {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .queue-cover {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .queue-cover-ph {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    background: rgba(108, 99, 255, 0.08);
    flex-shrink: 0;
  }

  .queue-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .queue-title {
    font-size: 12px;
    color: #999;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 220px;
  }

  .queue-artist {
    font-size: 10px;
    color: #555;
    white-space: nowrap;
  }

  /* ──── Spotify QR overlay ──── */
  .spotify-qr-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 10, 15, 0.95);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 30;
  }

  .qr-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 32px 40px;
    max-width: 380px;
  }

  .qr-icon {
    color: #1DB954;
    margin-bottom: 4px;
  }

  .qr-title {
    font-size: 20px;
    font-weight: 700;
    color: #f0f0f0;
    margin: 0;
  }

  .qr-subtitle {
    font-size: 14px;
    color: #aaa;
    margin: 0;
  }

  .qr-connect-btn {
    background: #1DB954;
    border: none;
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    padding: 16px 48px;
    border-radius: 28px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    -webkit-tap-highlight-color: transparent;
    margin: 8px 0;
    transition: opacity 150ms, transform 100ms;
  }
  .qr-connect-btn:active {
    opacity: 0.8;
    transform: scale(0.96);
  }

  .qr-hint {
    font-size: 12px;
    color: #666;
    text-align: center;
    line-height: 1.5;
    margin: 0;
    max-width: 260px;
  }

  .qr-retry {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #aaa;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    -webkit-tap-highlight-color: transparent;
    margin-top: 4px;
  }
  .qr-retry:active { opacity: 0.7; }
  .qr-retry:disabled { opacity: 0.4; }

  /* ──── Spotify recovery banner ──── */
  .spotify-recovery {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    background: rgba(255, 68, 68, 0.1);
    border-bottom: 1px solid rgba(255, 68, 68, 0.25);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 20;
  }

  .recovery-icon {
    color: #ff6b6b;
    flex-shrink: 0;
    display: flex;
  }

  .recovery-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .recovery-title {
    font-size: 13px;
    font-weight: 600;
    color: #ff6b6b;
  }

  .recovery-detail {
    font-size: 11px;
    color: #ff9999;
  }

  .recovery-actions {
    flex-shrink: 0;
    display: flex;
    gap: 8px;
  }

  .recovery-btn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #f0f0f0;
    font-size: 12px;
    font-weight: 500;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    -webkit-tap-highlight-color: transparent;
    transition: opacity 150ms;
  }
  .recovery-btn:active { opacity: 0.7; }
  .recovery-btn:disabled { opacity: 0.4; cursor: default; }



  /* ──── Playlists panel ──── */
  .playlists-panel {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding-top: 10px;
  }

  .playlists-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 4px 8px;
  }

  .playlists-title {
    font-size: 16px;
    font-weight: 600;
    color: #f0f0f0;
  }

  .playlists-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .playlist-item {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 8px;
    background: none;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    text-align: left;
    -webkit-tap-highlight-color: transparent;
  }
  .playlist-item:active { background: rgba(255,255,255,0.05); }

  .playlist-cover {
    width: 48px;
    height: 48px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .playlist-cover-ph {
    width: 48px;
    height: 48px;
    border-radius: 6px;
    background: rgba(108, 99, 255, 0.1);
    flex-shrink: 0;
  }

  .playlist-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .playlist-name {
    font-size: 14px;
    color: #f0f0f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .playlist-count {
    font-size: 11px;
    color: #888;
  }

  .playlists-empty {
    color: #555;
    font-size: 13px;
    text-align: center;
    padding: 20px;
  }

  /* ──── Search panel ──── */
  .search-panel {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding-top: 10px;
  }

  .search-bar {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 0 4px;
  }

  .search-display {
    flex: 1;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(108, 99, 255, 0.3);
    border-radius: 10px;
    padding: 10px 14px;
    min-height: 20px;
    display: flex;
    align-items: center;
  }

  .search-text {
    color: #f0f0f0;
    font-size: 14px;
  }

  .search-placeholder {
    color: #555;
    font-size: 14px;
  }

  .search-cursor {
    width: 2px;
    height: 16px;
    background: #6c63ff;
    margin-left: 1px;
    animation: blink 1s step-end infinite;
  }

  @keyframes blink {
    50% { opacity: 0; }
  }

  .search-close {
    background: none;
    border: none;
    color: #888;
    padding: 8px;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .search-results {
    flex: 1;
    overflow-y: auto;
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .search-item {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 8px;
    background: none;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    text-align: left;
    -webkit-tap-highlight-color: transparent;
  }
  .search-item:active { background: rgba(255,255,255,0.05); }

  .search-cover {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .search-cover-ph {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    background: rgba(255,255,255,0.05);
    flex-shrink: 0;
  }

  .search-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .search-title {
    font-size: 13px;
    color: #f0f0f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .search-artist {
    font-size: 11px;
    color: #888;
  }
</style>
