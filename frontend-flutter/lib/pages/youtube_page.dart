import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb, defaultTargetPlatform, TargetPlatform;
import 'package:provider/provider.dart';
import 'package:video_player/video_player.dart';
import 'package:flutterpi_gstreamer_video_player/flutterpi_gstreamer_video_player.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';
import '../components/virtual_keyboard.dart';

/// YOUTUBE — landscape salon page (1920×1200, viewed from the couch).
///
/// Three modes:
///  • NOW PLAYING — when state.youtubeNowPlaying != null: big card + stop button.
///  • SEARCH      — when the keyboard/search is open: text field + VirtualKeyboard
///                  + GRID of results (debounced 800ms, min 2 chars).
///  • IDLE        — big red play hero + "Rechercher" + voice hint.
class YouTubePage extends StatefulWidget {
  const YouTubePage({super.key});

  @override
  State<YouTubePage> createState() => _YouTubePageState();
}

class _YouTubePageState extends State<YouTubePage> {
  final _searchController = TextEditingController();
  bool _searchMode = false;
  bool _launching = false;   // tapped a result, waiting for the backend stream URL
  Timer? _debounce;
  Timer? _launchTimeout;     // backstop: clears the spinner if the backend silently drops the request

  void _play(AppState state, Map<String, dynamic> video) {
    setState(() => _launching = true);
    state.youtubePlay(video);
    // Backstop: youtubePlay() can silently drop a repeat tap (its own 5s debounce)
    // and a dropped/lost WS reply would otherwise hang the spinner forever.
    _launchTimeout?.cancel();
    _launchTimeout = Timer(const Duration(seconds: 18), () {
      if (mounted) setState(() => _launching = false);
    });
  }

  void _openSearch(AppState state) {
    setState(() => _searchMode = true);
    state.keyboardVisible = true;
    state.notify();
  }

  void _closeSearch(AppState state) {
    _debounce?.cancel();
    setState(() => _searchMode = false);
    state.keyboardVisible = false;
    state.notify();
  }

  /// Debounced search: 800ms, min 2 chars. The 800ms debounce already
  /// coalesces keystrokes; re-emitting an identical query is idempotent, so
  /// no manual dedup (lets a transient backend failure be retried by retyping).
  void _onQueryChanged(AppState state) {
    setState(() {}); // refresh the field text
    _debounce?.cancel();
    final q = _searchController.text.trim();
    if (q.length < 2) return;
    _debounce = Timer(const Duration(milliseconds: 800), () {
      state.youtubeSearch(q);
    });
  }

