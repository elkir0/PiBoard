<script>
  import { domotiqueData, wsConnected, sendWS } from '../stores/assistant.js';

  let statusRequested = false;

  $: if ($wsConnected && !$domotiqueData && !statusRequested) {
    statusRequested = true;
    sendWS({ type: 'domotique_status' });
  }
  $: if (!$wsConnected) statusRequested = false;

  $: devices = $domotiqueData || {
    volet_gauche: { name: 'Volet Gauche', type: 'shelly_roller', position: 0, state: 'stop' },
    volet_milieu: { name: 'Volet Milieu', type: 'shelly_roller', position: 0, state: 'stop' },
    volet_droit: { name: 'Volet Droit', type: 'shelly_cover_g2', position: 0, state: 'stop' },
    portail: { name: 'Portail', type: 'shelly_relay_g3', on: false },
    guinguette: { name: 'Guinguette', type: 'kasa_plug', on: false }
  };

  function isRoller(dev) {
    return dev.type === 'shelly_roller' || dev.type === 'shelly_cover_g2';
  }

  function roller(id, action) {
    sendWS({ type: 'domotique_roller', data: { id, action } });
  }
  function triggerGate() {
    sendWS({ type: 'domotique_portail' });
  }
  function plug(id, action) {
    sendWS({ type: 'domotique_plug', data: { id, action } });
  }
  function allRollers(action) {
    roller('volet_gauche', action);
    roller('volet_milieu', action);
    roller('volet_droit', action);
  }
</script>

<div class="dom-page">
  <div class="dom-header">
    <div class="dom-title">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="#6c63ff"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
      <h1>Domotique</h1>
    </div>
    <div class="dom-actions">
      <button class="hdr-btn" on:click={() => allRollers('open')}>Ouvrir tout</button>
      <button class="hdr-btn" on:click={() => allRollers('close')}>Fermer tout</button>
    </div>
  </div>

  <div class="dom-grid">
    <!-- Volet Gauche -->
    <div class="card">
      <div class="card-label">{devices.volet_gauche.name}</div>
      <div class="card-pos">{devices.volet_gauche.position ?? 0}%</div>
      <div class="card-state">{devices.volet_gauche.state === 'stop' ? 'Arrete' : devices.volet_gauche.state === 'open' ? 'Ouverture...' : 'Fermeture...'}</div>
      <div class="roller-btns">
        <button class="ctl" on:click={() => roller('volet_gauche', 'open')} aria-label="Ouvrir">&#9650;</button>
        <button class="ctl stop" on:click={() => roller('volet_gauche', 'stop')} aria-label="Stop">&#9632;</button>
        <button class="ctl" on:click={() => roller('volet_gauche', 'close')} aria-label="Fermer">&#9660;</button>
      </div>
    </div>

    <!-- Volet Milieu -->
    <div class="card">
      <div class="card-label">{devices.volet_milieu.name}</div>
      <div class="card-pos">{devices.volet_milieu.position ?? 0}%</div>
      <div class="card-state">{devices.volet_milieu.state === 'stop' ? 'Arrete' : devices.volet_milieu.state === 'open' ? 'Ouverture...' : 'Fermeture...'}</div>
      <div class="roller-btns">
        <button class="ctl" on:click={() => roller('volet_milieu', 'open')} aria-label="Ouvrir">&#9650;</button>
        <button class="ctl stop" on:click={() => roller('volet_milieu', 'stop')} aria-label="Stop">&#9632;</button>
        <button class="ctl" on:click={() => roller('volet_milieu', 'close')} aria-label="Fermer">&#9660;</button>
      </div>
    </div>

    <!-- Volet Droit -->
    <div class="card">
      <div class="card-label">{devices.volet_droit.name}</div>
      <div class="card-pos">{devices.volet_droit.position ?? 0}%</div>
      <div class="card-state">{devices.volet_droit.state === 'stop' ? 'Arrete' : devices.volet_droit.state === 'open' ? 'Ouverture...' : 'Fermeture...'}</div>
      <div class="roller-btns">
        <button class="ctl" on:click={() => roller('volet_droit', 'open')} aria-label="Ouvrir">&#9650;</button>
        <button class="ctl stop" on:click={() => roller('volet_droit', 'stop')} aria-label="Stop">&#9632;</button>
        <button class="ctl" on:click={() => roller('volet_droit', 'close')} aria-label="Fermer">&#9660;</button>
      </div>
    </div>

    <!-- Portail -->
    <div class="card">
      <div class="card-label">{devices.portail.name}</div>
      <svg class="card-icon" width="40" height="40" viewBox="0 0 24 24" fill="#888"><path d="M21 10H3V8l9-6 9 6v2zm-2 2v6h-3v-6h-2v6h-4v-6H8v6H5v-6H3v8h18v-8h-2z"/></svg>
      <button class="gate-btn" on:click={triggerGate}>
        {devices.portail.on ? 'Fermer' : 'Ouvrir'}
      </button>
    </div>

    <!-- Guinguette -->
    <div class="card">
      <div class="card-label">{devices.guinguette.name}</div>
      <svg class="card-icon" width="40" height="40" viewBox="0 0 24 24" fill={devices.guinguette.on ? '#4caf50' : '#888'}><path d="M16.01 7L16 3H8v4l-5 5v9c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-9l-4.99-5zM10 5h4v2h-4V5zm1 13.5V15H8l4-7v5.5h3l-4 7z"/></svg>
      <button class="plug-btn" class:on={devices.guinguette.on} on:click={() => plug('guinguette', devices.guinguette.on ? 'off' : 'on')}>
        {devices.guinguette.on ? 'ON' : 'OFF'}
      </button>
    </div>
  </div>
