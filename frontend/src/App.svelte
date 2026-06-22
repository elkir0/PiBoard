<script>
  import { onMount } from 'svelte';
  import { currentPage, assistantState, connectWS, wsConnected, fullscreenCam, transcript, speakingText, showSettings, audioSinks, sendWS } from './stores/assistant.js';
  import Music from './pages/Music.svelte';
  import Weather from './pages/Weather.svelte';
  import YouTube from './pages/YouTube.svelte';
  import Cameras from './pages/Cameras.svelte';
  import Devialet from './pages/Devialet.svelte';
  import Domotique from './pages/Domotique.svelte';
  import WaveAnimation from './components/WaveAnimation.svelte';

  const pages = [
    { name: 'Musique' },
    { name: 'Meteo' },
    { name: 'YouTube' },
    { name: 'Cameras' },
    { name: 'Devialet' },
    { name: 'Maison' }
  ];

  let touchStartX = 0;
  let touchDeltaX = 0;
  let swiping = false;
  let dragOffset = 0;

  onMount(() => {
    connectWS();
  });

  function onTouchStart(e) {
    // Don't swipe when settings panel is open
    if ($showSettings) return;
    touchStartX = e.touches[0].clientX;
    swiping = true;
    touchDeltaX = 0;
    dragOffset = 0;
  }

  function onTouchMove(e) {
    if (!swiping) return;
    touchDeltaX = e.touches[0].clientX - touchStartX;
    const maxDrag = 80;
    dragOffset = Math.sign(touchDeltaX) * Math.min(Math.abs(touchDeltaX) * 0.3, maxDrag);
  }

  function onTouchEnd() {
    if (!swiping) return;
    swiping = false;

    if (Math.abs(touchDeltaX) > 60) {
      if (touchDeltaX < 0 && $currentPage < 5) {
        currentPage.set($currentPage + 1);
      } else if (touchDeltaX > 0 && $currentPage > 0) {
        currentPage.set($currentPage - 1);
      }
    }
    touchDeltaX = 0;
    dragOffset = 0;
  }

  function openSettings() {
    showSettings.set(true);
    sendWS({ type: 'audio_sinks' });
  }

  function closeSettings() {
    showSettings.set(false);
    showShutdownConfirm = false;
  }

  let showShutdownConfirm = false;
  function shutdown() {
    if (!showShutdownConfirm) {
      showShutdownConfirm = true;
      return;
    }
    sendWS({ type: 'system_shutdown' });
    showShutdownConfirm = false;
  }

  function selectSink(name) {
    sendWS({ type: 'audio_set_sink', data: name });
  }

  // Clock
  let time = '';
  function updateClock() {
    const now = new Date();
    time = now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }
  onMount(() => {
    updateClock();
    const interval = setInterval(updateClock, 10000);
    return () => clearInterval(interval);
  });
</script>

<div
  class="container"
  on:touchstart={onTouchStart}
  on:touchmove={onTouchMove}
  on:touchend={onTouchEnd}