  /// Immediate search (OK / search button) — bypasses the debounce.
  void _searchNow(AppState state) {
    _debounce?.cancel();
    final q = _searchController.text.trim();
    if (q.length < 2) return;
    state.youtubeSearch(q);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _launchTimeout?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      final url = state.youtubePlayUrl;
      // Stop "launching" spinner once the URL lands or an error pops.
      if ((url != null || state.youtubeError.isNotEmpty) && _launching) {
        _launchTimeout?.cancel();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) setState(() => _launching = false);
        });
      }

      final Widget content;
      if (url != null && url.isNotEmpty) {
        content = _VideoPlayerView(
          key: ValueKey(url),
          url: url,
          video: state.youtubeNowPlaying ?? const {},
          onStop: state.youtubeStop,
        );
      } else if (_launching) {
        content = _launchingLayout(state);
      } else if (_searchMode) {
        content = _searchLayout(state);
      } else {
        content = _idleLayout(state);
      }

      return Stack(
        children: [
          // Video fills edge-to-edge (no page padding); other modes get padding.
          Positioned.fill(
            child: (url != null && url.isNotEmpty)
                ? content
                : Padding(padding: const EdgeInsets.all(PBTheme.pagePad), child: content),
          ),

          // Error toast (auto-clears in AppState after ~4s).
          if (state.youtubeError.isNotEmpty)
            Positioned(
              left: PBTheme.pagePad,
              right: PBTheme.pagePad,
              bottom: PBTheme.pagePad,
              child: _ErrorToast(message: state.youtubeError),
            ),
        ],
      );
    });
  }

  // ── IDLE ───────────────────────────────────────────────────────────────────
  Widget _idleLayout(AppState state) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 240,
            height: 240,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [PBTheme.red.withAlpha(60), PBTheme.red.withAlpha(14)],
              ),
              border: Border.all(color: PBTheme.red.withAlpha(120), width: 2),
            ),
            child: const Icon(Icons.play_arrow_rounded, color: PBTheme.red, size: 150),
          ),
          const SizedBox(height: 40),
          const Text('YouTube', style: PBTheme.h1),
          const SizedBox(height: 12),
          Text(
            t('youtube.idle_subtitle'),
            style: PBTheme.bodyMuted,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 40),
          _PrimaryButton(
            icon: Icons.search,
            label: t('youtube.search_button'),
            color: PBTheme.red,
            onTap: () => _openSearch(state),
          ),
          const SizedBox(height: 36),
          _VoiceHint(text: t('youtube.voice_hint')),
        ],
      ),
    );
  }

  // ── LAUNCHING (resolving the stream URL) ────────────────────────────────────
  Widget _launchingLayout(AppState state) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(color: PBTheme.red, strokeWidth: 3),
          const SizedBox(height: 28),
          Text(t('youtube.loading_video'), style: PBTheme.h3),
        ],
      ),
    );
  }

  // ── SEARCH ───────────────────────────────────────────────────────────────────
  Widget _searchLayout(AppState state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Search field row.
        Row(
          children: [
            Expanded(
              child: Container(
                height: PBTheme.touchMin,
                padding: const EdgeInsets.symmetric(horizontal: 22),
                decoration: PBTheme.frosted(active: true),
                alignment: Alignment.centerLeft,
                child: Row(
                  children: [
                    Icon(Icons.search, color: PBTheme.accentLight, size: 28),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Text(
                        _searchController.text.isEmpty
                            ? t('youtube.search_hint')
                            : _searchController.text,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: _searchController.text.isEmpty
                            ? PBTheme.bodyMuted
                            : PBTheme.body,
                      ),
                    ),
                    if (_searchController.text.isNotEmpty)
                      GestureDetector(
                        onTap: () {
                          _searchController.clear();
                          setState(() {});
                        },
                        child: const Padding(
                          padding: EdgeInsets.only(left: 8),
                          child: Icon(Icons.close, color: PBTheme.textMuted, size: 26),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 16),
            _IconButton(
              icon: Icons.search,
              color: PBTheme.red,
              onTap: () => _searchNow(state),
            ),
            const SizedBox(width: 12),
            _IconButton(
              icon: Icons.close,
              color: PBTheme.textMuted,
              onTap: () => _closeSearch(state),
            ),
          ],
        ),
        const SizedBox(height: 20),

        // Results grid / status.
        Expanded(child: _results(state)),

        // On-screen keyboard.
        const SizedBox(height: 16),
        VirtualKeyboard(
          controller: _searchController,
          onSubmit: () => _searchNow(state),
          onClose: () => _closeSearch(state),
          onChanged: () => _onQueryChanged(state),
        ),
      ],
    );
  }

  Widget _results(AppState state) {
    if (state.youtubeSearching) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: PBTheme.red, strokeWidth: 3),
            const SizedBox(height: 24),
            Text(t('youtube.searching'), style: PBTheme.h3),
          ],
        ),
      );
    }
    if (state.youtubeResults.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.video_library_outlined,
                color: PBTheme.textMuted.withAlpha(140), size: 80),
            const SizedBox(height: 20),
            Text(t('youtube.min_chars_hint'),
                style: PBTheme.bodyMuted),
          ],
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, c) {
        // Aim for ~360px wide cards across the available width.
        final cols = (c.maxWidth / 360).floor().clamp(2, 5);
        return GridView.builder(
          padding: EdgeInsets.zero,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: cols,
            crossAxisSpacing: 20,
            mainAxisSpacing: 20,
            childAspectRatio: 320 / 240, // thumb (16:9) + text block
          ),
          itemCount: state.youtubeResults.length,
          itemBuilder: (_, i) => _ResultCard(
            video: state.youtubeResults[i],
            onTap: () => _play(state, state.youtubeResults[i]),
          ),
        );
      },
    );
  }
}

