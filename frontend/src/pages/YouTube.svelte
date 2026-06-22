<script>
  import { onDestroy } from 'svelte';
  import { youtubeResults, youtubeNowPlaying, youtubeError, sendWS } from '../stores/assistant.js';
  import VirtualKeyboard from '../components/VirtualKeyboard.svelte';

  let showSearch = false;
  let searchQuery = '';
  let isSearching = false;
  let searchTimeout;

  $: if ($youtubeResults.length > 0) isSearching = false;

  function toggleSearch() {
    showSearch = !showSearch;
    if (!showSearch) {
      searchQuery = '';
    }
  }

  function onKeyboard(e) {
    const { action, char } = e.detail;
    if (action === 'char') searchQuery += char;
    else if (action === 'delete') searchQuery = searchQuery.slice(0, -1);
    else if (action === 'space') searchQuery += ' ';
    triggerSearch();
  }

  function triggerSearch() {
    clearTimeout(searchTimeout);
    if (searchQuery.length < 2) return;
    isSearching = true;
    searchTimeout = setTimeout(() => {
      sendWS({ type: 'youtube_search', data: searchQuery });
    }, 800);
  }

  function selectVideo(result) {
    sendWS({ type: 'youtube_select', data: result });
  }

  function stopVideo() {
    sendWS({ type: 'youtube_stop' });
  }

  function clearResults() {
    youtubeResults.set([]);
    showSearch = false;
    searchQuery = '';
  }

  onDestroy(() => clearTimeout(searchTimeout));
</script>