</div>

<style>
  .dom-page { width: 100%; height: 100%; display: flex; flex-direction: column; padding: 16px 20px 12px; gap: 10px; }

  .dom-header { display: flex; align-items: center; justify-content: space-between; }
  .dom-title { display: flex; align-items: center; gap: 8px; }
  .dom-title h1 { font-size: 18px; font-weight: 700; color: #f0f0f0; margin: 0; }
  .dom-actions { display: flex; gap: 6px; }
  .hdr-btn { background: rgba(108,99,255,0.12); border: 1px solid rgba(108,99,255,0.25); color: #6c63ff; font-size: 11px; font-weight: 600; padding: 6px 12px; border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; min-height: 36px; }
  .hdr-btn:active { opacity: 0.7; }

  .dom-grid { flex: 1; display: grid; grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 10px; min-height: 0; }

  .card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 12px 8px; }
  .card-label { font-size: 13px; font-weight: 600; color: #f0f0f0; }
  .card-pos { font-size: 24px; font-weight: 700; color: #6c63ff; font-variant-numeric: tabular-nums; }
  .card-state { font-size: 10px; color: #555; }
  .card-icon { margin: 4px 0; }

  .roller-btns { display: flex; gap: 8px; margin-top: 4px; }
  .ctl { background: rgba(255,255,255,0.06); border: none; color: #ccc; font-size: 16px; width: 44px; height: 44px; border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; -webkit-tap-highlight-color: transparent; }
  .ctl:active { background: rgba(108,99,255,0.3); color: #fff; }
  .ctl.stop { color: #ff5252; }

  .gate-btn { background: rgba(108,99,255,0.15); border: 2px solid rgba(108,99,255,0.4); color: #6c63ff; font-size: 14px; font-weight: 700; width: 120px; height: 48px; border-radius: 12px; cursor: pointer; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
  .gate-btn:active { background: rgba(108,99,255,0.35); }

  .plug-btn { background: rgba(255,255,255,0.06); border: 2px solid rgba(255,255,255,0.1); color: #888; font-size: 14px; font-weight: 700; width: 80px; height: 48px; border-radius: 24px; cursor: pointer; font-family: 'Inter', sans-serif; -webkit-tap-highlight-color: transparent; }
  .plug-btn.on { background: rgba(76,175,80,0.2); border-color: rgba(76,175,80,0.5); color: #4caf50; }
  .plug-btn:active { opacity: 0.7; }
</style>
