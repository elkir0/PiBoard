import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Toujours invoquer le yt-dlp du venv (recent), pas le /usr/bin/yt-dlp systeme
# (souvent une vieille version qui casse sur YouTube). `python -m yt_dlp`.
YTDLP = [sys.executable, "-m", "yt_dlp"]

YT_FORMAT_DEFAULT = "best[height<=480][vcodec^=avc]/bestvideo[height<=480][vcodec^=avc]+bestaudio/best[height<=480]/bestvideo[height<=480]+bestaudio/best"
YT_COOKIES = os.path.join(os.path.dirname(__file__), '..', '..', 'yt-cookies.txt')


def _get_yt_config() -> dict:
    """Read YouTube config from admin config manager (lazy import)."""
    try:
        from admin.config_manager import config
        return config.get_section("youtube")
    except Exception:
        return {}


def _get_raop_sink() -> str:
    """Find the best Devialet RAOP sink from PipeWire.

    Priority: 1) manual devialet_ipv4, 2) auto-discovered IPv4, 3) any Phantom, 4) default sink.
    """
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=5,
        )
        auto_ipv4 = None
        manual_ipv4 = None
        any_devialet = None
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[1]
            if "phantom" in name.lower() and "fe80" not in name and "devialet_ipv4" not in name:
                auto_ipv4 = name
            elif "devialet_ipv4" in name:
                manual_ipv4 = name
            elif "phantom" in name.lower():
                any_devialet = name

        # Prefer auto-discovered IPv4 (manual config may be stale)
        if auto_ipv4:
            return auto_ipv4
        if manual_ipv4:
            return manual_ipv4
        if any_devialet:
            return any_devialet
    except Exception:
        pass

    # Fallback: use default sink
    try:
        result = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=5,
        )
        sink = result.stdout.strip()
        if sink:
            return sink
    except Exception:
        pass
    return "@DEFAULT_SINK@"


