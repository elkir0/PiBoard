<script>
  import { onDestroy } from 'svelte';
  import { camerasData, sendWS, wsConnected, currentPage, fullscreenCam } from '../stores/assistant.js';

  let gridInterval;
  let now = Date.now();
  let tickInterval;

  // Update "now" every second for timestamp display
  tickInterval = setInterval(() => { now = Date.now(); }, 1000);

  // Grid refresh: every 1.5s when on camera page
  $: if ($currentPage === 3 && $wsConnected) {
    sendWS({ type: 'cameras_snapshots' });
    startGridRefresh();
  } else {
    stopGridRefresh();
  }

  function startGridRefresh() {
    stopGridRefresh();
    gridInterval = setInterval(() => {
      if ($currentPage === 3 && $wsConnected) {
        sendWS({ type: 'cameras_snapshots' });
      }
    }, 1500);
  }

  function stopGridRefresh() {
    if (gridInterval) { clearInterval(gridInterval); gridInterval = null; }
  }

  function openFullscreen(cam) {
    fullscreenCam.set(cam);
  }

  function connectedCount(cams) {
    return cams.filter(c => c.state === 'CONNECTED').length;
  }

  function statusLabel(cams) {
    const online = connectedCount(cams);
    const total = cams.length;
    if (online === total) return `${total} en ligne`;
    return `${online}/${total} en ligne`;
  }

  function agoLabel(cam) {
    if (!cam._ts) return '';
    const secs = Math.floor((now - cam._ts) / 1000);
    if (secs < 2) return 'maintenant';
    if (secs < 60) return `il y a ${secs}s`;
    return `il y a ${Math.floor(secs / 60)}min`;
  }

  onDestroy(() => {
    stopGridRefresh();
    if (tickInterval) clearInterval(tickInterval);
  });
</script>

