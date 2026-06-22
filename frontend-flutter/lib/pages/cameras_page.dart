import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';

class CamerasPage extends StatefulWidget {
  const CamerasPage({super.key});

  @override
  State<CamerasPage> createState() => _CamerasPageState();
}

class _CamerasPageState extends State<CamerasPage> {
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    // Poll snapshots every 3s ONLY while Caméras (page 3) is the active domain.
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) return;
      final state = context.read<AppState>();
      if (state.currentPage == 3 && !state.onHome) {
        state.send({'type': 'cameras_snapshots'});
      }
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  bool _isOnline(Map<String, dynamic> cam) {
    final v = cam['online'] ?? cam['state'];
    if (v is bool) return v;
    final s = '$v'.toLowerCase();
    return s == 'online' ||
        s == 'connected' ||
        s == 'true' ||
        s == 'ok' ||
        s == '1';
  }

  String _relTime(Map<String, dynamic> cam) {
    final ts = cam['_ts'];
    if (ts == null) return '';
    int? ms;
    if (ts is num) {
      ms = ts.toInt();
      // Tolerate seconds-based epochs.
      if (ms < 100000000000) ms *= 1000;
    } else {
      ms = int.tryParse('$ts');
      if (ms != null && ms < 100000000000) ms *= 1000;
    }
    if (ms == null) return '';
    final diff = DateTime.now().millisecondsSinceEpoch - ms;
    if (diff < 0) return t('cameras.just_now');
    final sec = diff ~/ 1000;
    if (sec < 5) return t('cameras.just_now');
    if (sec < 60) return t('cameras.ago') + ' ' + sec.toString() + 's';
    final min = sec ~/ 60;
    if (min < 60) return t('cameras.ago') + ' ' + min.toString() + 'min';
    final h = min ~/ 60;
    return t('cameras.ago') + ' ' + h.toString() + 'h';
  }

  // ── Build ────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      final cams = state.cameras;
      final onlineCount = cams.where(_isOnline).length;

      return Padding(
        padding: const EdgeInsets.all(PBTheme.pagePad),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _header(state, cams.length, onlineCount),
            const SizedBox(height: PBTheme.pagePad),
            Expanded(
              child: cams.isEmpty
                  ? _emptyState()
                  : LayoutBuilder(
                      builder: (context, constraints) =>
                          _grid(state, cams, constraints),
                    ),
            ),
          ],
        ),
      );
    });
  }

  // ── Header ──────────────────────────────────────────────────────────────

  Widget _header(AppState state, int total, int online) {
    final allOffline = total > 0 && online == 0;
    final badgeColor = total == 0
        ? PBTheme.textMuted
        : (allOffline ? PBTheme.red : PBTheme.green);
    final badgeText = total == 0
        ? t('cameras.none')
        : online.toString() +
            ' ' +
            t('cameras.online') +
            (total > online ? ' / ' + total.toString() : '');

    return Row(
      children: [
        Container(
          width: 64,
          height: 64,
          decoration: PBTheme.frosted(active: true, r: 18),
          child: Icon(Icons.videocam_rounded,
              size: 34, color: PBTheme.accentLight),
        ),
        const SizedBox(width: 18),
        Text(t('cameras.title'), style: PBTheme.h1),
        const SizedBox(width: 18),
        // Status badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
          decoration: PBTheme.frosted(r: 30),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: badgeColor,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Text(badgeText,
                  style: PBTheme.caption.copyWith(color: PBTheme.textPrimary)),
            ],
          ),
        ),
        const Spacer(),
        // Portail trigger
        _PortailButton(onTap: state.triggerPortail),
      ],
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────

  Widget _emptyState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 56,
            height: 56,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation(PBTheme.accent),
            ),
          ),
          const SizedBox(height: 28),
          Text(t('cameras.searching'),
              style: PBTheme.h3.copyWith(color: PBTheme.textSecondary)),
        ],
      ),
    );
  }

  // ── Responsive grid ──────────────────────────────────────────────────────

  Widget _grid(
      AppState state, List<Map<String, dynamic>> cams, BoxConstraints c) {
    final n = cams.length;
    int cols;
    int rows;
    if (n == 1) {
      cols = 1;
      rows = 1;
    } else if (n == 2) {
      cols = 2;
      rows = 1;
    } else {
      // 3 or 4 -> 2x2 (3 leaves one slot empty)
      cols = 2;
      rows = (n / 2).ceil();
    }

    const gap = 22.0;
    final cellW = (c.maxWidth - gap * (cols - 1)) / cols;
    final cellH = (c.maxHeight - gap * (rows - 1)) / rows;

    // For a single camera, cap the size and center it so it stays 16:9-ish
    // instead of stretching the whole wide area.
    if (n == 1) {
      final maxW = c.maxWidth;
      final maxH = c.maxHeight;
      double w = maxW;
      double h = w * 9 / 16;
      if (h > maxH) {
        h = maxH;
        w = h * 16 / 9;
      }
      return Center(
        child: SizedBox(
          width: w,
          height: h,
          child: _CameraCard(
            cam: cams[0],
            online: _isOnline(cams[0]),
            relTime: _relTime(cams[0]),
            onTap: () => state.setFullscreenCam(cams[0]),
          ),
        ),
      );
    }

    return Wrap(
      spacing: gap,
      runSpacing: gap,
      children: List.generate(n, (i) {
        return SizedBox(
          width: cellW,
          height: cellH,
          child: _CameraCard(
            cam: cams[i],
            online: _isOnline(cams[i]),
            relTime: _relTime(cams[i]),
            onTap: () => state.setFullscreenCam(cams[i]),
          ),
        );
      }),
    );
  }
}

