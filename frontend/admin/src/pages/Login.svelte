<script>
  import { login } from '../stores/auth.js';

  let password = '';
  let error = '';
  let loading = false;

  async function handleLogin() {
    if (!password.trim()) return;
    loading = true;
    error = '';
    const result = await login(password);
    loading = false;
    if (!result.ok) {
      error = result.error;
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') handleLogin();
  }
</script>

<div class="login-wrapper">
  <div class="login-card">
    <div class="login-logo">
      <span class="logo-text">PI-Board</span>
      <span class="logo-sub">Administration</span>
    </div>

    {#if error}
      <div class="login-error">{error}</div>
    {/if}

    <div class="form-group">
      <label class="form-label" for="password">Mot de passe</label>
      <input
        id="password"
        type="password"
        bind:value={password}
        on:keydown={handleKeydown}
        placeholder="Entrez le mot de passe admin"
        autocomplete="current-password"
      />
    </div>

    <button class="btn-login" on:click={handleLogin} disabled={loading}>
      {#if loading}
        Connexion...
      {:else}
        Se connecter
      {/if}
    </button>
  </div>
</div>

<style>
  .login-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 16px;
  }

  .login-card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 40px 32px;
    width: 100%;
    max-width: 380px;
  }

  .login-logo {
    text-align: center;
    margin-bottom: 32px;
  }

  .logo-text {
    display: block;
    font-size: 28px;
    font-weight: 700;
    color: #6c63ff;
  }

  .logo-sub {
    display: block;
    font-size: 14px;
    color: #888;
    margin-top: 4px;
  }

  .login-error {
    background: rgba(255, 107, 107, 0.1);
    border: 1px solid rgba(255, 107, 107, 0.2);
    color: #ff6b6b;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
  }

  .form-group {
    margin-bottom: 20px;
  }

  .form-label {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
    display: block;
  }

  input {
    background: #1a1a24;
    border: 1px solid #333;
    color: #f0f0f0;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 14px;
    width: 100%;
    font-family: 'Inter', sans-serif;
  }

  input:focus {
    border-color: #6c63ff;
    outline: none;
  }

  .btn-login {
    width: 100%;
    background: #6c63ff;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    transition: opacity 0.15s;
  }

  .btn-login:hover {
    opacity: 0.9;
  }

  .btn-login:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
