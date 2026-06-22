<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { apiGet } from '../stores/auth.js';

  let logs = '';
  let loading = true;
  let autoRefresh = true;
  let interval = null;
  let logsContainer;
  let filterText = '';

  async function fetchLogs() {
    const data = await apiGet('/admin/api/logs?lines=100');
    if (data && data.lines != null) {
      logs = Array.isArray(data.lines) ? data.lines.join('\n') : data.lines;
    }
  }

  async function scrollToBottom() {
    await tick();
    if (logsContainer) {
      logsContainer.scrollTop = logsContainer.scrollHeight;
    }
  }

  function startInterval() {
    if (interval) clearInterval(interval);
    if (autoRefresh) {
      interval = setInterval(async () => {
        await fetchLogs();
        await scrollToBottom();
      }, 5000);
    }
  }

  function toggleAutoRefresh() {
    autoRefresh = !autoRefresh;
    if (autoRefresh) {
      startInterval();
    } else if (interval) {
      clearInterval(interval);
      interval = null;
    }
  }

  function getLineClass(line) {
    if (!line) return '';
    if (line.includes('[ERROR]') || line.includes('ERROR')) return 'log-error';
    if (line.includes('[WARNING]') || line.includes('WARNING')) return 'log-warning';
    if (line.includes('[AUTH]')) return 'log-auth';
    if (line.includes('[WS]') || line.includes('[WEBSOCKET]')) return 'log-ws';
    return '';
  }

  $: filteredLines = (() => {
    const allLines = logs ? logs.split('\n') : [];
    if (!filterText.trim()) return allLines;
    const lower = filterText.toLowerCase();
    return allLines.filter(line => line.toLowerCase().includes(lower));
  })();

  onMount(async () => {
    await fetchLogs();
    loading = false;
    await scrollToBottom();
    startInterval();
  });

  onDestroy(() => {
    if (interval) clearInterval(interval);
  });
</script>

<div class="page">
  <div class="page-header">
    <h1 class="page-title">Journaux</h1>
    <div class="header-actions">
      <button class="btn-toggle" class:active={autoRefresh} on:click={toggleAutoRefresh}>
        {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
      </button>
      <button class="btn-scroll" on:click={scrollToBottom}>Aller en bas</button>
      <button class="btn-scroll" on:click={fetchLogs}>Rafraichir</button>
    </div>
  </div>

  <div class="filter-row">
    <input
      type="text"
      class="filter-input"
      bind:value={filterText}
      placeholder="Filtrer les logs..."
    />
    {#if filterText}
      <span class="filter-count">{filteredLines.length} ligne{filteredLines.length !== 1 ? 's' : ''}</span>
    {/if}
  </div>

  {#if loading}
    <div class="loading">Chargement...</div>
  {:else}
    <div class="logs-card">
      <div class="logs-content" bind:this={logsContainer}>
        {#if filteredLines.length === 0}
          <span class="no-logs">Aucun log disponible.</span>
        {:else}
          {#each filteredLines as line}
            <div class="log-line {getLineClass(line)}">{line}</div>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .page {
    max-width: 100%;
    display: flex;
    flex-direction: column;
    height: calc(100vh - 48px);
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .page-title {
    font-size: 22px;
    font-weight: 700;
  }

  .header-actions {
    display: flex;
    gap: 8px;
  }

  .filter-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .filter-input {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-family: 'Inter', sans-serif;
    flex: 1;
    max-width: 400px;
  }

  .filter-input:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .filter-input::placeholder {
    color: #555;
  }

  .filter-count {
    font-size: 12px;
    color: #666;
    white-space: nowrap;
  }

  .loading {
    color: #888;
    padding: 40px;
    text-align: center;
  }

  .btn-toggle {
    background: #1a1a24;
    border: 1px solid #333;
    color: #888;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.15s, color 0.15s;
  }

  .btn-toggle.active {
    border-color: rgba(74, 222, 128, 0.3);
    color: #4ade80;
  }

  .btn-toggle:hover {
    border-color: #6c63ff;
    color: #f0f0f0;
  }

  .btn-scroll {
    background: #1a1a24;
    border: 1px solid #333;
    color: #888;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.15s, color 0.15s;
  }

  .btn-scroll:hover {
    border-color: #6c63ff;
    color: #f0f0f0;
  }

  .logs-card {
    background: #0a0a0f;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .logs-content {
    padding: 16px;
    margin: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #ccc;
    overflow-y: auto;
    height: 100%;
  }

  .no-logs {
    color: #666;
  }

  .log-line {
    white-space: pre-wrap;
    word-break: break-all;
  }

  .log-line.log-error {
    color: #ff6b6b;
  }

  .log-line.log-warning {
    color: #fbbf24;
  }

  .log-line.log-auth {
    color: #60a5fa;
  }

  .log-line.log-ws {
    color: #555;
  }

  @media (max-width: 768px) {
    .page {
      height: calc(100vh - 76px);
    }

    .page-header {
      flex-direction: column;
      align-items: flex-start;
    }
  }
</style>
