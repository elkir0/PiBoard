<script>
  import { onMount } from 'svelte';
  import { isAuthenticated, checkAuth, logout, toastMessage } from './stores/auth.js';

  import Login from './pages/Login.svelte';
  import Dashboard from './pages/Dashboard.svelte';
  import Audio from './pages/Audio.svelte';
  import Voice from './pages/Voice.svelte';
  import Music from './pages/Music.svelte';
  import YouTube from './pages/YouTube.svelte';
  import Weather from './pages/Weather.svelte';
  import Cameras from './pages/Cameras.svelte';
  import Screen from './pages/Screen.svelte';
  import Interface from './pages/Interface.svelte';
  import System from './pages/System.svelte';
  import Logs from './pages/Logs.svelte';

  let activePage = 'dashboard';
  let sidebarOpen = false;
  let toast = null;

  toastMessage.subscribe(v => toast = v);

  const navItems = [
    { id: 'dashboard', label: 'Tableau de bord', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1' },
    { id: 'audio', label: 'Audio & Micro', icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z' },
    { id: 'voice', label: 'Commandes vocales', icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z' },
    { id: 'music', label: 'Musique', icon: 'M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z' },
    { id: 'youtube', label: 'YouTube', icon: 'M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664zM21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    { id: 'weather', label: 'Meteo', icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z' },
    { id: 'cameras', label: 'Cameras', icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
    { id: 'screen', label: 'Ecran & Horaires', icon: 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z' },
    { id: 'interface', label: 'Interface', icon: 'M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01' },
    { id: 'system', label: 'Systeme', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
    { id: 'logs', label: 'Journaux', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01' },
  ];

  function navigate(pageId) {
    activePage = pageId;
    sidebarOpen = false;
  }

  onMount(() => {
    checkAuth();
  });
</script>

{#if !$isAuthenticated}
  <Login />
{:else}
  <div class="layout">
    <button class="hamburger" on:click={() => sidebarOpen = !sidebarOpen}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        {#if sidebarOpen}
          <path d="M6 18L18 6M6 6l12 12" />
        {:else}
          <path d="M4 6h16M4 12h16M4 18h16" />
        {/if}
      </svg>
    </button>

    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    {#if sidebarOpen}
      <div class="overlay" on:click={() => sidebarOpen = false}></div>
    {/if}

    <aside class="sidebar" class:open={sidebarOpen}>
      <div class="sidebar-header">
        <span class="logo">PI-Board</span>
        <span class="logo-sub">Admin</span>
      </div>
      <nav class="sidebar-nav">
        {#each navItems as item}
          <button
            class="nav-item"
            class:active={activePage === item.id}
            on:click={() => navigate(item.id)}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d={item.icon} />
            </svg>
            <span>{item.label}</span>
          </button>
        {/each}
      </nav>
      <button class="nav-item logout-btn" on:click={logout}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
        </svg>
        <span>Deconnexion</span>
      </button>
    </aside>

    <main class="content">
      {#if activePage === 'dashboard'}
        <Dashboard />
      {:else if activePage === 'audio'}
        <Audio />
      {:else if activePage === 'voice'}
        <Voice />
      {:else if activePage === 'music'}
        <Music />
      {:else if activePage === 'youtube'}
        <YouTube />
      {:else if activePage === 'weather'}
        <Weather />
      {:else if activePage === 'cameras'}
        <Cameras />
      {:else if activePage === 'screen'}
        <Screen />
      {:else if activePage === 'interface'}
        <Interface />
      {:else if activePage === 'system'}
        <System />
      {:else if activePage === 'logs'}
        <Logs />
      {/if}
    </main>
  </div>
{/if}

{#if toast}
  <div class="toast" class:error={toast.type === 'error'} class:success={toast.type === 'success'}>
    {toast.text}
  </div>
{/if}

<style>
  .layout {
    display: flex;
    min-height: 100vh;
  }

  .hamburger {
    display: none;
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 1001;
    background: #111118;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    color: #f0f0f0;
    padding: 8px;
    cursor: pointer;
  }

  .overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 999;
  }

  .sidebar {
    width: 240px;
    background: #111118;
    border-right: 1px solid rgba(255,255,255,0.06);
    display: flex;
    flex-direction: column;
    height: 100vh;
    position: sticky;
    top: 0;
    flex-shrink: 0;
    overflow-y: auto;
  }

  .sidebar-header {
    padding: 20px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  .logo {
    font-size: 20px;
    font-weight: 700;
    color: #6c63ff;
  }

  .logo-sub {
    font-size: 12px;
    color: #888;
    font-weight: 500;
  }

  .sidebar-nav {
    flex: 1;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 8px;
    border: none;
    background: none;
    color: #888;
    cursor: pointer;
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    text-align: left;
    width: 100%;
    transition: background 0.15s, color 0.15s;
  }

  .nav-item:hover {
    background: rgba(108, 99, 255, 0.08);
    color: #f0f0f0;
  }

  .nav-item.active {
    background: rgba(108, 99, 255, 0.15);
    color: #6c63ff;
  }

  .logout-btn {
    margin: 8px;
    color: #ff6b6b;
  }

  .logout-btn:hover {
    background: rgba(255, 107, 107, 0.1);
    color: #ff6b6b;
  }

  .content {
    flex: 1;
    padding: 24px;
    min-width: 0;
    overflow-y: auto;
  }

  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    z-index: 2000;
    animation: slideIn 0.3s ease-out;
  }

  .toast.success {
    background: #1a3a2a;
    color: #4ade80;
    border: 1px solid rgba(74, 222, 128, 0.2);
  }

  .toast.error {
    background: #3a1a1a;
    color: #ff6b6b;
    border: 1px solid rgba(255, 107, 107, 0.2);
  }

  @keyframes slideIn {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  @media (max-width: 768px) {
    .hamburger {
      display: block;
    }

    .overlay {
      display: block;
    }

    .sidebar {
      position: fixed;
      left: -240px;
      z-index: 1000;
      transition: left 0.3s ease;
    }

    .sidebar.open {
      left: 0;
    }

    .content {
      padding: 60px 16px 16px;
    }
  }
</style>