// ── VIDEO PLAYER (in-widget, flutter-pi gstreamer, HW-decoded) ──────────────────
class _VideoPlayerView extends StatefulWidget {
  final String url;
  final Map<String, dynamic> video;
  final VoidCallback onStop;
  const _VideoPlayerView({super.key, required this.url, required this.video, required this.onStop});
  @override
  State<_VideoPlayerView> createState() => _VideoPlayerViewState();
}

class _VideoPlayerViewState extends State<_VideoPlayerView> {
  VideoPlayerController? _c;
  bool _ready = false;
  String? _error;
  bool _showControls = true;
  Timer? _hideTimer;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final VideoPlayerController c;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.linux) {
      // flutter-pi's default video player pipeline is VIDEO-ONLY (audio decoded
      // then discarded). Custom pipeline: video -> appsink "sink" (what the
      // plugin reads), audio -> pulsesink (PipeWire default sink = Devialet).
      final pipeline =
          'uridecodebin name=src uri="${widget.url}" ! video/x-raw ! appsink sync=true name="sink" '
          'src. ! audio/x-raw ! queue ! audioconvert ! audioresample ! pulsesink';
      c = FlutterpiVideoPlayerController.withGstreamerPipeline(pipeline);
    } else {
      c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
    }
    _c = c;
    try {
      await c.initialize();
      await c.setVolume(1.0);
      await c.play();
      c.addListener(_tick);
      if (!mounted) return;
      setState(() => _ready = true);
      _scheduleHide();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  // Only rebuild for time/controls when the overlay is visible (no per-frame
  // cost while watching).
  void _tick() {
    if (mounted && _showControls) setState(() {});
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    _c?.removeListener(_tick);
    _c?.dispose();
    super.dispose();
  }

  void _toggleControls() {
    setState(() => _showControls = !_showControls);
    if (_showControls) _scheduleHide();
  }

  void _scheduleHide() {
    _hideTimer?.cancel();
    _hideTimer = Timer(const Duration(seconds: 4), () {
      if (mounted && (_c?.value.isPlaying ?? false)) setState(() => _showControls = false);
    });
  }

  Future<void> _togglePlay() async {
    final c = _c;
    if (c == null) return;
    try {
      c.value.isPlaying ? await c.pause() : await c.play();
    } catch (_) {}
    if (mounted) setState(() {});
    _scheduleHide();
  }

  Future<void> _seekBy(int secs) async {
    final c = _c;
    if (c == null) return;
    // seekTo clamps to [0, duration] internally — no manual clamp needed.
    try {
      await c.seekTo(c.value.position + Duration(seconds: secs));
    } catch (_) {}
    _scheduleHide();
  }

  String _fmt(Duration d) =>
      '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final c = _c;
    final v = c?.value;
    final playing = v?.isPlaying ?? false;
    final ar = (v != null && v.aspectRatio > 0) ? v.aspectRatio : 16 / 9;

    return GestureDetector(
      onTap: _toggleControls,
      behavior: HitTestBehavior.opaque,
      child: ColoredBox(
        color: Colors.black,
        child: Stack(fit: StackFit.expand, children: [
          if (_ready && c != null)
            Center(child: AspectRatio(aspectRatio: ar, child: VideoPlayer(c)))
          else if (_error != null)
            Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.error_outline_rounded, color: PBTheme.red, size: 64),
                const SizedBox(height: 16),
                Text(t('youtube.playback_failed'), style: PBTheme.h3),
                const SizedBox(height: 24),
                _PrimaryButton(icon: Icons.arrow_back_rounded, label: t('youtube.back'), color: PBTheme.red, onTap: widget.onStop),
              ]),
            )
          else
            Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const CircularProgressIndicator(color: PBTheme.red, strokeWidth: 3),
                const SizedBox(height: 24),
                Text(t('youtube.connecting'), style: PBTheme.h3),
              ]),
            ),

          if (_ready && _showControls && c != null && v != null) ...[
            Positioned.fill(
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Colors.black.withAlpha(150), Colors.transparent, Colors.black.withAlpha(190)],
                      stops: const [0.0, 0.45, 1.0],
                    ),
                  ),
                ),
              ),
            ),
            // Top bar: back + title + volume (Devialet) + stop.
            Positioned(
              top: 24, left: 24, right: 24,
              child: Row(children: [
                _circleBtn(Icons.arrow_back_rounded, widget.onStop),
                const SizedBox(width: 20),
                Expanded(child: Text('${widget.video['title'] ?? ''}', style: PBTheme.h3, maxLines: 1, overflow: TextOverflow.ellipsis)),
                const SizedBox(width: 20),
                _volumeControl(context),
                const SizedBox(width: 20),
                _circleBtn(Icons.stop_rounded, widget.onStop, iconColor: PBTheme.red),
              ]),
            ),
            // Center transport.
            Align(
              alignment: Alignment.center,
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                _circleBtn(Icons.replay_10_rounded, () => _seekBy(-10), size: 72),
                const SizedBox(width: 44),
                _circleBtn(playing ? Icons.pause_rounded : Icons.play_arrow_rounded, _togglePlay, size: 104, primary: true),
                const SizedBox(width: 44),
                _circleBtn(Icons.forward_10_rounded, () => _seekBy(10), size: 72),
              ]),
            ),
            // Bottom seek bar + times.
            Positioned(
              left: 32, right: 32, bottom: 30,
              child: Row(children: [
                Text(_fmt(v.position), style: PBTheme.body.copyWith(color: Colors.white)),
                const SizedBox(width: 18),
                Expanded(
                  child: VideoProgressIndicator(
                    c,
                    allowScrubbing: true,
                    padding: const EdgeInsets.symmetric(vertical: 18),
                    colors: VideoProgressColors(
                      playedColor: PBTheme.red,
                      bufferedColor: Colors.white.withAlpha(70),
                      backgroundColor: Colors.white.withAlpha(30),
                    ),
                  ),
                ),
                const SizedBox(width: 18),
                Text(_fmt(v.duration), style: PBTheme.body.copyWith(color: Colors.white)),
              ]),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _volumeControl(BuildContext context) {
    final state = context.read<AppState>();
    final vol = state.volumeLevel;
    void setVol(int v) {
      state.send({'type': 'music_volume', 'data': v.clamp(0, 100)});
      _scheduleHide();
    }
    return Container(
      height: 60,
      padding: const EdgeInsets.symmetric(horizontal: 6),
      decoration: BoxDecoration(
        color: Colors.black.withAlpha(130),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: Colors.white.withAlpha(70), width: 1.5),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        GestureDetector(
          onTap: () => setVol(vol - 5),
          child: const Padding(padding: EdgeInsets.all(10), child: Icon(Icons.volume_down_rounded, color: Colors.white, size: 30)),
        ),
        SizedBox(width: 46, child: Text('$vol', textAlign: TextAlign.center, style: PBTheme.h3.copyWith(color: Colors.white))),
        GestureDetector(
          onTap: () => setVol(vol + 5),
          child: const Padding(padding: EdgeInsets.all(10), child: Icon(Icons.volume_up_rounded, color: Colors.white, size: 30)),
        ),
      ]),
    );
  }

  Widget _circleBtn(IconData icon, VoidCallback onTap, {double size = 60, bool primary = false, Color? iconColor}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: size, height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: primary ? PBTheme.red.withAlpha(220) : Colors.black.withAlpha(130),
          border: Border.all(color: Colors.white.withAlpha(70), width: 1.5),
        ),
        child: Icon(icon, color: iconColor ?? Colors.white, size: size * 0.5),
      ),
    );
  }
}