<div class="cameras-page">
  {#if $camerasData.length > 0}
    <!-- Header -->
    <div class="cam-header">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" opacity="0.5">
        <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/>
      </svg>
      <span class="cam-title">Cameras</span>
      <span class="cam-count">{statusLabel($camerasData)}</span>
    </div>

    <!-- Grid -->
    <div class="cam-grid" class:grid-1={$camerasData.length === 1} class:grid-2={$camerasData.length === 2} class:grid-3={$camerasData.length === 3} class:grid-4={$camerasData.length >= 4}>
      {#each $camerasData as cam, i}
        <button
          class="cam-card"
          class:connected={cam.state === 'CONNECTED'}
          class:single={$camerasData.length === 1}
          class:bottom-center={$camerasData.length === 3 && i === 2}
          on:click={() => openFullscreen(cam)}
        >
          <div class="cam-img-wrapper">
            {#if cam.snapshot}
              <img src="data:image/jpeg;base64,{cam.snapshot}" alt={cam.name} class="cam-img" />
            {:else}
              <div class="cam-placeholder">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" opacity="0.25">
                  <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/>
                </svg>
              </div>
            {/if}

            <!-- LIVE badge -->
            {#if cam.state === 'CONNECTED'}
              <div class="live-badge">
                <span class="live-dot"></span>
                <span class="live-text">LIVE</span>
              </div>
            {/if}

            <!-- Timestamp -->
            {#if cam._ts}
              <span class="cam-timestamp">{agoLabel(cam)}</span>
            {/if}

            <!-- Name overlay at bottom of image -->
            <div class="cam-label-overlay">
              <span class="cam-dot" class:online={cam.state === 'CONNECTED'}></span>
              <span class="cam-name">{cam.name}</span>
            </div>
          </div>
        </button>
      {/each}
    </div>

    <!-- Portail button — bottom left -->
    <button class="portail-btn" on:click={() => sendWS({ type: 'domotique_portail' })}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 2v20H4V2h2zm14 0v20h-2V2h2zm-7 4h-2v2H9v2h2v2h2v-2h2V8h-2V6z"/></svg>
      Portail
    </button>

  {:else}
    <!-- Empty state -->
    <div class="empty-state">
      <div class="empty-icon-wrapper">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor" opacity="0.3">
          <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/>
        </svg>
      </div>
      <p class="empty-title">Cameras</p>
      <p class="empty-subtitle">Recherche des cameras...</p>
    </div>
  {/if}
</div>

<style>
  .cameras-page {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 28px 20px 20px;
  }

  /* Header */
  .cam-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 18px;
    color: #888;
  }
  .cam-title {
    font-size: 20px;
    font-weight: 600;
    color: #f0f0f0;
  }
  .cam-count {
    font-size: 12px;
    color: #44ff88;
    background: rgba(68,255,136,0.08);
    padding: 3px 10px;
    border-radius: 10px;
    font-weight: 500;
  }

  /* Portail button — fixed bottom left */
  .portail-btn {
    position: absolute;
    bottom: 12px;
    left: 20px;
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(108, 99, 255, 0.15);
    border: 1px solid rgba(108, 99, 255, 0.3);
    color: #6c63ff;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    -webkit-tap-highlight-color: transparent;
    min-height: 44px;
    z-index: 10;
  }
  .portail-btn:active { opacity: 0.7; transform: scale(0.95); }

  /* Grid layouts */
  .cam-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    width: 100%;
    max-width: 860px;
    justify-content: center;
  }

  /* 1 camera: centered, wider */
  .cam-grid.grid-1 .cam-card {
    width: 70%;
  }

  /* 2 cameras: side by side */
  .cam-grid.grid-2 .cam-card {
    flex: 1 1 45%;
    max-width: 50%;
  }

  /* 3 cameras: first 2 take half, 3rd centered below */
  .cam-grid.grid-3 .cam-card {
    flex: 1 1 45%;
    max-width: calc(50% - 5px);
  }
  .cam-grid.grid-3 .cam-card.bottom-center {
    flex: 0 0 55%;
    max-width: 55%;
  }

  /* 4+ cameras: 2x2 */
  .cam-grid.grid-4 .cam-card {
    flex: 1 1 45%;
    max-width: calc(50% - 5px);
  }

  /* Card */
  .cam-card {
    position: relative;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    overflow: hidden;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    padding: 0;
    display: block;
    transition: transform 0.15s ease-out;
  }
  .cam-card.connected {
    border-color: rgba(68,255,136,0.2);
  }
  .cam-card:active {
    transform: scale(0.97);
  }

  /* Image wrapper */
  .cam-img-wrapper {
    position: relative;
    width: 100%;
    height: 180px;
  }

  .cam-img {
    width: 100%;
    height: 180px;
    object-fit: cover;
    display: block;
  }

  .cam-placeholder {
    width: 100%;
    height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.02);
    color: #555;
  }

  /* LIVE badge */
  .live-badge {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    align-items: center;
    gap: 4px;
    background: rgba(0,0,0,0.55);
    padding: 3px 8px;
    border-radius: 6px;
  }
  .live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #ff3b3b;
    animation: pulse-dot 1.5s ease-in-out infinite;
  }
  .live-text {
    font-size: 10px;
    font-weight: 700;
    color: #ff3b3b;
    letter-spacing: 0.5px;
  }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* Timestamp */
  .cam-timestamp {
    position: absolute;
    bottom: 30px;
    right: 6px;
    font-size: 9px;
    color: rgba(240,240,240,0.5);
    background: rgba(0,0,0,0.45);
    padding: 2px 5px;
    border-radius: 4px;
  }

  /* Name overlay at bottom of image */
  .cam-label-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 16px 10px 8px;
    background: linear-gradient(to bottom, transparent, rgba(0,0,0,0.7));
  }

  .cam-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #555;
    flex-shrink: 0;
  }
  .cam-dot.online {
    background: #44ff88;
  }

  .cam-name {
    font-size: 12px;
    font-weight: 500;
    color: #ddd;
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    color: #555;
  }
  .empty-icon-wrapper {
    animation: pulse-icon 2.5s ease-in-out infinite;
  }
  .empty-title {
    font-size: 22px;
    font-weight: 600;
    color: #f0f0f0;
    margin: 0;
  }
  .empty-subtitle {
    font-size: 13px;
    color: #888;
    margin: 0;
  }

  @keyframes pulse-icon {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 0.6; }
  }
</style>
