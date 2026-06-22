import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../components/virtual_keyboard.dart';
import '../i18n.dart';

/// MUSIQUE — flagship landscape split-pane page (1788px usable @ 1200p).
/// LEFT ~42% = NOW PLAYING (album art, transport, progress, volume).
/// RIGHT ~58% = tabbed panel [Recherche | Playlists | File].
class MusicPage extends StatefulWidget {
  const MusicPage({super.key});

  @override
  State<MusicPage> createState() => _MusicPageState();
}

class _MusicPageState extends State<MusicPage> {
  // Right-panel tab: 0 = Recherche, 1 = Playlists, 2 = File
  int _tab = 0;

  final _searchController = TextEditingController();
  Timer? _searchDebounce;
  Timer? _volumeDebounce;

  List<Map<String, dynamic>> _searchResults = [];
  List<Map<String, dynamic>> _playlists = [];
  bool _playlistsLoaded = false;
  late StreamSubscription _wsSub;

  // Local drag state for the progress bar (so the thumb tracks the finger).
  double? _seekDrag; // 0..1 while dragging, null otherwise

  @override
  void initState() {
    super.initState();
    final state = context.read<AppState>();
    _wsSub = state.messages.listen((msg) {
      final type = msg['type'];
      final data = msg['data'];
      if (type == 'music_search_results' && data is List) {
        setState(() => _searchResults = List<Map<String, dynamic>>.from(data));
      } else if (type == 'music_playlists' && data is List) {
        setState(() {
          _playlists = List<Map<String, dynamic>>.from(data);
          _playlistsLoaded = true;
        });
      }
    });
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _volumeDebounce?.cancel();
    _searchController.dispose();
    _wsSub.cancel();
    super.dispose();
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  void _selectTab(AppState state, int tab) {
    if (_tab == tab) return;
    setState(() => _tab = tab);
    if (tab == 1 && !_playlistsLoaded) {
      state.send({'type': 'music_playlists'});
    }
    if (tab == 2) {
      state.send({'type': 'music_queue'});
    }
    // Recherche owns the keyboard; leaving it closes the keyboard.
    if (tab != 0) _setKeyboard(state, false);
  }

  void _setKeyboard(AppState state, bool visible) {
    if (state.keyboardVisible == visible) return;
    state.keyboardVisible = visible;
    state.notify();
  }

  void _runSearch(AppState state) {
    final q = _searchController.text.trim();
    if (q.length >= 2) state.send({'type': 'music_search', 'data': q});
  }

  void _searchDebounced(AppState state) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 400), () => _runSearch(state));
  }

  /// Volume slider → Devialet, debounced ~150ms. Prompt-spec message.
  void _onVolume(AppState state, int v) {
    state.volumeLevel = v;
    state.notify();
    _volumeDebounce?.cancel();
    _volumeDebounce = Timer(const Duration(milliseconds: 150), () {
      state.send({'type': 'music_volume', 'data': v});
    });
  }

  void _togglePlayPause(AppState state, bool playing) {
    // Optimistic UI flip, then resume/pause helpers.
    state.musicData = {...state.musicData, 'playing': !playing};
    state.notify();
    if (playing) {
      state.musicPause();
    } else {
      state.musicResume();
    }
  }

  String _fmt(int ms) {
    if (ms < 0) ms = 0;
    final totalSec = ms ~/ 1000;
    final m = totalSec ~/ 60;
    final s = totalSec % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      // Spotify auth overlay ONLY when the Spotify provider demands re-auth.
      if (state.spotifyStatus == 'auth_required') return _buildAuth(state);

      return Padding(
        padding: const EdgeInsets.all(PBTheme.pagePad),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // LEFT ~42% — NOW PLAYING
            Expanded(flex: 42, child: _buildNowPlaying(state)),
            const SizedBox(width: PBTheme.pagePad),
            // RIGHT ~58% — tabbed panel
            Expanded(flex: 58, child: _buildRightPanel(state)),
          ],
        ),
      );
    });
  }

  // ════════════════════════════ LEFT: NOW PLAYING ════════════════════════════
  Widget _buildNowPlaying(AppState state) {
    final m = state.musicData;
    final playing = m['playing'] == true;
    final hasTrack = ((m['title'] as String?) ?? '').isNotEmpty;
    final title = hasTrack ? ((m['title'] as String?) ?? '--') : t('music.waiting');
    final artist = hasTrack ? ((m['artist'] as String?) ?? '') : '';
    final album = hasTrack ? ((m['album'] as String?) ?? '') : '';
    final imageUrl =
        hasTrack ? (((m['cover'] as String?) ?? (m['image'] as String?)) ?? '') : '';

    final progressMs = (m['progress_ms'] as num?)?.toInt() ?? 0;
    final durationMs = (m['duration_ms'] as num?)?.toInt() ?? 0;
    final hasDuration = durationMs > 0;
    final liveFrac =
        hasDuration ? (progressMs / durationMs).clamp(0.0, 1.0) : 0.0;
    final frac = _seekDrag ?? liveFrac;
    final remainingMs = hasDuration ? (durationMs - progressMs) : 0;

    return Container(
      decoration: PBTheme.frosted(active: playing),
      padding: const EdgeInsets.all(PBTheme.pagePad),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(t('music.now_playing'), style: PBTheme.label),
          const SizedBox(height: 24),

          // Album art — fills available width up to ~360px, square, centered.
          Expanded(
            child: Center(
              child: LayoutBuilder(builder: (_, c) {
                final side = c.maxWidth.clamp(0, 360).toDouble();
                return _albumArt(imageUrl, side, playing);
              }),
            ),
          ),
          const SizedBox(height: 28),

          // Title / artist / album
          Text(
            title,
            style: PBTheme.h1,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 6),
          if (artist.isNotEmpty)
            Text(artist, style: PBTheme.h2.copyWith(color: PBTheme.textSecondary),
                maxLines: 1, overflow: TextOverflow.ellipsis),
          if (!hasTrack)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                t('music.voice_hint'),
                style: PBTheme.bodyMuted,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          if (album.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(album, style: PBTheme.caption,
                  maxLines: 1, overflow: TextOverflow.ellipsis),
            ),

          const SizedBox(height: 20),

          // Equalizer (animates ONLY when playing)
          SizedBox(height: 36, child: _Equalizer(active: playing)),
          const SizedBox(height: 16),

          // Progress bar (draggable seek)
          _progressBar(state, frac, progressMs, remainingMs, hasDuration, durationMs),
          const SizedBox(height: 20),

          // Transport
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _transportBtn(Icons.skip_previous_rounded, () => state.musicPrev(), 40),
              const SizedBox(width: 24),
              _transportBtn(
                playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                () => _togglePlayPause(state, playing),
                72,
                primary: true,
              ),
              const SizedBox(width: 24),
              _transportBtn(Icons.skip_next_rounded, () => state.musicNext(), 40),
              const SizedBox(width: 24),
              _transportBtn(Icons.stop_rounded, () => state.musicStop(), 38,
                  iconColor: PBTheme.red),
            ],
          ),
          const SizedBox(height: 22),

          // Volume → Devialet
          Row(
            children: [
              Icon(Icons.volume_down_rounded, size: 30, color: PBTheme.textSecondary),
              Expanded(
                child: SliderTheme(
                  data: SliderThemeData(
                    trackHeight: 8,
                    thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 13),
                    overlayShape: const RoundSliderOverlayShape(overlayRadius: 26),
                    activeTrackColor: PBTheme.accent,
                    inactiveTrackColor: Colors.white.withAlpha(28),
                    thumbColor: PBTheme.accentLight,
                    overlayColor: PBTheme.accent.withAlpha(40),
                  ),
                  child: Slider(
                    value: state.volumeLevel.toDouble().clamp(0, 100),
                    min: 0,
                    max: 100,
                    onChanged: (v) => _onVolume(state, v.round()),
                  ),
                ),
              ),
              Icon(Icons.volume_up_rounded, size: 30, color: PBTheme.textSecondary),
              const SizedBox(width: 12),
              SizedBox(
                width: 56,
                child: Text('${state.volumeLevel}',
                    style: PBTheme.h3, textAlign: TextAlign.center),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Center(
            child: Text(t('music.volume_devialet'),
                style: PBTheme.caption.copyWith(color: PBTheme.textMuted)),
          ),
        ],
      ),
    );
  }

  Widget _albumArt(String url, double side, bool playing) {
    return Stack(
      alignment: Alignment.center,
      children: [
        if (playing)
          Container(
            width: side * 0.92,
            height: side * 0.92,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(24),
              boxShadow: [
                BoxShadow(
                  color: PBTheme.accent.withAlpha(70),
                  blurRadius: 60,
                  spreadRadius: 6,
                ),
              ],
            ),
          ),
        Container(
          width: side,
          height: side,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            color: PBTheme.surface,
            border: Border.all(color: Colors.white.withAlpha(22), width: 1),
          ),
          child: url.isNotEmpty
              ? Image.network(url,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => _coverPlaceholder())
              : _coverPlaceholder(),
        ),
      ],
    );
  }

  Widget _progressBar(AppState state, double frac, int progressMs,
      int remainingMs, bool hasDuration, int durationMs) {
    return Column(
      children: [
        SliderTheme(
          data: SliderThemeData(
            trackHeight: 8,
            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 12),
            overlayShape: const RoundSliderOverlayShape(overlayRadius: 24),
            activeTrackColor: PBTheme.accent,
            inactiveTrackColor: Colors.white.withAlpha(24),
            thumbColor: PBTheme.accentLight,
            overlayColor: PBTheme.accent.withAlpha(40),
          ),
          child: Slider(
            value: frac.clamp(0.0, 1.0),
            min: 0,
            max: 1,
            onChanged: hasDuration
                ? (v) => setState(() => _seekDrag = v)
                : null,
            onChangeEnd: hasDuration
                ? (v) {
                    final ms = (v * durationMs).round();
                    state.send({'type': 'music_seek', 'data': ms});
                    setState(() => _seekDrag = null);
                  }
                : null,
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(_fmt(progressMs), style: PBTheme.caption),
            Text(hasDuration ? '-${_fmt(remainingMs)}' : '--:--',
                style: PBTheme.caption),
          ],
        ),
      ],
    );
  }

  Widget _transportBtn(IconData icon, VoidCallback onTap, double iconSize,
      {bool primary = false, Color? iconColor}) {
    final box = (iconSize + 32).clamp(PBTheme.touchMin, 120).toDouble();
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: box,
        height: box,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: primary
              ? LinearGradient(
                  colors: [PBTheme.accent.withAlpha(90), PBTheme.accentDim.withAlpha(70)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                )
              : null,
          color: primary ? null : Colors.white.withAlpha(14),
          border: Border.all(
            color: primary ? PBTheme.accent.withAlpha(140) : Colors.white.withAlpha(28),
            width: 1,
          ),
        ),
        child: Icon(icon,
            size: iconSize, color: iconColor ?? (primary ? Colors.white : PBTheme.textPrimary)),
      ),
    );
  }

  // ════════════════════════════ RIGHT: TABBED PANEL ══════════════════════════
  Widget _buildRightPanel(AppState state) {
    return Container(
      decoration: PBTheme.frosted(),
      padding: const EdgeInsets.all(PBTheme.pagePad),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Tab bar
          Row(
            children: [
              _tabBtn(state, 0, t('music.tab_search'), Icons.search_rounded),
              const SizedBox(width: 12),
              _tabBtn(state, 1, t('music.tab_playlists'), Icons.queue_music_rounded),
              const SizedBox(width: 12),
              _tabBtn(state, 2, t('music.tab_queue'), Icons.playlist_play_rounded),
            ],
          ),
          const SizedBox(height: 24),
          Expanded(
            child: switch (_tab) {
              0 => _buildSearchTab(state),
              1 => _buildPlaylistsTab(state),
              _ => _buildQueueTab(state),
            },
          ),
        ],
      ),
    );
  }

  Widget _tabBtn(AppState state, int tab, String label, IconData icon) {
    final active = _tab == tab;
    return Expanded(
      child: GestureDetector(
        onTap: () => _selectTab(state, tab),
        child: Container(
          height: PBTheme.touchMin,
          decoration: PBTheme.glass(active: active, r: 16),
          alignment: Alignment.center,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon,
                  size: 26,
                  color: active ? PBTheme.accent : PBTheme.textSecondary),
              const SizedBox(width: 10),
              Flexible(
                child: Text(
                  label,
                  style: PBTheme.h3.copyWith(
                      color: active ? PBTheme.textPrimary : PBTheme.textSecondary),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── Tab: Recherche ──────────────────────────────────────────────────────
  Widget _buildSearchTab(AppState state) {
    final showKeyboard = state.keyboardVisible;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Search field (tap to open keyboard)
        GestureDetector(
          onTap: () => _setKeyboard(state, true),
          child: Container(
            height: PBTheme.touchMin,
            padding: const EdgeInsets.symmetric(horizontal: 20),
            decoration: PBTheme.glass(active: showKeyboard, r: 16),
            child: Row(
              children: [
                Icon(Icons.search_rounded, size: 28, color: PBTheme.textSecondary),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    _searchController.text.isEmpty
                        ? t('music.search_hint')
                        : _searchController.text,
                    style: _searchController.text.isEmpty
                        ? PBTheme.body.copyWith(color: PBTheme.textMuted)
                        : PBTheme.body,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (_searchController.text.isNotEmpty)
                  GestureDetector(
                    onTap: () {
                      _searchController.clear();
                      setState(() => _searchResults = []);
                    },
                    child: Icon(Icons.close_rounded,
                        size: 26, color: PBTheme.textSecondary),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
        Expanded(
          child: _searchResults.isEmpty
              ? _emptyHint(Icons.search_rounded, t('music.search_empty'))
              : ListView.separated(
                  itemCount: _searchResults.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, i) {
                    final r = _searchResults[i];
                    return _resultRow(
                      cover: (r['cover'] as String?) ?? (r['image'] as String?) ?? '',
                      title: (r['title'] as String?) ?? '',
                      subtitle: (r['artist'] as String?) ?? '',
                      onTap: () {
                        state.send({'type': 'music_play_uri', 'data': r['uri']});
                        _setKeyboard(state, false);
                      },
                      trailing: Icon(Icons.play_circle_fill_rounded,
                          color: PBTheme.accent.withAlpha(190), size: 36),
                    );
                  },
                ),
        ),
        if (showKeyboard) ...[
          const SizedBox(height: 12),
          VirtualKeyboard(
            controller: _searchController,
            onSubmit: () => _runSearch(state),
            onClose: () => _setKeyboard(state, false),
            onChanged: () {
              setState(() {});
              _searchDebounced(state);
            },
          ),
        ],
      ],
    );
  }

  // ── Tab: Playlists ──────────────────────────────────────────────────────
  void _refreshPlaylists(AppState state) {
    setState(() => _playlistsLoaded = false);
    state.send({'type': 'music_playlists'});
  }

  Widget _buildPlaylistsTab(AppState state) {
    if (!_playlistsLoaded) {
      return _emptyHint(Icons.queue_music_rounded, t('music.playlists_loading'));
    }
    if (_playlists.isEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(t('music.tab_playlists'), style: PBTheme.h3),
              const Spacer(),
              GestureDetector(
                onTap: () => _refreshPlaylists(state),
                child: Container(
                  width: PBTheme.touchMin,
                  height: PBTheme.touchMin,
                  decoration: PBTheme.glass(r: 16),
                  child: Icon(Icons.refresh_rounded,
                      color: PBTheme.textSecondary, size: 28),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _emptyHint(Icons.queue_music_rounded, t('music.playlists_empty')),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text(t('music.tab_playlists'), style: PBTheme.h3),
            const Spacer(),
            GestureDetector(
              onTap: () => _refreshPlaylists(state),
              child: Container(
                width: PBTheme.touchMin,
                height: PBTheme.touchMin,
                decoration: PBTheme.glass(r: 16),
                child: Icon(Icons.refresh_rounded,
                    color: PBTheme.textSecondary, size: 28),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: ListView.separated(
            itemCount: _playlists.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (_, i) {
              final pl = _playlists[i];
              final count = pl['tracks'] ?? pl['count'] ?? '?';
              return _resultRow(
                cover: (pl['cover'] as String?) ?? (pl['image'] as String?) ?? '',
                title: (pl['name'] as String?) ?? (pl['title'] as String?) ?? '',
                subtitle: '$count ${t('music.tracks_suffix')}',
                onTap: () {
                  state.send({'type': 'music_play_playlist', 'data': pl['uri']});
                  _selectTab(state, 2);
                },
                trailing: Icon(Icons.play_circle_fill_rounded,
                    color: PBTheme.accent.withAlpha(190), size: 36),
              );
            },
          ),
        ),
      ],
    );
  }

  // ── Tab: File (queue) ───────────────────────────────────────────────────
  Widget _buildQueueTab(AppState state) {
    final q = state.musicQueue;
    if (q.isEmpty) {
      return _emptyHint(Icons.playlist_play_rounded, t('music.queue_empty'));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text(t('music.queue_up_next'), style: PBTheme.h3),
            const Spacer(),
            GestureDetector(
              onTap: () => state.send({'type': 'music_queue'}),
              child: Container(
                width: PBTheme.touchMin,
                height: PBTheme.touchMin,
                decoration: PBTheme.glass(r: 16),
                child: Icon(Icons.refresh_rounded,
                    color: PBTheme.textSecondary, size: 28),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: ListView.separated(
            itemCount: q.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (_, i) {
              final t = q[i];
              return _resultRow(
                cover: (t['cover'] as String?) ?? (t['image'] as String?) ?? '',
                title: (t['title'] as String?) ?? '',
                subtitle: (t['artist'] as String?) ?? '',
                leadingIndex: i + 1,
                onTap: null,
              );
            },
          ),
        ),
      ],
    );
  }

  // ── Shared list row ─────────────────────────────────────────────────────
  Widget _resultRow({
    required String cover,
    required String title,
    required String subtitle,
    VoidCallback? onTap,
    Widget? trailing,
    int? leadingIndex,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        constraints: const BoxConstraints(minHeight: PBTheme.touchMin),
        padding: const EdgeInsets.all(12),
        decoration: PBTheme.glass(opacity: 0.04, r: 16),
        child: Row(
          children: [
            if (leadingIndex != null)
              SizedBox(
                width: 36,
                child: Text('$leadingIndex',
                    style: PBTheme.h3.copyWith(color: PBTheme.textMuted),
                    textAlign: TextAlign.center),
              ),
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: cover.isNotEmpty
                  ? Image.network(cover,
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => _miniCover())
                  : _miniCover(),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(title,
                      style: PBTheme.body,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(subtitle,
                        style: PBTheme.caption,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ],
                ],
              ),
            ),
            if (trailing != null) ...[
              const SizedBox(width: 12),
              trailing,
            ],
          ],
        ),
      ),
    );
  }

  Widget _emptyHint(IconData icon, String text) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 64, color: PBTheme.textMuted.withAlpha(120)),
          const SizedBox(height: 16),
          Text(text, style: PBTheme.bodyMuted, textAlign: TextAlign.center),
        ],
      ),
    );
  }

  // ════════════════════════════ SPOTIFY AUTH ═════════════════════════════════
  Widget _buildAuth(AppState state) {
    // pi-board.local (ancienne prod) ne résout plus -> hostname réel du backend.
    final host = state.systemInfo?['hostname'] != null
        ? '${state.systemInfo!['hostname']}.local'
        : 'PiBoardV2.local';
    final scanUrl = 'http://$host:8000/api/spotify/reauth';
    return Padding(
      padding: const EdgeInsets.all(PBTheme.pagePad),
      child: Center(
        child: PBTheme.glassBox(
          active: true,
          padding: const EdgeInsets.all(40),
          borderRadius: 28,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.music_note_rounded, size: 40, color: PBTheme.accent),
                  const SizedBox(width: 14),
                  Text(t('music.spotify_disconnected'), style: PBTheme.h1),
                ],
              ),
              const SizedBox(height: 12),
              Text(t('music.spotify_scan_qr'), style: PBTheme.body),
              const SizedBox(height: 28),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: QrImageView(
                  data: scanUrl,
                  version: QrVersions.auto,
                  size: 240,
                  backgroundColor: Colors.white,
                  eyeStyle: const QrEyeStyle(
                      eyeShape: QrEyeShape.square, color: Colors.black),
                  dataModuleStyle: const QrDataModuleStyle(
                      dataModuleShape: QrDataModuleShape.square,
                      color: Colors.black),
                ),
              ),
              const SizedBox(height: 18),
              Text('$host:8000',
                  style: PBTheme.caption.copyWith(color: PBTheme.textMuted)),
              const SizedBox(height: 24),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  GestureDetector(
                    onTap: () => state.send({'type': 'spotify_auth_browser'}),
                    child: Container(
                      height: PBTheme.touchMin,
                      padding: const EdgeInsets.symmetric(horizontal: 28),
                      alignment: Alignment.center,
                      decoration: PBTheme.accentButton,
                      child: Text(t('music.spotify_connect'),
                          style: TextStyle(
                              fontSize: 20,
                              color: PBTheme.accent,
                              fontWeight: FontWeight.w700)),
                    ),
                  ),
                  const SizedBox(width: 16),
                  GestureDetector(
                    onTap: () => state.send({'type': 'spotify_retry'}),
                    child: Container(
                      height: PBTheme.touchMin,
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      alignment: Alignment.center,
                      decoration: PBTheme.glass(r: 16),
                      child: Text(t('music.spotify_verify'),
                          style: PBTheme.body
                              .copyWith(color: PBTheme.textSecondary)),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── Cover placeholders ──────────────────────────────────────────────────
  Widget _coverPlaceholder() => Container(
        color: PBTheme.surface,
        alignment: Alignment.center,
        child: Icon(Icons.music_note_rounded, size: 96, color: PBTheme.textMuted),
      );

  Widget _miniCover([double s = 56]) => Container(
        width: s,
        height: s,
        color: PBTheme.surface,
        alignment: Alignment.center,
        child: Icon(Icons.music_note_rounded, size: s * 0.5, color: PBTheme.textMuted),
      );
}

/// 8-bar equalizer. Animates (transform/opacity) ONLY while [active].
/// When idle it freezes to a static low baseline — no per-frame work.
class _Equalizer extends StatefulWidget {
  final bool active;
  const _Equalizer({required this.active});

  @override
  State<_Equalizer> createState() => _EqualizerState();
}

class _EqualizerState extends State<_Equalizer>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  static const _bars = 8;
  // Per-bar phase + speed for an organic look.
  final List<double> _phase = [0.0, 0.6, 1.2, 0.3, 0.9, 1.5, 0.45, 1.1];
  final List<double> _speed = [1.0, 1.4, 0.8, 1.7, 1.1, 0.9, 1.5, 1.2];

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    if (widget.active) _c.repeat();
  }

  @override
  void didUpdateWidget(covariant _Equalizer old) {
    super.didUpdateWidget(old);
    if (widget.active && !_c.isAnimating) {
      _c.repeat();
    } else if (!widget.active && _c.isAnimating) {
      _c.stop();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) {
        final t = _c.value * 2 * math.pi;
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: List.generate(_bars, (i) {
            double h;
            if (widget.active) {
              final s = (1 + math.sin(t * _speed[i] + _phase[i])) / 2; // 0..1
              h = 6 + s * 30;
            } else {
              h = 6; // static baseline
            }
            return Container(
              width: 8,
              height: h,
              margin: const EdgeInsets.symmetric(horizontal: 4),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(4),
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    PBTheme.accent,
                    PBTheme.accentLight,
                  ],
                ),
              ),
            );
          }),
        );
      },
    );
  }
}