// ── RESULT CARD ────────────────────────────────────────────────────────────────
class _ResultCard extends StatelessWidget {
  final Map<String, dynamic> video;
  final VoidCallback onTap;
  const _ResultCard({required this.video, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final thumb = (video['thumbnail'] as String?) ?? '';
    final title = (video['title'] as String?) ?? '';
    final channel = (video['channel'] as String?) ?? '';
    final duration = (video['duration'] ?? video['duration_string'] ?? '').toString();

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: PBTheme.frosted(),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Thumbnail (16:9) with play overlay + duration badge.
            AspectRatio(
              aspectRatio: 16 / 9,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (thumb.isNotEmpty)
                    Image.network(thumb, fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const _ThumbPlaceholder())
                  else
                    const _ThumbPlaceholder(),
                  Center(
                    child: Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        color: Colors.black.withAlpha(120),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white.withAlpha(60)),
                      ),
                      child: const Icon(Icons.play_arrow_rounded,
                          color: Colors.white, size: 40),
                    ),
                  ),
                  if (duration.isNotEmpty)
                    Positioned(
                      right: 8,
                      bottom: 8,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: Colors.black.withAlpha(190),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(duration,
                            style: PBTheme.caption.copyWith(color: Colors.white)),
                      ),
                    ),
                ],
              ),
            ),
            // Text block.
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: PBTheme.body.copyWith(fontWeight: FontWeight.w600, height: 1.2),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const Spacer(),
                    if (channel.isNotEmpty)
                      Text(channel,
                          style: PBTheme.caption,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── SHARED WIDGETS ──────────────────────────────────────────────────────────────
class _PrimaryButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _PrimaryButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin + 8,
        padding: const EdgeInsets.symmetric(horizontal: 36),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [color.withAlpha(70), color.withAlpha(40)],
          ),
          border: Border.all(color: color.withAlpha(140), width: 1.5),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 34),
            const SizedBox(width: 16),
            Text(label,
                style: PBTheme.h3.copyWith(color: PBTheme.textPrimary)),
          ],
        ),
      ),
    );
  }
}

