import 'dart:io';
import 'dart:async';

/// Manages mpv DRM playback — kills flutter-pi display, plays video, signals when done.
/// In V2 flutter-pi mode, we can't overlay mpv. Instead, backend handles mpv launch
/// and the flutter-pi process is paused/resumed via signals or the backend orchestrates.
///
/// For now: backend launches mpv via subprocess, flutter-pi stays running but mpv
/// takes DRM master. When mpv exits, flutter-pi reclaims display automatically.
///
/// Alternative: flutter-pi app sends command to backend, backend kills flutter-pi,
/// runs mpv, then restarts flutter-pi. This is handled by the systemd service.
class MpvService {
  static Future<bool> isPlaying() async {
    final result = await Process.run('pgrep', ['-x', 'mpv']);
    return result.exitCode == 0;
  }

  static Future<void> stop() async {
    await Process.run('pkill', ['-x', 'mpv']);
  }
}
