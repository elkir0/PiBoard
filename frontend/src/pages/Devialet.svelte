<script>
  import { devialetData, wsConnected, sendWS } from '../stores/assistant.js';

  let statusRequested = false;

  $: if ($wsConnected && !$devialetData && !statusRequested) {
    statusRequested = true;
    sendWS({ type: 'devialet_status' });
  }
  $: if (!$wsConnected) statusRequested = false;

  $: d = $devialetData || {
    connected: false, model: '', systemName: 'Devialet', firmware: '',
    volume: 0, nightMode: false, eqPreset: 'flat', currentSource: null,
    sources: [], devices: []
  };

  let volumeTimeout;
  function onVolumeInput(e) {
    const vol = parseInt(e.target.value);
    clearTimeout(volumeTimeout);
    volumeTimeout = setTimeout(() => sendWS({ type: 'devialet_volume', data: vol }), 150);
  }

  function volUp() { sendWS({ type: 'devialet_volume_up' }); }
  function volDown() { sendWS({ type: 'devialet_volume_down' }); }
  function toggleMute() { sendWS({ type: d.volume === 0 ? 'devialet_unmute' : 'devialet_mute' }); }
  function play() { sendWS({ type: 'devialet_play' }); }
  function pause() { sendWS({ type: 'devialet_pause' }); }
  function prev() { sendWS({ type: 'devialet_prev' }); }
  function next() { sendWS({ type: 'devialet_next' }); }
  function toggleNight() { sendWS({ type: 'devialet_night_mode', data: !d.nightMode }); }
  function setEq(preset) { sendWS({ type: 'devialet_eq_preset', data: preset }); }

  const sourceLabels = { spotifyconnect: 'Spotify', airplay2: 'AirPlay', bluetooth: 'Bluetooth', optical: 'Optique', upnp: 'UPnP', raat: 'Roon' };
  function getSourceLabel(src) { return sourceLabels[src] || src || 'Veille'; }
</script>