class _IconButton extends StatelessWidget {
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  const _IconButton({required this.icon, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: PBTheme.touchMin,
        height: PBTheme.touchMin,
        decoration: BoxDecoration(
          color: color.withAlpha(30),
          border: Border.all(color: color.withAlpha(110)),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Icon(icon, color: color, size: 30),
      ),
    );
  }
}

class _VoiceHint extends StatelessWidget {
  final String text;
  const _VoiceHint({required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.mic_none_rounded, color: PBTheme.accentLight.withAlpha(200), size: 26),
        const SizedBox(width: 12),
        Text(text, style: PBTheme.caption.copyWith(color: PBTheme.accentLight)),
      ],
    );
  }
}

class _ThumbPlaceholder extends StatelessWidget {
  const _ThumbPlaceholder();
  @override
  Widget build(BuildContext context) {
    return Container(
      color: PBTheme.surface,
      child: Icon(Icons.smart_display_outlined,
          color: PBTheme.textMuted.withAlpha(120), size: 48),
    );
  }
}

class _ErrorToast extends StatelessWidget {
  final String message;
  const _ErrorToast({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
      decoration: BoxDecoration(
        color: PBTheme.red.withAlpha(40),
        border: Border.all(color: PBTheme.red.withAlpha(140)),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: PBTheme.red, size: 30),
          const SizedBox(width: 16),
          Expanded(
            child: Text(message,
                style: PBTheme.body.copyWith(color: PBTheme.textPrimary),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ),
        ],
      ),
    );
  }
}
