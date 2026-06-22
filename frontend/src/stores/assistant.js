import { writable, derived } from 'svelte/store';

export const currentPage = writable(0);
export const assistantState = writable('IDLE');
export const wsConnected = writable(false);
export const transcript = writable('');
export const musicData = writable({ playing: false });
export const weatherData = writable(null);
export const youtubeResults = writable([]);
export const youtubeNowPlaying = writable(null);
export const speakingText = writable('');
export const volumeLevel = writable(50);
export const musicQueue = writable([]);
export const musicSearchResults = writable([]);
export const musicPlaylists = writable([]);
export const spotifyStatus = writable('loading');
export const spotifyReauthUrl = writable(null);
export const spotifyAuthQr = writable(null);
export const youtubeError = writable('');
export const camerasData = writable([]);
export const fullscreenCam = writable(null);
export const devialetData = writable(null);
export const domotiqueData = writable(null);
export const showSettings = writable(false);
export const audioSinks = writable({ default: '', sinks: [] });

let ws = null;

export function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    wsConnected.set(true);
    console.log('[WS] Connecte');
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    switch (msg.type) {
      case 'state':
        assistantState.set(msg.data);
        break;
      case 'page':
        currentPage.set(msg.data);
        break;
      case 'transcript':
        transcript.set(msg.data.text);
        break;
      case 'music':
        musicData.set(msg.data);
        break;
      case 'weather':
        weatherData.set(msg.data);
        break;
      case 'youtube_results':
        youtubeResults.set(msg.data);
        break;
      case 'youtube_playing':
        youtubeNowPlaying.set(msg.data);
        break;
      case 'youtube_stopped':
        youtubeNowPlaying.set(null);
        if (msg.data && msg.data.error) {
          youtubeError.set(msg.data.error);
          setTimeout(() => youtubeError.set(''), 4000);
        }
        break;
      case 'speaking':
        speakingText.set(msg.data);
        break;
      case 'volume':
        volumeLevel.set(msg.data);
        break;
      case 'music_queue':
        musicQueue.set(msg.data);
        break;
      case 'music_search_results':
        musicSearchResults.set(msg.data);
        break;
      case 'music_playlists':
        musicPlaylists.set(msg.data);
        break;
      case 'spotify_status':
        spotifyStatus.set(msg.data);
        if (msg.data === 'ok') {
          spotifyReauthUrl.set(null);
          spotifyAuthQr.set(null);
        }
        break;
      case 'spotify_reauth_url':
        spotifyReauthUrl.set(msg.data);
        break;
      case 'spotify_auth_qr':
        spotifyAuthQr.set(msg.data);
        break;
      case 'audio_sinks':
        audioSinks.set(msg.data);
        break;
      case 'audio_sink_changed':
        if (msg.data.success) {
          audioSinks.update(s => ({
            ...s,
            default: msg.data.default,
            sinks: s.sinks.map(sink => ({ ...sink, is_default: sink.name === msg.data.default })),
          }));
        }
        break;
      case 'cameras_snapshots':
        camerasData.set(msg.data);
        break;
      case 'camera_snapshot':
        camerasData.update(cams => cams.map(c =>
          c.id === msg.data.id ? { ...c, snapshot: msg.data.snapshot } : c
        ));
        fullscreenCam.update(cam =>
          cam && cam.id === msg.data.id ? { ...cam, snapshot: msg.data.snapshot } : cam
        );
        break;
      case 'cameras_list':
        camerasData.set(msg.data);
        break;
      case 'devialet_status':
        devialetData.set(msg.data);
        break;
      case 'domotique_status':
        domotiqueData.set(msg.data);
        break;
    }
  };

  ws.onclose = () => {
    wsConnected.set(false);
    console.log('[WS] Deconnecte, reconnexion dans 3s...');
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => ws.close();
}

export function sendWS(message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}
