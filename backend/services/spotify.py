import asyncio
import logging
import os
import json
from typing import Any

from config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_DEVICE_NAME,
)

logger = logging.getLogger(__name__)

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False
    logger.warning("[SPOTIFY] spotipy non disponible")

SPOTIFY_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative"


class MusicController:
    def __init__(self):
        self._sp = None
        self._device_id = None
        self._broadcast_fn = None  # Set by main.py to broadcast status changes
        self._status_override = None  # Force a status (e.g. after auth error)
        self._device_watcher_task = None  # Keep a ref so the task isn't GC'd
        self._auth_lock = asyncio.Lock()  # Serialise refresh / cache nuke

    def set_broadcast(self, fn):
        """Set the broadcast function for pushing status updates to frontend."""
        self._broadcast_fn = fn

    @property
    def status(self) -> str:
        if self._status_override:
            return self._status_override
        if not HAS_SPOTIPY or not SPOTIFY_CLIENT_ID:
            return "no_credentials"
        if not os.path.exists(self._cache_path()):
            return "auth_required"
        if not self._sp:
            return "not_connected"
        return "ok"

    async def _broadcast_status(self):
        """Push current status to all connected clients."""
        if self._broadcast_fn:
            try:
                await self._broadcast_fn({"type": "spotify_status", "data": self.status})
            except Exception:
                pass

    def _cache_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), '..', '..', '.spotify_cache')

    async def _handle_api_error(self, e: Exception):
        """Detect auth failures — try refresh before nuking cache."""
        err_str = str(e).lower()
        if not any(k in err_str for k in ["invalid_grant", "token revoked", "expired", "401", "access token"]):
            return

        # Serialise concurrent error handlers so we don't race refresh vs cache nuke
        async with self._auth_lock:
            logger.warning("[SPOTIFY] Erreur auth detectee, tentative de refresh...")
            loop = asyncio.get_event_loop()

            # Try to refresh token first (don't delete cache yet!)
            try:
                new_client = await loop.run_in_executor(None, self._try_refresh_token)
                if new_client:
                    self._sp = new_client
                    self._status_override = None
                    logger.info("[SPOTIFY] Token refresh reussi")
                    await self._broadcast_status()
                    return
            except Exception as refresh_err:
                logger.warning("[SPOTIFY] Refresh echoue: %s", refresh_err)

            # Refresh truly failed — token is dead
            logger.warning("[SPOTIFY] Token irrecuperable — passage en auth_required")
            self._sp = None
            self._status_override = "auth_required"
            cache = self._cache_path()
            if os.path.exists(cache):
                os.remove(cache)
                logger.info("[SPOTIFY] Cache OAuth supprime")
            await self._broadcast_status()

    def _try_refresh_token(self):
        """Attempt to refresh the access token using the cached refresh_token."""
        cache = self._cache_path()
        if not os.path.exists(cache):
            return None
        # Read refresh_token from cache
        with open(cache, 'r') as f:
            token_info = json.load(f)
        refresh_token = token_info.get("refresh_token")
        if not refresh_token:
            return None
        auth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPE,
            cache_path=cache,
        )
        auth.refresh_access_token(refresh_token)
        return spotipy.Spotify(auth_manager=auth)

    def get_auth_url(self) -> str | None:
        """Generate Spotify OAuth URL for re-authentication."""
        if not HAS_SPOTIPY or not SPOTIFY_CLIENT_ID:
            return None
        auth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPE,
            cache_path=self._cache_path(),
        )
        return auth.get_authorize_url()

    def get_auth_qr(self) -> str | None:
        """Generate QR code as data:image/png;base64 for the Spotify auth URL."""
        url = self.get_auth_url()
        if not url:
            return None
        try:
            import qrcode
            import io
            import base64
            qr = qrcode.QRCode(version=1, box_size=8, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="white", back_color="#0a0a0f")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:image/png;base64,{b64}"
        except ImportError:
            logger.warning("[SPOTIFY] qrcode non installe — pip install 'qrcode[pil]'")
            return None

    async def token_watchdog(self):
        """Proactively refresh token every 45 min to prevent expiry."""
        while True:
            await asyncio.sleep(45 * 60)
            if not self._sp:
                continue
            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._sp.current_user), timeout=10
                )
                logger.info("[SPOTIFY] Token watchdog: OK")
            except Exception as e:
                logger.warning("[SPOTIFY] Token watchdog: %s", e)
                await self._handle_api_error(e)

    async def handle_callback(self, code: str) -> bool:
        """Handle OAuth callback code, create client, broadcast ok status."""
        if not HAS_SPOTIPY or not SPOTIFY_CLIENT_ID:
            return False
        loop = asyncio.get_event_loop()
        try:
            def _exchange(code):
                auth = SpotifyOAuth(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET,
                    redirect_uri=SPOTIFY_REDIRECT_URI,
                    scope=SPOTIFY_SCOPE,
                    cache_path=self._cache_path(),
                )
                auth.get_access_token(code)
                return spotipy.Spotify(auth_manager=auth)

            self._sp = await loop.run_in_executor(None, _exchange, code)
            self._status_override = None
            logger.info("[SPOTIFY] Re-authentification reussie")
            await self._find_device()
            if not self._device_id:
                self._device_watcher_task = asyncio.create_task(self._device_watcher())
            await self._broadcast_status()
            return True
        except Exception as e:
            logger.error("[SPOTIFY] Erreur callback OAuth: %s", e)
            return False

    async def start(self):
        if not HAS_SPOTIPY or not SPOTIFY_CLIENT_ID:
            logger.info("[SPOTIFY] Mode mock (pas de credentials)")
            await self._broadcast_status()
            return

        if not os.path.exists(self._cache_path()):
            logger.warning("[SPOTIFY] Pas de cache OAuth — authentification requise")
            await self._broadcast_status()
            return

        loop = asyncio.get_event_loop()
        try:
            self._sp = await asyncio.wait_for(
                loop.run_in_executor(None, self._create_client), timeout=10
            )
            logger.info("[SPOTIFY] Client cree")
        except asyncio.TimeoutError:
            logger.warning("[SPOTIFY] Timeout creation client (rate limit?) — mode degrade")
            self._sp = None
            return
        except Exception as e:
            logger.error("[SPOTIFY] Erreur auth: %s", e)
            self._sp = None
            return
        # Quick connection test with timeout
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._sp.current_user), timeout=10
            )
            logger.info("[SPOTIFY] Connecte")
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("[SPOTIFY] Test connexion echoue: %s — client reste actif", e)
        await self._find_device()
        # Si pas de device, lance un watcher qui cherche toutes les 30s
        if not self._device_id:
            self._device_watcher_task = asyncio.create_task(self._device_watcher())

    async def _device_watcher(self):
        """Cherche le device Spotify Connect en boucle apres le boot."""
        for attempt in range(20):  # 20 * 30s = 10 minutes max
            await asyncio.sleep(30)
            await self._find_device()
            if self._device_id:
                logger.info("[SPOTIFY] Device trouve apres %d tentatives", attempt + 1)
                return
        logger.warning("[SPOTIFY] Device jamais trouve apres 10 minutes")

    def _create_client(self):
        auth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPE,
            cache_path=self._cache_path(),
        )
        return spotipy.Spotify(auth_manager=auth)

    async def _find_device(self):
        if not self._sp:
            return
        loop = asyncio.get_event_loop()
        try:
            devices = await loop.run_in_executor(None, self._sp.devices)
            all_devices = devices.get("devices", [])
            for d in all_devices:
                if SPOTIFY_DEVICE_NAME.lower() in d["name"].lower():
                    self._device_id = d["id"]
                    if not d.get("is_active"):
                        try:
                            await loop.run_in_executor(
                                None, lambda: self._sp.transfer_playback(d["id"], force_play=False)
                            )
                            logger.info("[SPOTIFY] Device active: %s", d["name"])
                        except Exception:
                            pass
                    logger.info("[SPOTIFY] Device trouve: %s (%s)", d["name"], d["id"])
                    return
            # Si pas trouve, utiliser le premier device dispo
            if all_devices:
                self._device_id = all_devices[0]["id"]
                logger.info("[SPOTIFY] Device fallback: %s", all_devices[0]["name"])
            else:
                self._device_id = None
                logger.warning("[SPOTIFY] Aucun device Spotify disponible")
        except Exception as e:
            logger.error("[SPOTIFY] Erreur devices: %s", e)

    async def search_and_play(self, query: str) -> dict[str, Any]:
        if not self._sp:
            return {"error": "Spotify non configure", "playing": False}

        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                None, lambda: self._sp.search(q=query, type="track", limit=1, market="FR")
            )
            tracks = results.get("tracks", {}).get("items", [])
            if not tracks:
                return {"error": f"Aucun resultat pour '{query}'", "playing": False}

            track = tracks[0]
            seed_track = track["id"]
            seed_artist = track["artists"][0]["id"] if track["artists"] else None

            await self._find_device()

            # Build radio-style queue via search (artist_top_tracks returns 403)
            rec_uris = []
            artist_name = track["artists"][0]["name"] if track["artists"] else None
            if artist_name:
                # Clean artist name for search (remove quotes/apostrophes that break API)
                safe_name = artist_name.replace("'", " ").replace('"', " ")
                try:
                    # 3 searches with limit=10 each (limit=20 returns 400 on some queries)
                    searches = [
                        f"artist:{safe_name}",
                        safe_name,
                        f"{safe_name} mix",
                    ]
                    for sq in searches:
                        batch = await loop.run_in_executor(
                            None,
                            lambda q=sq: self._sp.search(
                                q=q, type="track", limit=10, market="FR"
                            ),
                        )
                        for t in batch.get("tracks", {}).get("items", []):
                            if t["uri"] != track["uri"] and t["uri"] not in rec_uris:
                                rec_uris.append(t["uri"])
                    logger.info("[SPOTIFY] Radio queue: %d tracks pour %s", len(rec_uris), artist_name)
                except Exception as e:
                    logger.warning("[SPOTIFY] Radio queue build failed: %s", e)

            # Play seed track + radio queue in one call (replaces current queue)
            all_uris = [track["uri"]] + rec_uris[:20]
            await loop.run_in_executor(
                None,
                lambda: self._sp.start_playback(
                    device_id=self._device_id,
                    uris=all_uris,
                ),
            )

            info = {
                "playing": True,
                "title": track["name"],
                "artist": ", ".join(a["name"] for a in track["artists"]),
                "album": track["album"]["name"],
                "cover": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                "uri": track["uri"],
                "queue_size": len(rec_uris),
                "progress_ms": 0,
                "duration_ms": track.get("duration_ms", 0),
            }
            logger.info("[SPOTIFY] Lecture: %s - %s (+%d radio)", info["artist"], info["title"], len(rec_uris))
            return info

        except Exception as e:
            logger.error("[SPOTIFY] Erreur play: %s", e)
            await self._handle_api_error(e)
            return {"error": str(e), "playing": False}

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        if not self._sp:
            return []
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                None, lambda: self._sp.search(q=query, type="track", limit=limit, market="FR")
            )
            tracks = results.get("tracks", {}).get("items", [])
            return [
                {
                    "title": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "album": t["album"]["name"],
                    "cover": t["album"]["images"][-1]["url"] if t["album"]["images"] else None,
                    "uri": t["uri"],
                }
                for t in tracks
            ]
        except Exception as e:
            logger.error("[SPOTIFY] Erreur search: %s", e)
            await self._handle_api_error(e)
            return []

    async def play_tracks(self, items: list) -> dict:
        """Joue une liste de requetes texte (AI mix) — recherche + start_playback.

        Remplace l'ancien acces direct a `music._sp` dans handle_ai_mix.
        """
        if not self._sp:
            return {"playing": False, "error": "Spotify non configure"}
        loop = asyncio.get_event_loop()
        uris: list[str] = []
        first_info = None
        for song in items:
            try:
                results = await loop.run_in_executor(
                    None, lambda s=song: self._sp.search(q=s, type="track", limit=1, market="FR")
                )
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    t = tracks[0]
                    uris.append(t["uri"])
                    if not first_info:
                        first_info = {
                            "playing": True,
                            "title": t["name"],
                            "artist": ", ".join(a["name"] for a in t["artists"]),
                            "album": t["album"]["name"],
                            "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                            "uri": t["uri"],
                            "progress_ms": 0,
                            "duration_ms": t.get("duration_ms", 0),
                        }
            except Exception:
                pass
        if not uris:
            return {"playing": False, "error": "Aucun morceau trouve"}
        try:
            await self._find_device()
            await loop.run_in_executor(
                None, lambda: self._sp.start_playback(device_id=self._device_id, uris=uris)
            )
            logger.info("[SPOTIFY] AI mix: %d morceaux", len(uris))
            return {**(first_info or {"playing": True}), "queue_size": len(uris) - 1}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur play_tracks: %s", e)
            return {"playing": False, "error": str(e)}

    async def play_uri(self, uri: str) -> dict:
        """Play a URI and build a radio queue from the track's artist."""
        if not self._sp:
            return {"playing": False}
        loop = asyncio.get_event_loop()
        try:
            # Get track info to find artist name for radio queue
            track_id = uri.split(":")[-1] if ":" in uri else uri
            track = await loop.run_in_executor(
                None, lambda: self._sp.track(track_id, market="FR")
            )
            if track and track.get("artists"):
                # Use search_and_play with artist name for full radio queue
                artist_name = track["artists"][0]["name"]
                query = f"{track['name']} {artist_name}"
                return await self.search_and_play(query)

            # Fallback: just play the URI
            await self._find_device()
            await loop.run_in_executor(
                None, lambda: self._sp.start_playback(device_id=self._device_id, uris=[uri])
            )
            await asyncio.sleep(0.5)
            return await self.get_current()
        except Exception as e:
            logger.error("[SPOTIFY] Erreur play_uri: %s", e)
            return {"playing": False, "error": str(e)}

    async def get_queue(self) -> list[dict]:
        if not self._sp:
            return []
        loop = asyncio.get_event_loop()
        try:
            queue = await loop.run_in_executor(None, self._sp.queue)
            items = queue.get("queue", [])[:10]
            return [
                {
                    "title": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "cover": t["album"]["images"][-1]["url"] if t["album"]["images"] else None,
                }
                for t in items
            ]
        except Exception as e:
            logger.error("[SPOTIFY] Erreur queue: %s", e)
            return []

    async def pause(self) -> dict:
        if not self._sp:
            return {"paused": False}
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sp.pause_playback(device_id=self._device_id))
            logger.info("[SPOTIFY] Pause")
            return {"paused": True}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur pause: %s", e)
            return {"paused": False, "error": str(e)}

    async def resume(self) -> dict:
        if not self._sp:
            return {"resumed": False}
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sp.start_playback(device_id=self._device_id))
            logger.info("[SPOTIFY] Resume")
            return {"resumed": True}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur resume: %s", e)
            return {"resumed": False, "error": str(e)}

    async def previous_track(self) -> dict:
        if not self._sp:
            return {"skipped": False}
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sp.previous_track(device_id=self._device_id))
            logger.info("[SPOTIFY] Precedent")
            return {"skipped": True}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur previous: %s", e)
            return {"skipped": False, "error": str(e)}

    async def next_track(self) -> dict:
        if not self._sp:
            return {"skipped": False}
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: self._sp.next_track(device_id=self._device_id))
            await asyncio.sleep(0.5)
            current = await self.get_current()
            logger.info("[SPOTIFY] Suivant")
            return {**current, "skipped": True}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur next: %s", e)
            return {"skipped": False, "error": str(e)}

    async def spotify_volume(self, percent: int):
        """Control Spotify Connect volume via API (duck/restore for TTS)."""
        if not self._sp:
            return
        percent = max(0, min(100, percent))
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._sp.volume(percent, device_id=self._device_id),
            )
            logger.info("[SPOTIFY] Volume Spotify: %d%%", percent)
        except Exception as e:
            logger.warning("[SPOTIFY] Erreur volume Spotify: %s", e)

    async def get_spotify_volume(self) -> int:
        """Read current Spotify device volume."""
        if not self._sp:
            return 70
        loop = asyncio.get_event_loop()
        try:
            playback = await loop.run_in_executor(None, self._sp.current_playback)
            if playback and playback.get("device"):
                vol = playback["device"].get("volume_percent", 70)
                logger.info("[SPOTIFY] Volume actuel: %d%%", vol)
                return vol
        except Exception as e:
            logger.warning("[SPOTIFY] Erreur lecture volume: %s", e)
        return 70

    async def set_volume(self, percent: int) -> dict:
        """Controle le volume PipeWire du sink par defaut (Devialet AirPlay)."""
        percent = max(0, min(100, percent))
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: __import__('subprocess').run(
                    ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{percent}%'],
                    check=True,
                ),
            )
            logger.info("[AUDIO] Volume PipeWire: %d%%", percent)
            return {"volume": percent}
        except Exception as e:
            logger.error("[AUDIO] Erreur volume: %s", e)
            return {"error": str(e)}

    async def get_volume(self) -> int:
        """Lit le volume PipeWire actuel."""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: __import__('subprocess').run(
                    ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                    capture_output=True, text=True,
                ),
            )
            # Parse "Volume: front-left: 45875 /  70% / ..."
            for part in result.stdout.split('/'):
                part = part.strip()
                if part.endswith('%'):
                    return int(part[:-1].strip())
        except Exception:
            pass
        return 50

    def _read_librespot_event(self) -> dict | None:
        """Read librespot onevent file for real-time playback state."""
        try:
            import json as _json, time as _time
            with open("/tmp/librespot-now.json") as f:
                data = _json.load(f)
            # Ignore stale events (>30s old)
            ts = data.get("ts", 0)
            if ts and (_time.time() - ts) > 30:
                return None
            return data
        except Exception:
            return None

    async def get_current(self) -> dict:
        if not self._sp:
            return {"playing": False}
        loop = asyncio.get_event_loop()
        try:
            current = await loop.run_in_executor(None, self._sp.current_playback)

            # Check librespot onevent for real-time state (sync file read off the loop)
            libre_state = await loop.run_in_executor(None, self._read_librespot_event)
            libre_playing = libre_state and libre_state.get("event") in ("playing", "changed", "started")
            libre_track_id = libre_state.get("track_id", "") if libre_state else ""

            api_playing = current and current.get("is_playing", False)
            api_track = current.get("item") if current else None

            # If librespot says playing but API disagrees, trust librespot
            if libre_playing and libre_track_id and not api_playing:
                # Fetch track metadata by ID from Spotify API
                try:
                    track = await loop.run_in_executor(None, self._sp.track, libre_track_id)
                    if track:
                        return {
                            "playing": True,
                            "title": track["name"],
                            "artist": ", ".join(a["name"] for a in track["artists"]),
                            "album": track["album"]["name"],
                            "cover": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                            "progress_ms": libre_state.get("position_ms", 0),
                            "duration_ms": track.get("duration_ms", 0),
                        }
                except Exception as e:
                    logger.debug("[SPOTIFY] Librespot track lookup failed: %s", e)

            if not api_track:
                if libre_playing:
                    return {"playing": True, "title": "Lecture en cours...", "artist": "", "album": "", "cover": None, "progress_ms": 0, "duration_ms": 0}
                return {"playing": False}

            return {
                "playing": api_playing or libre_playing,
                "title": api_track["name"],
                "artist": ", ".join(a["name"] for a in api_track["artists"]),
                "album": api_track["album"]["name"],
                "cover": api_track["album"]["images"][0]["url"] if api_track["album"]["images"] else None,
                "progress_ms": current.get("progress_ms", 0),
                "duration_ms": api_track.get("duration_ms", 0),
            }
        except Exception as e:
            logger.error("[SPOTIFY] Erreur current: %s", e)
            await self._handle_api_error(e)
            return {"playing": False}

    async def get_playlists(self) -> list[dict]:
        if not self._sp:
            return []
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                None, lambda: self._sp.current_user_playlists(limit=50)
            )
            return [
                {
                    "name": p["name"],
                    "id": p["id"],
                    "uri": p["uri"],
                    "cover": p["images"][0]["url"] if p.get("images") else None,
                    "tracks": p.get("tracks", {}).get("total", 0) if isinstance(p.get("tracks"), dict) else 0,
                }
                for p in results.get("items", [])
                if p
            ]
        except Exception as e:
            logger.error("[SPOTIFY] Erreur playlists: %s", e)
            await self._handle_api_error(e)
            return []

    async def play_playlist(self, playlist_uri: str) -> dict:
        if not self._sp:
            return {"playing": False}
        loop = asyncio.get_event_loop()
        try:
            await self._find_device()
            await loop.run_in_executor(
                None,
                lambda: self._sp.start_playback(
                    device_id=self._device_id,
                    context_uri=playlist_uri,
                ),
            )
            await loop.run_in_executor(
                None, lambda: self._sp.shuffle(True, device_id=self._device_id)
            )
            await asyncio.sleep(0.5)
            return await self.get_current()
        except Exception as e:
            logger.error("[SPOTIFY] Erreur play_playlist: %s", e)
            return {"playing": False, "error": str(e)}