<div class="youtube-page">

  {#if $youtubeError}
    <div class="yt-error">{$youtubeError}</div>
  {/if}

  {#if $youtubeNowPlaying}
    <!-- NOW PLAYING (VLC is fullscreen over Chromium) -->
    <div class="now-playing-card" style={$youtubeNowPlaying.thumbnail ? `--np-bg: url(${$youtubeNowPlaying.thumbnail})` : ''}>
      <div class="np-bg-overlay"></div>
      <div class="np-content">
        <span class="np-badge"><span class="np-dot"></span>EN LECTURE</span>
        <p class="np-title">{$youtubeNowPlaying.title}</p>
        <p class="np-channel">{$youtubeNowPlaying.channel}</p>
        <button class="stop-btn" on:click={stopVideo}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2"/>
          </svg>
          <span>Arreter la video</span>
        </button>
      </div>
    </div>
    <p class="voice-hint">Dites "Terminator, stop" pour arreter</p>

  {:else if showSearch}
    <!-- SEARCH MODE (keyboard open) -->
    <div class="search-header">
      <div class="search-display search-active">
        {#if searchQuery}
          <span class="search-text">{searchQuery}</span>
        {:else}
          <span class="search-placeholder">Rechercher sur YouTube...</span>
        {/if}
        <span class="cursor"></span>
      </div>
      <button class="close-btn" on:click={toggleSearch}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button>
    </div>

    <div class="search-results">
      {#if isSearching && $youtubeResults.length === 0}
        <p class="loading-text">Recherche...</p>
      {:else if $youtubeResults.length > 0}
        {#each $youtubeResults as result, i}
          <button class="result-card result-stagger" style="animation-delay: {i * 50}ms" on:click={() => selectVideo(result)}>
            <div class="thumb-wrap">
              {#if result.thumbnail}
                <img src={result.thumbnail} alt="" class="result-thumb" loading="lazy" />
              {:else}
                <div class="result-thumb-ph"></div>
              {/if}
              <div class="thumb-play-overlay">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                  <path d="M8 5v14l11-7L8 5z"/>
                </svg>
              </div>
              {#if result.duration}
                <span class="thumb-duration">{result.duration}</span>
              {/if}
            </div>
            <div class="result-info">
              <p class="result-title">{result.title}</p>
              <p class="result-channel"><span class="channel-dot"></span>{result.channel}</p>
            </div>
          </button>
        {/each}
      {:else if searchQuery.length >= 2 && !isSearching}
        <p class="no-results">Aucun resultat</p>
      {/if}
    </div>

    <div class="keyboard-area">
      <VirtualKeyboard on:key={onKeyboard} />
    </div>

  {:else if $youtubeResults.length > 0}
    <!-- RESULTS (full page, no keyboard) -->
    <div class="results-header">
      <button class="icon-btn" on:click={toggleSearch}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
        </svg>
      </button>
      <span class="results-label">YouTube</span>
      <button class="icon-btn" on:click={clearResults}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button>
    </div>
    <div class="full-results">
      {#each $youtubeResults as result, i}
        <button class="result-card large result-stagger" style="animation-delay: {i * 50}ms" on:click={() => selectVideo(result)}>
          <div class="thumb-wrap thumb-wrap-large">
            {#if result.thumbnail}
              <img src={result.thumbnail} alt="" class="result-thumb" loading="lazy" />
            {:else}
              <div class="result-thumb-ph"></div>
            {/if}
            <div class="thumb-play-overlay">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                <path d="M8 5v14l11-7L8 5z"/>
              </svg>
            </div>
            {#if result.duration}
              <span class="thumb-duration">{result.duration}</span>
            {/if}
          </div>
          <div class="result-info">
            <p class="result-title">{result.title}</p>
            <p class="result-channel"><span class="channel-dot"></span>{result.channel}</p>
          </div>
        </button>
      {/each}
    </div>

  {:else}
    <!-- IDLE (empty state) -->
    <div class="empty-state">
      <div class="play-icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="currentColor">
          <path d="M10 8.64L15.27 12 10 15.36V8.64M8 5v14l11-7L8 5z"/>
        </svg>
      </div>
      <p class="empty-title">YouTube</p>
      <p class="empty-subtitle">Rechercher ou demander une video</p>
      <button class="search-prompt" on:click={toggleSearch}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
        </svg>
        <span>Rechercher une video</span>
      </button>
      <p class="voice-hint-idle">Ou dites "Terminator, mets un clip de Stromae"</p>
    </div>
  {/if}
</div>

<style>
  .youtube-page {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 36px 24px 28px;
    position: relative;
  }

  /* Error toast with shake */
  .yt-error {
    position: absolute;
    top: 44px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 20px;
    background: rgba(255,68,68,0.18);
    border: 1px solid rgba(255,68,68,0.4);
    border-radius: 10px;
    color: #ff6b6b;
    font-size: 13px;
    font-weight: 500;
    z-index: 10;
    animation: shakeIn 0.4s ease-out;
  }
  @keyframes shakeIn {
    0% { transform: translateX(-50%) translateX(-12px); opacity: 0; }
    20% { transform: translateX(-50%) translateX(10px); opacity: 1; }
    40% { transform: translateX(-50%) translateX(-8px); }
    60% { transform: translateX(-50%) translateX(5px); }
    80% { transform: translateX(-50%) translateX(-2px); }
    100% { transform: translateX(-50%) translateX(0); }
  }

  /* IDLE empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    text-align: center;
  }
  .play-icon {
    color: #FF0000;
    opacity: 0.85;
    margin-bottom: 4px;
  }
  .empty-title {
    font-size: 24px;
    font-weight: 700;
    color: #f0f0f0;
    letter-spacing: -0.3px;
  }
  .empty-subtitle {
    font-size: 14px;
    color: #888;
    margin-bottom: 8px;
  }

  .search-prompt {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    max-width: 400px;
    height: 52px;
    padding: 0 20px;
    background: rgba(108,99,255,0.08);
    border: 1.5px solid rgba(108,99,255,0.35);
    border-radius: 14px;
    color: #b0abff;
    font-size: 15px;
    font-weight: 500;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: opacity 0.15s ease;
  }
  .search-prompt:active {
    opacity: 0.7;
    transform: scale(0.98);
  }

  .voice-hint-idle {
    font-size: 12px;
    color: #555;
    margin-top: 8px;
    font-style: italic;
  }


  /* SEARCH MODE */
  .search-header {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 0 16px;
    width: 100%;
    flex-shrink: 0;
  }
  .search-display {
    flex: 1;
    height: 44px;
    display: flex;
    align-items: center;
    padding: 0 14px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(108,99,255,0.3);
    border-radius: 10px;
    transition: border-color 0.2s ease;
  }
  .search-display.search-active {
    border-color: rgba(108,99,255,0.6);
    background: rgba(108,99,255,0.06);
  }
  .search-text { font-size: 14px; color: #f0f0f0; }
  .search-placeholder { font-size: 14px; color: #555; }
  .cursor {
    width: 2px;
    height: 16px;
    background: #6c63ff;
    margin-left: 2px;
    animation: blink 1s step-end infinite;
  }
  @keyframes blink {
    50% { opacity: 0; }
  }

  .close-btn, .icon-btn {
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    flex-shrink: 0;
  }
  .close-btn:active, .icon-btn:active { color: #f0f0f0; }

  .search-results {
    flex: 1;
    overflow-y: auto;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 12px;
  }

  .loading-text, .no-results {
    font-size: 13px;
    color: #555;
    text-align: center;
    margin-top: 32px;
  }

  .keyboard-area {
    width: 100%;
    flex-shrink: 0;
  }

  /* RESULT CARDS (shared) */
  .result-card {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 10px 8px;
    min-height: 68px;
    background: none;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    text-align: left;
    -webkit-tap-highlight-color: transparent;
    width: 100%;
    transition: transform 0.1s ease, background-color 0.1s ease;
  }
  .result-card:active {
    transform: scale(0.98);
    background: rgba(108,99,255,0.08);
  }
  .result-card.large { padding: 12px 8px; min-height: 72px; }

  /* Stagger fade-in animation for results */
  .result-stagger {
    animation: fadeSlideIn 0.25s ease-out both;
  }
  @keyframes fadeSlideIn {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Thumbnail wrapper with overlay */
  .thumb-wrap {
    position: relative;
    width: 140px;
    height: 80px;
    flex-shrink: 0;
    border-radius: 8px;
    overflow: hidden;
  }
  .thumb-wrap-large {
    width: 140px;
    height: 80px;
  }

  .result-thumb {
    width: 100%;
    height: 100%;
    border-radius: 8px;
    object-fit: cover;
    background: rgba(255,255,255,0.05);
  }
  .result-thumb-ph {
    width: 100%;
    height: 100%;
    border-radius: 8px;
    background: rgba(255,255,255,0.05);
  }

  /* Play icon overlay on thumbnail */
  .thumb-play-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.25);
    opacity: 0.7;
    border-radius: 8px;
  }

  /* Duration badge on thumbnail */
  .thumb-duration {
    position: absolute;
    bottom: 4px;
    right: 4px;
    padding: 2px 5px;
    background: rgba(0,0,0,0.8);
    border-radius: 4px;
    font-size: 10px;
    font-weight: 500;
    color: #f0f0f0;
    letter-spacing: 0.3px;
    line-height: 1.3;
  }

  .result-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .result-title {
    font-size: 14px;
    font-weight: 500;
    color: #f0f0f0;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .result-channel {
    font-size: 11px;
    color: #888;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .channel-dot {
    display: inline-block;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: #6c63ff;
    flex-shrink: 0;
  }

  /* RESULTS full page header */
  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0 16px 8px;
    flex-shrink: 0;
  }
  .results-label { font-size: 14px; font-weight: 600; color: #f0f0f0; }

  .full-results {
    flex: 1;
    overflow-y: auto;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 0 12px;
  }

  /* NOW PLAYING */
  .now-playing-card {
    position: relative;
    width: 100%;
    max-width: 440px;
    border-radius: 16px;
    overflow: hidden;
    background-image: var(--np-bg);
    background-size: cover;
    background-position: center;
    background-color: rgba(108,99,255,0.08);
    border: 1px solid rgba(108,99,255,0.2);
  }
  .np-bg-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(10,10,15,0.82);
  }
  .np-content {
    position: relative;
    z-index: 1;
    padding: 28px 32px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-align: center;
    align-items: center;
  }
  .np-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #ff4444;
    font-weight: 600;
    margin-bottom: 6px;
  }
  .np-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ff4444;
    animation: pulseDot 1.5s ease-in-out infinite;
  }
  @keyframes pulseDot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  .np-title {
    font-size: 18px;
    font-weight: 600;
    color: #f0f0f0;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .np-channel { font-size: 13px; color: #999; }

  .stop-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-top: 18px;
    width: 100%;
    max-width: 280px;
    height: 48px;
    background: rgba(255,68,68,0.14);
    border: 1px solid rgba(255,68,68,0.3);
    border-radius: 12px;
    color: #ff6b6b;
    font-size: 14px;
    font-weight: 500;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform 0.1s ease;
  }
  .stop-btn:active {
    transform: scale(0.97);
    background: rgba(255,68,68,0.25);
  }

  .voice-hint {
    font-size: 12px;
    color: #555;
    margin-top: 16px;
  }
</style>