<div class="dev-page">
  <!-- Header with Devialet logo -->
  <div class="dev-header">
    <div class="dev-brand">
      <svg class="dev-logo" width="28" height="28" viewBox="0 0 100 100" fill="currentColor">
        <circle cx="50" cy="50" r="46" fill="none" stroke="currentColor" stroke-width="3"/>
        <text x="50" y="58" text-anchor="middle" font-size="32" font-weight="700" font-family="Inter,sans-serif">D</text>
      </svg>
      <div class="dev-titles">
        <h1>{d.systemName || 'Devialet'}</h1>
        <span class="dev-sub">{d.model}{d.firmware ? ' v' + d.firmware : ''}</span>
      </div>
    </div>
    <div class="dev-status">
      <span class="dev-source-tag">{getSourceLabel(d.currentSource)}</span>
      <span class="dot" class:on={d.connected}></span>
    </div>
  </div>

  {#if !d.connected}
    <div class="dev-offline">Enceinte non detectee</div>
  {:else}
    <!-- Volume -->
    <div class="dev-vol">
      <div class="dev-vol-ring">
        <span class="dev-vol-num">{d.volume ?? '--'}</span>
      </div>
      <div class="dev-vol-bar">
        <button class="ctl" on:click={volDown} aria-label="Vol -">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/></svg>
        </button>
        <input type="range" min="0" max="100" value={d.volume} on:input={onVolumeInput} />
        <button class="ctl" on:click={volUp} aria-label="Vol +">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
        </button>
      </div>
    </div>

    <!-- Playback controls -->
    <div class="dev-playback">
      <button class="ctl" on:click={prev}><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg></button>
      <button class="ctl play" on:click={d.currentSource ? pause : play}>
        {#if d.currentSource}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
        {:else}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        {/if}
      </button>
      <button class="ctl" on:click={next}><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg></button>
      <button class="ctl" class:active={d.volume === 0} on:click={toggleMute}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          {#if d.volume === 0}
            <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
          {:else}
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
          {/if}
        </svg>
      </button>
    </div>

    <!-- Stereo + Settings in one row -->
    <div class="dev-bottom">
      {#if d.devices && d.devices.length > 1}
        <div class="dev-stereo">
          {#each d.devices as dev}
            <div class="spk" class:leader={dev.isLeader}>
              <span class="spk-lr">{dev.role === 'FrontLeft' ? 'L' : 'R'}</span>
              <span class="spk-name">{dev.name}</span>
            </div>
          {/each}
        </div>
      {/if}

      <div class="dev-settings">
        <button class="night" class:active={d.nightMode} on:click={toggleNight}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M9.37 5.51A7.35 7.35 0 0 0 9.1 7.5c0 4.08 3.32 7.4 7.4 7.4.68 0 1.35-.09 1.99-.27A7.014 7.014 0 0 1 12 19c-3.86 0-7-3.14-7-7 0-2.93 1.81-5.45 4.37-6.49z"/></svg>
          Nuit
        </button>
        <div class="eq-grp">
          {#each ['flat', 'custom', 'voice'] as p}
            <button class="eq" class:active={d.eqPreset === p} on:click={() => setEq(p)}>{p === 'flat' ? 'Flat' : p === 'custom' ? 'Custom' : 'Voice'}</button>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .dev-page { width: 100%; height: 100%; display: flex; flex-direction: column; padding: 20px 24px 16px; gap: 12px; }

  /* Header */
  .dev-header { display: flex; align-items: center; justify-content: space-between; }
  .dev-brand { display: flex; align-items: center; gap: 10px; }
  .dev-logo { color: #6c63ff; }
  .dev-titles h1 { font-size: 18px; font-weight: 700; color: #f0f0f0; margin: 0; }
  .dev-sub { font-size: 10px; color: #555; }
  .dev-status { display: flex; align-items: center; gap: 8px; }
  .dev-source-tag { font-size: 11px; color: #6c63ff; font-weight: 500; background: rgba(108,99,255,0.1); padding: 3px 10px; border-radius: 10px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #ff4444; }
  .dot.on { background: #4caf50; }
  .dev-offline { flex: 1; display: flex; align-items: center; justify-content: center; color: #555; }

  /* Volume */
  .dev-vol { display: flex; flex-direction: column; align-items: center; gap: 10px; }
  .dev-vol-ring { width: 100px; height: 100px; border-radius: 50%; border: 3px solid rgba(108,99,255,0.35); display: flex; align-items: center; justify-content: center; }
  .dev-vol-num { font-size: 36px; font-weight: 700; color: #f0f0f0; font-variant-numeric: tabular-nums; }
  .dev-vol-bar { display: flex; align-items: center; gap: 8px; width: 100%; max-width: 360px; }
  .dev-vol-bar input { -webkit-appearance: none; appearance: none; flex: 1; height: 5px; border-radius: 3px; background: rgba(255,255,255,0.1); outline: none; }
  .dev-vol-bar input::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; border-radius: 50%; background: #6c63ff; cursor: pointer; }

  /* Shared button */
  .ctl { background: none; border: none; color: #888; padding: 8px; cursor: pointer; border-radius: 50%; display: flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; -webkit-tap-highlight-color: transparent; }
  .ctl:active { color: #f0f0f0; transform: scale(0.9); }
  .ctl.play { background: #6c63ff; color: #fff; min-width: 50px; min-height: 50px; }
  .ctl.play:active { opacity: 0.85; }
  .ctl.active { color: #6c63ff; }

  /* Playback */
  .dev-playback { display: flex; align-items: center; justify-content: center; gap: 8px; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 8px 16px; }

  /* Bottom: stereo + settings */
  .dev-bottom { display: flex; flex-direction: column; gap: 10px; margin-top: auto; }

  .dev-stereo { display: flex; gap: 8px; }
  .spk { flex: 1; display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.03); border-radius: 8px; padding: 8px 12px; border: 1px solid transparent; }
  .spk.leader { border-color: rgba(108,99,255,0.2); }
  .spk-lr { font-size: 12px; font-weight: 700; color: #6c63ff; }
  .spk-name { font-size: 11px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .dev-settings { display: flex; align-items: center; justify-content: space-between; }
  .night { display: flex; align-items: center; gap: 5px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); color: #666; font-size: 11px; font-weight: 500; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; min-height: 40px; }
  .night.active { color: #ffd54f; border-color: rgba(255,213,79,0.3); }
  .eq-grp { display: flex; gap: 3px; background: rgba(255,255,255,0.03); border-radius: 8px; padding: 3px; }
  .eq { background: none; border: none; color: #555; font-size: 11px; font-weight: 500; padding: 7px 14px; border-radius: 6px; cursor: pointer; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; min-height: 40px; }
  .eq.active { background: rgba(108,99,255,0.2); color: #6c63ff; font-weight: 600; }
</style>