class YouTubeController:
    def __init__(self):
        self._use_drm = False  # Track if we killed flutter-pi
        self._vlc_process: asyncio.subprocess.Process | None = None
        self._on_music_pause: Callable | None = None
        self._on_music_resume: Callable | None = None
        self._on_wakeword_pause: Callable | None = None
        self._on_wakeword_resume: Callable | None = None
        self._on_volume_restore: Callable | None = None
        self._queue: list[dict] = []
        self._queue_index: int = 0
        self._on_finish_callback = None
        self._on_next_callback: Callable | None = None
        self._stopped = False
        self._flutter_playing = False  # True pendant une lecture in-Flutter (V3)

    def set_music_callbacks(self, pause_fn, resume_fn):
        """Set callbacks to pause/resume Spotify when YouTube plays/stops."""
        self._on_music_pause = pause_fn
        self._on_music_resume = resume_fn

    def set_volume_callback(self, restore_fn):
        """Set callback to restore Devialet volume after mpv starts."""
        self._on_volume_restore = restore_fn

    def set_wakeword_callbacks(self, pause_fn, resume_fn):
        """Set callbacks to pause/resume wake word during video playback (saves CPU)."""
        self._on_wakeword_pause = pause_fn
        self._on_wakeword_resume = resume_fn

    def set_queue(self, results: list[dict], on_next=None):
        """Set the video queue from search results."""
        self._queue = results
        self._queue_index = 0
        self._on_next_callback = on_next
        self._stopped = False
        logger.info("[YOUTUBE] Queue: %d videos", len(results))

    def get_queue(self) -> list[dict]:
        """Return remaining videos in queue."""
        if self._queue_index + 1 < len(self._queue):
            return self._queue[self._queue_index + 1:]
        return []

    def _base_args(self) -> list[str]:
        """Arguments yt-dlp communs. (Le yt-dlp recent gere les challenges JS de
        YouTube nativement — pas besoin de '--remote-components', qui n'existe pas
        comme option et faisait echouer TOUTES les recherches silencieusement.)"""
        args: list[str] = []
        if os.path.exists(YT_COOKIES):
            args.extend(["--cookies", YT_COOKIES])
        return args

    async def _run_ytdlp(self, args: list[str], timeout: float):
        """Lance yt-dlp et retourne (proc, stdout, stderr). Sur timeout OU
        annulation du pipeline, TUE le sous-process (sinon yt-dlp orphelin
        continue de tourner sur un reseau lent/bloque et s'accumule). Re-leve
        l'exception : les call sites gardent leurs `except TimeoutError`."""
        proc = await asyncio.create_subprocess_exec(
            *YTDLP, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc, stdout, stderr
        except (asyncio.TimeoutError, asyncio.CancelledError):
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError, asyncio.CancelledError):
                pass
            raise

    async def search(self, query: str, limit: int = 0) -> list[dict[str, Any]]:
        cfg = _get_yt_config()
        if limit <= 0:
            limit = cfg.get("search_limit", 5)
        timeout = cfg.get("search_timeout_s", 15)
        try:
            proc, stdout, stderr = await self._run_ytdlp(
                [
                    *self._base_args(),
                    f"ytsearch{limit}:{query}",
                    "--dump-json",
                    "--flat-playlist",
                    "--no-download",
                ],
                timeout=timeout,
            )
            if not stdout.strip() and stderr:
                logger.warning("[YOUTUBE] yt-dlp recherche KO: %s", stderr.decode(errors="ignore")[:300])

            import json
            results = []
            for line in stdout.decode().strip().split("\n"):
                if not line:
                    continue
                data = json.loads(line)
                # Get best thumbnail (last in list = highest res)
                thumbs = data.get("thumbnails", [])
                thumb_url = thumbs[-1]["url"] if thumbs else data.get("thumbnail", "")
                # Use standard YouTube thumbnail URL as fallback
                vid_id = data.get("id", "")
                if not thumb_url and vid_id:
                    thumb_url = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
                results.append({
                    "id": vid_id,
                    "title": data.get("title", ""),
                    "channel": data.get("channel", data.get("uploader", "")),
                    "duration": data.get("duration_string", ""),
                    "thumbnail": thumb_url,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                })

            logger.info("[YOUTUBE] Recherche '%s': %d resultats", query, len(results))
            return results

        except asyncio.TimeoutError:
            logger.error("[YOUTUBE] Timeout recherche")
            return []
        except FileNotFoundError:
            logger.error("[YOUTUBE] yt-dlp non installe")
            return []
        except Exception as e:
            logger.error("[YOUTUBE] Erreur recherche: %s", e)
            return []

    async def play(self, url: str, on_finish=None) -> dict:
        # Stop any existing playback (but don't clear queue)
        await self._stop_vlc()

        self._on_finish_callback = on_finish

        try:
            # Pause wake word to free CPU for video playback
            if self._on_wakeword_pause:
                try:
                    self._on_wakeword_pause()
                except Exception:
                    pass

            # Pause Spotify before playing YouTube (timeout to avoid rate limit block)
            if self._on_music_pause:
                try:
                    await asyncio.wait_for(self._on_music_pause(), timeout=3)
                    logger.info("[YOUTUBE] Spotify mis en pause")
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning("[YOUTUBE] Pause Spotify skip: %s", e)

            return await self._launch_vlc(url)

        except asyncio.TimeoutError:
            logger.error("[YOUTUBE] Timeout yt-dlp")
            return {"playing": False, "error": "Timeout"}
        except FileNotFoundError as e:
            logger.error("[YOUTUBE] Programme manquant: %s", e)
            return {"playing": False, "error": "vlc ou yt-dlp non installe"}
        except Exception as e:
            logger.error("[YOUTUBE] Erreur lecture: %s", e)
            return {"playing": False, "error": str(e)}

    async def resolve_for_flutter(self, url: str) -> dict:
        """Resout l'URL de flux DIRECTE (progressive, un seul flux audio+video)
        pour une lecture DANS l'UI Flutter (plugin gstreamer de flutter-pi, decode
        HW). On met la musique en pause (le son video part sur le Devialet) mais on
        GARDE le wake word actif (le CPU est libre avec le decode materiel, et
        'Terminator stop' reste possible). Retourne {playing, url} ou {error}."""
        self._stopped = False
        # Pause la musique (Deezer/Spotify) — pas de double flux audio.
        if self._on_music_pause:
            try:
                await asyncio.wait_for(self._on_music_pause(), timeout=3)
                logger.info("[YOUTUBE] Musique mise en pause (video)")
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("[YOUTUBE] Pause musique skip: %s", e)
        cfg = _get_yt_config()
        timeout = cfg.get("search_timeout_s", 15)
        # Format PROGRESSIF (a+v dans une seule URL) pour video_player : 22=720p,
        # 18=360p H.264/AAC. Sinon meilleur combine <=720p.
        fmt = "best[height<=720][ext=mp4][acodec!=none][vcodec!=none]/22/18/best[height<=720]/best"
        try:
            proc, stdout, stderr = await self._run_ytdlp(
                ["-f", fmt, "--get-url", *self._base_args(), url],
                timeout=timeout,
            )
            stream = (stdout.decode().strip().split("\n") or [""])[0]
            if not stream:
                logger.warning("[YOUTUBE] resolve KO: %s", stderr.decode(errors="ignore")[:300])
                return {"playing": False, "error": "Flux introuvable"}
            logger.info("[YOUTUBE] Flux resolu pour lecture in-Flutter")
            self._flutter_playing = True
            return {"playing": True, "url": stream}
        except asyncio.TimeoutError:
            return {"playing": False, "error": "Timeout"}
        except Exception as e:
            logger.error("[YOUTUBE] Erreur resolve: %s", e)
            return {"playing": False, "error": str(e)}

    async def stop_flutter(self) -> dict:
        """Arret de la lecture in-Flutter : reprend juste la musique (l'UI a deja
        coupe la video de son cote)."""
        self._stopped = True
        self._flutter_playing = False
        if self._on_music_resume:
            try:
                await asyncio.wait_for(self._on_music_resume(), timeout=3)
                logger.info("[YOUTUBE] Musique reprise")
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("[YOUTUBE] Reprise musique skip: %s", e)
        return {"stopped": True}

    async def _launch_vlc(self, url: str) -> dict:
        """Get stream URLs and launch VLC for a single video."""
        cfg = _get_yt_config()
        yt_format = cfg.get("format", YT_FORMAT_DEFAULT)
        proc, stdout, stderr = await self._run_ytdlp(
            ["-f", yt_format, "--get-url", *self._base_args(), url],
            timeout=30,
        )
        stderr_text = stderr.decode().strip() if stderr else ""
        if stderr_text:
            for line in stderr_text.split("\n"):
                if "WARNING" not in line and line.strip():
                    logger.warning("[YOUTUBE] yt-dlp: %s", line[:200])

        if proc.returncode != 0:
            logger.error("[YOUTUBE] yt-dlp echoue (code %d) pour %s: %s", proc.returncode, url, stderr_text[:300])
            return {"playing": False, "error": f"yt-dlp erreur (code {proc.returncode})"}

        stream_urls = [u for u in stdout.decode().strip().split("\n") if u.startswith("http")]

        if not stream_urls:
            logger.error("[YOUTUBE] yt-dlp n'a retourne aucune URL pour %s", url)
            return {"playing": False, "error": "Impossible d'obtenir l'URL"}

        cache_ms = cfg.get("network_cache_ms", 5000)
        logger.info("[YOUTUBE] %d stream URLs", len(stream_urls))
        env = {**os.environ}

        # Detect if flutter-pi is running (DRM mode) vs Chromium (Wayland mode)
        try:
            _check = subprocess.run(["pgrep", "-x", "flutter-pi"], capture_output=True, timeout=2)
            use_drm = _check.returncode == 0
        except Exception:
            use_drm = False
        self._use_drm = use_drm
        if use_drm:
            # Kill flutter-pi to release DRM master
            await self._kill_flutterpi()

        # mpv: video + audio via PipeWire → AirPlay
        cache_secs = max(10, cache_ms // 1000)
        if use_drm:
            player_args = [
                "mpv",
                "--fullscreen",
                "--ao=pipewire",
                "--vo=drm",
                "--no-terminal",
                "--input-ipc-server=/tmp/mpv-socket",
                "--volume=100",
                f"--cache-secs={cache_secs}",
                f"--demuxer-readahead-secs={cache_secs}",
                "--demuxer-max-bytes=80M",
                "--hwdec=no",
                "--audio-buffer=1",
            ]
        else:
            player_args = [
                "mpv",
                "--fullscreen",
                "--ao=pulse",
                "--vo=gpu",
                "--gpu-context=wayland",
                "--no-terminal",
                f"--cache-secs={cache_secs}",
                f"--demuxer-readahead-secs={cache_secs}",
                "--demuxer-max-bytes=80M",
                "--hwdec=no",
                "--audio-buffer=1",
            ]
        if len(stream_urls) >= 2 and stream_urls[1]:
            player_args.append(f"--audio-file={stream_urls[1]}")
        player_args.append(stream_urls[0])

        logger.info("[YOUTUBE] Lancement mpv: %d args, video=%s", len(player_args), url)
        self._vlc_process = await asyncio.create_subprocess_exec(
            *player_args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Wait briefly to check player didn't die immediately
        await asyncio.sleep(2)
        if self._vlc_process.returncode is not None:
            exit_code = self._vlc_process.returncode
            player_err = ""
            try:
                stderr_data = await asyncio.wait_for(self._vlc_process.stderr.read(2000), timeout=1)
                player_err = stderr_data.decode().strip()[:300]
            except Exception:
                pass
            logger.error("[YOUTUBE] mpv mort immediatement (code %d): %s", exit_code, player_err)
            self._vlc_process = None
            return {"playing": False, "error": f"mpv echoue (code {exit_code})"}

        logger.info("[YOUTUBE] mpv demarre OK (PID %d)", self._vlc_process.pid)

        # Start touch control listener (pause/stop/seek via screen zones)
        asyncio.create_task(self._touch_control_listener())

        # Restore Devialet volume (mpv/PipeWire can reset it)
        if self._on_volume_restore:
            try:
                await self._on_volume_restore()
            except Exception:
                pass

        # Watch for natural VLC exit → play next in queue
        asyncio.create_task(self._watch_vlc())

        return {"playing": True, "url": url}

    async def _watch_vlc(self):
        try:
            if self._vlc_process:
                start_time = asyncio.get_event_loop().time()
                await self._vlc_process.wait()
                duration = asyncio.get_event_loop().time() - start_time
                exit_code = self._vlc_process.returncode
                self._vlc_process = None

                # If VLC died very fast, it's an error not a natural end
                if duration < 5:
                    logger.warning("[YOUTUBE] mpv termine trop vite (%.1fs, code %s) — skip", duration, exit_code)
                    # Don't chain next, just clean up — restart flutter-pi
                    await self._restart_flutterpi()
                    if self._on_wakeword_resume:
                        try:
                            self._on_wakeword_resume()
                        except Exception:
                            pass
                    if self._on_music_resume:
                        try:
                            await asyncio.wait_for(self._on_music_resume(), timeout=3)
                        except Exception:
                            pass
                    if self._on_finish_callback:
                        await self._on_finish_callback()
                    return

                logger.info("[YOUTUBE] mpv termine naturellement (%.0fs)", duration)

                # If stopped manually, don't play next
                if self._stopped:
                    return

                # Try to play next in queue
                if self._queue_index + 1 < len(self._queue):
                    self._queue_index += 1
                    next_video = self._queue[self._queue_index]
                    logger.info("[YOUTUBE] Enchainement: %s (%d/%d)",
                                next_video["title"][:50], self._queue_index + 1, len(self._queue))

                    # Notify frontend of new video
                    if self._on_next_callback:
                        try:
                            await self._on_next_callback(next_video)
                        except Exception:
                            pass

                    try:
                        await self._launch_vlc(next_video["url"])
                        return  # _watch_vlc will be called again by _launch_vlc
                    except Exception as e:
                        logger.error("[YOUTUBE] Erreur enchainement: %s", e)

                # Queue exhausted or error — restart flutter-pi + resume wake word + Spotify
                logger.info("[YOUTUBE] Queue terminee")
                await self._restart_flutterpi()
                if self._on_wakeword_resume:
                    try:
                        self._on_wakeword_resume()
                    except Exception:
                        pass
                if self._on_music_resume:
                    try:
                        await asyncio.wait_for(self._on_music_resume(), timeout=3)
                        logger.info("[YOUTUBE] Spotify repris")
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning("[YOUTUBE] Reprise Spotify skip: %s", e)
                if self._on_finish_callback:
                    await self._on_finish_callback()
        except Exception as e:
            logger.error("[YOUTUBE] Erreur watcher mpv: %s", e)

    async def _kill_flutterpi(self):
        """Kill flutter-pi to release DRM master for mpv."""
        try:
            proc = await asyncio.create_subprocess_exec("pkill", "-9", "flutter-pi")
            await proc.wait()
            await asyncio.sleep(1)  # Let DRM release
            logger.info("[YOUTUBE] flutter-pi killed (DRM released)")
        except Exception as e:
            logger.warning("[YOUTUBE] flutter-pi kill: %s", e)

    async def _restart_flutterpi(self):
        """Restart flutter-pi after mpv playback ends."""
        if not self._use_drm:
            return
        self._use_drm = False
        try:
            from config import FLUTTER_RESTART_CMD
            cmd = (FLUTTER_RESTART_CMD or "").strip()
            if not cmd:
                logger.info("[YOUTUBE] FLUTTER_RESTART_CMD vide -> pas de relance flutter-pi")
                return
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", f"nohup {cmd} > /tmp/piboard-flutter-restart.log 2>&1 &",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            logger.info("[YOUTUBE] relance flutter-pi planifiée (%s)", cmd)
        except Exception as e:
            logger.error("[YOUTUBE] flutter-pi restart failed: %s", e)

    async def _stop_vlc(self):
        """Stop player without resuming Spotify or clearing queue."""
        if self._vlc_process and self._vlc_process.returncode is None:
            try:
                self._vlc_process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self._vlc_process.wait(), timeout=3)
                logger.info("[YOUTUBE] mpv arrete")
            except (asyncio.TimeoutError, ProcessLookupError):
                self._vlc_process.kill()
            self._vlc_process = None

    async def stop(self) -> dict:
        """Full stop: kill VLC, clear queue, resume wake word + Spotify."""
        self._stopped = True
        self._queue = []
        self._queue_index = 0
        await self._stop_vlc()
        # Restart flutter-pi if in DRM mode
        await self._restart_flutterpi()
        # Resume wake word (frees CPU constraint)
        if self._on_wakeword_resume:
            try:
                self._on_wakeword_resume()
            except Exception:
                pass
        # Resume Spotify after stop (timeout to avoid rate limit block)
        if self._on_music_resume:
            try:
                await asyncio.wait_for(self._on_music_resume(), timeout=3)
                logger.info("[YOUTUBE] Spotify repris")
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("[YOUTUBE] Reprise Spotify skip: %s", e)
        return {"stopped": True}

    async def _touch_control_listener(self):
        """Listen for touchscreen taps to control mpv.

        Zones (landscape 800x480):
          Left 1/3  = seek -10s
          Center    = pause/play
          Right 1/3 = seek +10s
          Long press (>1s) or double-tap (<400ms) = stop video
        """
        try:
            import glob, struct, time as _time

            # Find touchscreen device
            devs = glob.glob("/dev/input/event*")
            touch_dev = None
            for d in devs:
                try:
                    name_path = f"/sys/class/input/{d.split('/')[-1]}/device/name"
                    with open(name_path) as f:
                        name = f.read().strip().lower()
                        if "touch" in name or "ft5" in name or "edt" in name:
                            touch_dev = d
                            break
                except Exception:
                    continue
            if not touch_dev:
                logger.warning("[YOUTUBE] No touchscreen found")
                return

            logger.info("[YOUTUBE] Touch controls on %s (left=rew, center=pause, right=fwd, long=stop)", touch_dev)
            await asyncio.sleep(2)  # Grace period

            loop = asyncio.get_event_loop()
            screen_w = 800  # DSI display width

            def _read_events():
                """Blocking touch event reader — returns (action, x) tuples."""
                results = []
                touch_x = 0
                touch_down_time = 0
                last_tap_time = 0

                with open(touch_dev, "rb") as f:
                    while self.is_playing:
                        data = f.read(24)
                        if len(data) < 24:
                            break
                        _, _, ev_type, ev_code, ev_value = struct.unpack("llHHi", data)

                        # EV_ABS=3, ABS_X=0 (or ABS_MT_POSITION_X=53)
                        if ev_type == 3 and ev_code in (0, 53):
                            touch_x = ev_value

                        # EV_KEY=1, BTN_TOUCH=330
                        if ev_type == 1 and ev_code == 330:
                            now = _time.monotonic()
                            if ev_value == 1:  # Touch down
                                touch_down_time = now
                            elif ev_value == 0:  # Touch up
                                hold_duration = now - touch_down_time

                                if hold_duration > 1.0:
                                    return ("stop", touch_x)

                                # Double tap detection
                                if now - last_tap_time < 0.4:
                                    return ("stop", touch_x)

                                last_tap_time = now

                                # Zone detection
                                third = screen_w / 3
                                if touch_x < third:
                                    return ("rewind", touch_x)
                                elif touch_x > third * 2:
                                    return ("forward", touch_x)
                                else:
                                    return ("pause", touch_x)

                return None

            while self.is_playing:
                result = await loop.run_in_executor(None, _read_events)
                if not result or not self.is_playing:
                    break

                action, x = result
                logger.info("[YOUTUBE] Touch: %s (x=%d)", action, x)

                if action == "stop":
                    await self.stop()
                    break
                elif action == "pause":
                    await self._mpv_ipc(["cycle", "pause"])
                elif action == "rewind":
                    await self._mpv_ipc(["seek", "-10"])
                elif action == "forward":
                    await self._mpv_ipc(["seek", "10"])

        except Exception as e:
            logger.warning("[YOUTUBE] Touch listener: %s", e)

    async def _mpv_ipc(self, command: list) -> bool:
        """Send a command to mpv via IPC socket."""
        import json as _json
        try:
            reader, writer = await asyncio.open_unix_connection("/tmp/mpv-socket")
            msg = _json.dumps({"command": command}) + "\n"
            writer.write(msg.encode())
            await writer.drain()
            writer.close()
            return True
        except Exception:
            return False

    async def pause(self) -> bool:
        """Toggle pause on mpv."""
        return await self._mpv_ipc(["cycle", "pause"])

    async def seek(self, seconds: int) -> bool:
        """Seek forward/backward."""
        return await self._mpv_ipc(["seek", str(seconds)])

    @property
    def is_playing(self) -> bool:
        return self._flutter_playing or (
            self._vlc_process is not None and self._vlc_process.returncode is None
        )