>
  <div class="ambient-bg" class:listening={$assistantState === 'LISTENING'} class:speaking={$assistantState === 'SPEAKING'}></div>

  <header class="top-bar">
    <span class="clock">{time}</span>
    <span class="brand">pi-board</span>
    <div class="top-right">
      <button class="settings-btn" on:click={openSettings} aria-label="Parametres">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1115.6 12 3.6 3.6 0 0112 15.6z"/>
        </svg>
      </button>
      <span class="ws-dot" class:connected={$wsConnected}></span>
    </div>
  </header>

  <div
    class="pages"
    class:dragging={swiping}
    style="transform: translateX(calc({-$currentPage * 100}vw + {dragOffset}px))"
  >
    <div class="page" class:page-hidden={$currentPage !== 0}><Music /></div>
    <div class="page" class:page-hidden={$currentPage !== 1}><Weather /></div>
    <div class="page" class:page-hidden={$currentPage !== 2}><YouTube /></div>
    <div class="page" class:page-hidden={$currentPage !== 3}><Cameras /></div>
    <div class="page" class:page-hidden={$currentPage !== 4}><Devialet /></div>
    <div class="page" class:page-hidden={$currentPage !== 5}><Domotique /></div>
  </div>

  <nav class="indicators">
    {#each pages as p, i}
      <button
        class="indicator"
        class:active={$currentPage === i}
        on:click={() => currentPage.set(i)}
        aria-label={p.name}
      >
        <span class="indicator-dot"></span>
        {#if $currentPage === i}
          <span class="indicator-label">{p.name}</span>
        {/if}
      </button>
    {/each}
  </nav>

  {#if $assistantState === 'LISTENING' || $assistantState === 'SPEAKING' || $assistantState === 'PROCESSING'}
    <div class="voice-pill">
      <WaveAnimation state={$assistantState} />
      <span class="voice-label">
        {#if $assistantState === 'LISTENING'}Ecoute...
        {:else if $assistantState === 'PROCESSING'}
          {#if $transcript}"{$transcript}"{:else}Reflexion...{/if}
        {:else}
          {#if $speakingText}{$speakingText}{:else}Parle...{/if}
        {/if}
      </span>
    </div>
  {/if}

  {#if $showSettings}
    <div class="settings-overlay" on:click|self={closeSettings} on:touchstart|stopPropagation on:touchmove|stopPropagation on:touchend|stopPropagation>
      <div class="settings-panel">
        <div class="settings-header">
          <h2 class="settings-title">Parametres</h2>
          <button class="settings-close" on:click={closeSettings}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </div>

        <div class="settings-section">
          <span class="settings-label">Sortie audio</span>
          <div class="sinks-list">
            {#each $audioSinks.sinks as sink}
              <button
                class="sink-item"
                class:active={sink.is_default}
                on:click={() => selectSink(sink.name)}
              >
                <div class="sink-info">
                  <span class="sink-desc">{sink.description}</span>
                  <span class="sink-name">{sink.name}</span>
                </div>
                {#if sink.is_default}
                  <svg class="sink-check" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                  </svg>
                {/if}
                {#if sink.state === 'RUNNING'}
                  <span class="sink-active-dot"></span>
                {/if}
              </button>
            {/each}
            {#if $audioSinks.sinks.length === 0}
              <p class="sinks-empty">Chargement...</p>
            {/if}
          </div>
        </div>

        <div class="settings-section">
          <span class="settings-label">Systeme</span>
          <div class="settings-info">
            <span class="info-row">
              <span class="info-key">WebSocket</span>
              <span class="info-val" class:ok={$wsConnected}>{$wsConnected ? 'Connecte' : 'Deconnecte'}</span>
            </span>
            <span class="info-row">
              <span class="info-key">Admin</span>
              <a class="info-link" href="/admin/" target="_blank">Ouvrir le panneau</a>
            </span>
          </div>
          <button class="shutdown-btn" class:confirm={showShutdownConfirm} on:click={shutdown}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/>
            </svg>
            {showShutdownConfirm ? 'Confirmer extinction' : 'Eteindre PI-Board'}
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if $fullscreenCam}
    <button class="cam-fullscreen" on:click={() => fullscreenCam.set(null)}>
      <img src="/api/cameras/{$fullscreenCam.id}/stream" alt={$fullscreenCam.name} class="cam-fs-img" />
      <div class="cam-fs-bar">
        <span class="cam-fs-name">{$fullscreenCam.name}</span>
        <span class="cam-fs-hint">Appuyez pour fermer</span>
      </div>
    </button>
  {/if}
</div>

<style>
  .container {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    position: relative;
    background: #0a0a0f;
    touch-action: pan-x;
  }

  .ambient-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    opacity: 0.12;
    background: radial-gradient(ellipse 60% 40% at 50% 120%, #6c63ff, transparent);
    transition: opacity 800ms ease;
    pointer-events: none;
  }
  .ambient-bg.listening {
    opacity: 0.25;
    background: radial-gradient(ellipse 80% 50% at 50% 100%, #6c63ff, transparent);
  }
  .ambient-bg.speaking {
    opacity: 0.2;
    background: radial-gradient(ellipse 70% 45% at 50% 100%, #8b7fff, transparent);
  }

  .top-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    background: linear-gradient(to bottom, rgba(10,10,15,0.95) 0%, transparent 100%);
  }

  .clock {
    font-size: 13px;
    font-weight: 500;
    color: #888;
  }

  .brand {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #6c63ff;
    opacity: 0.7;
  }

  .ws-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #ff4444;
    transition: background 500ms ease;
  }
  .ws-dot.connected {
    background: #44ff88;
  }

  /* Horizontal swipe pages */
  .pages {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: row;
    transition: transform 400ms cubic-bezier(0.22, 1, 0.36, 1);
    will-change: transform;
  }
  .pages.dragging {
    transition: none;
  }

  .page {
    width: 100vw;
    height: 100vh;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
  }

  /* Pause ALL animations and demote GPU layers on non-visible pages */
  .page-hidden :global(*) {
    animation-play-state: paused !important;
    will-change: auto !important;
  }
  .page-hidden {
    visibility: hidden;
  }

  /* Bottom horizontal dots */
  .indicators {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    flex-direction: row;
    justify-content: center;
    gap: 4px;
    z-index: 20;
    align-items: center;
    padding: 6px 0 10px;
  }

  .indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 14px 24px;
    -webkit-tap-highlight-color: transparent;
  }

  .indicator-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(255,255,255,0.2);
    transition: background 300ms ease, transform 300ms ease;
  }
  .indicator.active .indicator-dot {
    background: #6c63ff;
    transform: scale(1.3);
  }

  .indicator-label {
    font-size: 11px;
    color: #6c63ff;
    font-weight: 500;
    letter-spacing: 0.5px;
  }

  .voice-pill {
    position: fixed;
    top: 36px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 30;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: rgba(108, 99, 255, 0.15);
    border: 1px solid rgba(108, 99, 255, 0.3);
    border-radius: 20px;
    backdrop-filter: blur(8px);
    animation: pillIn 200ms ease-out;
  }

  .voice-label {
    font-size: 11px;
    font-weight: 500;
    color: #6c63ff;
    max-width: 500px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @keyframes pillIn {
    from { transform: translateX(-50%) scale(0.8); opacity: 0; }
    to { transform: translateX(-50%) scale(1); opacity: 1; }
  }

  /* ──── Settings ──── */
  .top-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .settings-btn {
    background: none;
    border: none;
    color: #555;
    padding: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    -webkit-tap-highlight-color: transparent;
    transition: color 200ms;
  }
  .settings-btn:active { color: #f0f0f0; }

  .settings-overlay {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    justify-content: flex-end;
  }

  .settings-panel {
    width: 340px;
    max-width: 85vw;
    height: 100%;
    background: #111118;
    border-left: 1px solid rgba(255,255,255,0.06);
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 24px;
    animation: slideIn 250ms ease-out;
  }

  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }

  .settings-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .settings-title {
    font-size: 18px;
    font-weight: 700;
    color: #f0f0f0;
    margin: 0;
  }

  .settings-close {
    background: none;
    border: none;
    color: #888;
    padding: 8px;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .settings-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .settings-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #6c63ff;
    font-weight: 600;
  }

  .sinks-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .sink-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    text-align: left;
    -webkit-tap-highlight-color: transparent;
    transition: border-color 200ms;
  }
  .sink-item:active { background: rgba(255,255,255,0.06); }
  .sink-item.active {
    border-color: rgba(108, 99, 255, 0.4);
    background: rgba(108, 99, 255, 0.08);
  }

  .sink-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .sink-desc {
    font-size: 13px;
    color: #f0f0f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sink-name {
    font-size: 10px;
    color: #555;
    font-family: monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sink-check {
    color: #6c63ff;
    flex-shrink: 0;
  }

  .sink-active-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #44ff88;
    flex-shrink: 0;
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .sinks-empty {
    color: #555;
    font-size: 13px;
    padding: 12px;
  }

  .settings-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
  }

  .info-key {
    font-size: 13px;
    color: #888;
  }

  .info-val {
    font-size: 13px;
    color: #ff6b6b;
    font-weight: 500;
  }
  .info-val.ok { color: #44ff88; }

  .info-link {
    font-size: 12px;
    color: #6c63ff;
    text-decoration: none;
  }

  .shutdown-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    justify-content: center;
    background: rgba(255, 68, 68, 0.08);
    border: 1px solid rgba(255, 68, 68, 0.2);
    color: #ff6b6b;
    font-size: 12px;
    font-weight: 500;
    padding: 10px;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    -webkit-tap-highlight-color: transparent;
    margin-top: 8px;
    min-height: 44px;
  }
  .shutdown-btn:active { opacity: 0.7; }
  .shutdown-btn.confirm {
    background: rgba(255, 68, 68, 0.25);
    border-color: rgba(255, 68, 68, 0.5);
    font-weight: 700;
  }

  .cam-fullscreen {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    cursor: pointer;
    padding: 0;
    -webkit-tap-highlight-color: transparent;
  }
  .cam-fs-img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .cam-fs-placeholder {
    color: #555;
    font-size: 16px;
  }
  .cam-fs-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 12px 16px;
    background: linear-gradient(transparent, rgba(0,0,0,0.8));
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .cam-fs-name {
    font-size: 14px;
    font-weight: 500;
    color: #f0f0f0;
  }
  .cam-fs-hint {
    font-size: 11px;
    color: #555;
  }
</style>
