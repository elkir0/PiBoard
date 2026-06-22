import { writable } from 'svelte/store';

export const isAuthenticated = writable(false);
export const toastMessage = writable(null);

let toastTimer = null;

function showToast(text, type = 'success') {
  if (toastTimer) clearTimeout(toastTimer);
  toastMessage.set({ text, type });
  toastTimer = setTimeout(() => toastMessage.set(null), 3000);
}

export { showToast };

function getBaseUrl() {
  if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }
  return '';
}

async function handleResponse(res) {
  if (res.status === 401) {
    isAuthenticated.set(false);
    return null;
  }
  return res;
}

export async function login(password) {
  try {
    const res = await fetch(`${getBaseUrl()}/admin/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: 'admin', password }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.token) {
        localStorage.setItem('admin_token', data.token);
      }
      isAuthenticated.set(true);
      return { ok: true };
    }
    return { ok: false, error: 'Mot de passe incorrect' };
  } catch (e) {
    return { ok: false, error: 'Impossible de contacter le serveur' };
  }
}

export async function logout() {
  try {
    await fetch(`${getBaseUrl()}/admin/api/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
    });
  } catch (e) {
    // ignore
  }
  localStorage.removeItem('admin_token');
  isAuthenticated.set(false);
}

export async function checkAuth() {
  try {
    const res = await fetch(`${getBaseUrl()}/admin/api/auth-check`, {
      credentials: 'include',
      headers: authHeaders(),
    });
    if (res.ok) {
      isAuthenticated.set(true);
      return true;
    }
    isAuthenticated.set(false);
    return false;
  } catch (e) {
    isAuthenticated.set(false);
    return false;
  }
}

function authHeaders() {
  const token = localStorage.getItem('admin_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function apiGet(url) {
  try {
    const res = await fetch(`${getBaseUrl()}${url}`, {
      credentials: 'include',
      headers: authHeaders(),
    });
    const handled = await handleResponse(res);
    if (!handled) return null;
    if (handled.ok) return await handled.json();
    return null;
  } catch (e) {
    showToast('Erreur de connexion', 'error');
    return null;
  }
}

export async function apiPut(url, data) {
  try {
    const res = await fetch(`${getBaseUrl()}${url}`, {
      method: 'PUT',
      credentials: 'include',
      headers: authHeaders(),
      body: JSON.stringify(data),
    });
    const handled = await handleResponse(res);
    if (!handled) return { ok: false };
    return { ok: handled.ok, data: handled.ok ? await handled.json() : null };
  } catch (e) {
    showToast('Erreur de connexion', 'error');
    return { ok: false };
  }
}

export async function apiPost(url, data) {
  try {
    const res = await fetch(`${getBaseUrl()}${url}`, {
      method: 'POST',
      credentials: 'include',
      headers: authHeaders(),
      body: JSON.stringify(data),
    });
    const handled = await handleResponse(res);
    if (!handled) return { ok: false };
    return { ok: handled.ok, data: handled.ok ? await handled.json() : null };
  } catch (e) {
    showToast('Erreur de connexion', 'error');
    return { ok: false };
  }
}