// ── Portail button ───────────────────────────────────────────────────────────

class _PortailButton extends StatelessWidget {
  final VoidCallback onTap;
  const _PortailButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin,
        padding: const EdgeInsets.symmetric(horizontal: 26),
        decoration: PBTheme.accentButton,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.door_sliding_outlined,
                size: 28, color: PBTheme.accent),
            const SizedBox(width: 12),
            Text(t('cameras.gate'),
                style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                    color: PBTheme.accent)),
          ],
        ),
      ),
    );
  }
}

// ── Camera card ───────────────────────────────────────────────────────────────

class _CameraCard extends StatelessWidget {
  final Map<String, dynamic> cam;
  final bool online;
  final String relTime;
  final VoidCallback onTap;

  const _CameraCard({
    required this.cam,
    required this.online,
    required this.relTime,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final name = cam['name'] as String? ?? t('cameras.default_name');
    final snapshot = cam['snapshot'] as String? ?? '';

    // Decode defensively: base64Decode throws (FormatException) on a truncated
    // or partial WS payload, BEFORE Image.memory's errorBuilder can catch it.
    // Fall back to the placeholder instead of crashing the build (zéro-crash).
    Uint8List? bytes;
    if (snapshot.isNotEmpty) {
      try {
        bytes = base64Decode(snapshot);
      } catch (_) {
        bytes = null;
      }
    }

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: PBTheme.frosted(r: PBTheme.radius),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Snapshot or placeholder
            if (bytes != null)
              Image.memory(
                bytes,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                errorBuilder: (_, __, ___) => _Placeholder(name: name),
              )
            else
              _Placeholder(name: name),

            // Top scrim for legibility of badges
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              height: 70,
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Colors.black.withAlpha(140), Colors.transparent],
                  ),
                ),
              ),
            ),

            // LIVE badge (only when online and has a decoded frame)
            if (online && bytes != null)
              const Positioned(top: 16, left: 16, child: _LiveBadge()),

            // Relative timestamp (top-right)
            if (relTime.isNotEmpty)
              Positioned(
                top: 16,
                right: 16,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.black.withAlpha(150),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    relTime,
                    style: PBTheme.caption.copyWith(color: PBTheme.textPrimary),
                  ),
                ),
              ),

            // Bottom scrim + name + online dot
            Positioned(
              bottom: 0,
              left: 0,
              right: 0,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.bottomCenter,
                    end: Alignment.topCenter,
                    colors: [Colors.black.withAlpha(170), Colors.transparent],
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color: online ? PBTheme.green : PBTheme.textMuted,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: PBTheme.h3.copyWith(color: PBTheme.textPrimary),
                      ),
                    ),
                    if (!online)
                      Text(t('cameras.offline'),
                          style: PBTheme.caption
                              .copyWith(color: PBTheme.textMuted)),
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

// ── LIVE badge (pulsing red dot) ──────────────────────────────────────────────

class _LiveBadge extends StatefulWidget {
  const _LiveBadge();

  @override
  State<_LiveBadge> createState() => _LiveBadgeState();
}

class _LiveBadgeState extends State<_LiveBadge>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black.withAlpha(150),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FadeTransition(
            opacity: Tween(begin: 0.35, end: 1.0).animate(_ctrl),
            child: Container(
              width: 12,
              height: 12,
              decoration: const BoxDecoration(
                color: PBTheme.red,
                shape: BoxShape.circle,
              ),
            ),
          ),
          const SizedBox(width: 8),
          const Text('LIVE',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.5,
                  color: PBTheme.textPrimary)),
        ],
      ),
    );
  }
}

// ── Placeholder (no snapshot / decode error) ─────────────────────────────────

class _Placeholder extends StatelessWidget {
  final String name;
  const _Placeholder({required this.name});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: PBTheme.ambient(),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.videocam_off_rounded,
              color: PBTheme.textMuted, size: 56),
          const SizedBox(height: 16),
          Text(name,
              style: PBTheme.bodyMuted.copyWith(color: PBTheme.textMuted)),
          const SizedBox(height: 6),
          Text(t('cameras.no_signal'),
              style: PBTheme.caption.copyWith(color: PBTheme.textMuted)),
        ],
      ),
    );
  }
}
