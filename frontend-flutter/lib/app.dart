import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'stores/app_state.dart';
import 'theme.dart';
import 'i18n.dart';
import 'components/wave_animation.dart';
import 'pages/accueil_page.dart';
import 'pages/music_page.dart';
import 'pages/weather_page.dart';
import 'pages/youtube_page.dart';
import 'pages/cameras_page.dart';
import 'pages/devialet_page.dart';
import 'pages/domotique_page.dart';
import 'pages/settings_page.dart';

/// V3 "Salon" shell — persistent left rail + full-bleed drill-in + full-width
/// voice band. HOME (Accueil) is the calm default; 60s idle returns to it.
class PiBoardApp extends StatefulWidget {
  const PiBoardApp({super.key});
  @override
  State<PiBoardApp> createState() => _PiBoardAppState();
}

class _PiBoardAppState extends State<PiBoardApp> {
  Timer? _autoReturn;

  // Rail destinations. index 0 = Accueil (UI-only HOME); 1..6 map to domain
  // page indices 0..5 (Musique..Maison) — see _railToPage.
  // (icône, clé i18n) — le libellé est traduit au rendu via t().
  static const _rail = [
    (Icons.dashboard_rounded, 'nav.home'),
    (Icons.music_note_rounded, 'nav.music'),
    (Icons.wb_sunny_rounded, 'nav.weather'),
    (Icons.smart_display_rounded, 'nav.youtube'),
    (Icons.videocam_rounded, 'nav.cameras'),
    (Icons.speaker_rounded, 'nav.devialet'),
    (Icons.home_rounded, 'nav.house'),
  ];

  @override
  void dispose() {
    _autoReturn?.cancel();
    super.dispose();
  }

  // Tâche en cours -> on ne ramène jamais l'utilisateur à l'Accueil de force.
  bool _busy(AppState state) =>
      state.onHome ||
      state.youtubeNowPlaying != null ||
      state.fullscreenCam != null ||
      state.onSettings ||
      state.keyboardVisible ||
      state.assistantState != 'IDLE';

  void _bump(AppState state) {
    // Reset RÉEL du timer 60s : à n'appeler QUE sur une vraie interaction
    // (pointer down, tap rail). On annule puis on relaisse _ensureAutoReturn
    // (post-frame) le réarmer si le contexte le permet.
    _autoReturn?.cancel();
    _ensureAutoReturn(state);
  }

  void _ensureAutoReturn(AppState state) {
    // Idempotent : appelé à CHAQUE rebuild (post-frame). Si le timer tourne déjà,
    // no-op -> les rebuilds ~2/s de la lecture musicale ne le réinitialisent plus
    // (sinon le retour Accueil 60s ne se déclenchait jamais pendant la musique).
    if (_busy(state)) {
      _autoReturn?.cancel();
      _autoReturn = null;
      return;
    }
    if (_autoReturn != null && _autoReturn!.isActive) return;
    _autoReturn = Timer(const Duration(seconds: 60), () {
      if (mounted) context.read<AppState>().goHome();
    });
  }

  Widget _domainPage(int i) {
    switch (i) {
      case 0: return const MusicPage();
      case 1: return const WeatherPage();
      case 2: return const YouTubePage();
      case 3: return const CamerasPage();
      case 4: return const DevialetPage();
      case 5: return const DomotiquePage();
      default: return const MusicPage();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _ensureAutoReturn(state));
      final voiceActive = state.assistantState != 'IDLE';

      return Scaffold(
        backgroundColor: PBTheme.bg,
        body: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (_) => _bump(state),
          child: Stack(children: [
            // Static ambient backdrop (no animated/blur cost).
            Positioned.fill(
              child: DecoratedBox(
                decoration: PBTheme.ambient(playing: state.musicData['playing'] == true),
              ),
            ),

            Row(children: [
              _rail_(state),
              Expanded(
                child: Column(children: [
                  // Full-width voice band (collapses to 0 when idle).
                  AnimatedSize(
                    duration: const Duration(milliseconds: 130),
                    curve: Curves.easeOutCubic,
                    child: voiceActive ? _voiceBand(state) : const SizedBox(width: double.infinity),
                  ),
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 260),
                      transitionBuilder: (child, anim) =>
                          FadeTransition(opacity: anim, child: child),
                      child: KeyedSubtree(
                        key: ValueKey(state.onSettings
                            ? 'settings'
                            : (state.onHome ? 'home' : 'p${state.currentPage}')),
                        child: state.onSettings
                            ? SettingsPage(state: state)
                            : (state.onHome ? const AccueilPage() : _domainPage(state.currentPage)),
                      ),
                    ),
                  ),
                ]),
              ),
            ]),

            // Halo d'état plein écran — feedback INSTANT et impossible à rater :
            // violet = écoute, cyan = réflexion, vert = parle.
            if (voiceActive)
              Positioned.fill(child: _StatusGlow(state: state.assistantState)),

            if (state.fullscreenCam != null) _cameraOverlay(state),
          ]),
        ),
      );
    });
  }

  // ── Left rail ────────────────────────────────────────────────────────────
  Widget _rail_(AppState state) {
    return Container(
      width: PBTheme.railWidth,
      color: PBTheme.bgElevated.withAlpha(180),
      child: Column(children: [
        const SizedBox(height: 18),
        Text('pi', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: PBTheme.accent, letterSpacing: -1)),
        const SizedBox(height: 14),
        Expanded(
          child: ListView.builder(
            padding: EdgeInsets.zero,
            itemCount: _rail.length,
            itemBuilder: (_, i) {
              // En page Réglages, AUCUN item de domaine/accueil n'est actif (sinon le
              // dernier `currentPage` resterait surligné EN PLUS du bouton Réglages).
              final active = !state.onSettings &&
                  (i == 0 ? state.onHome : (!state.onHome && state.currentPage == i - 1));
              return _railItem(state, i, _rail[i].$1, t(_rail[i].$2), active);
            },
          ),
        ),
        _nowPlayingStub(state),
        const SizedBox(height: 8),
        _wsDot(state),
        const SizedBox(height: 8),
        // Séparateur visuel : « Réglages » est détaché des 6 pages de domaine.
        Container(
          height: 1,
          margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
          color: PBTheme.textMuted.withAlpha(40),
        ),
        _railSettings(state),
        const SizedBox(height: 8),
      ]),
    );
  }

  Widget _railItem(AppState state, int i, IconData icon, String label, bool active) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () { _bump(state); i == 0 ? state.goHome() : state.goToPage(i - 1); },
      child: Container(
        height: 84,
        margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: active
            ? BoxDecoration(color: PBTheme.accent.withAlpha(38), borderRadius: BorderRadius.circular(18),
                border: Border.all(color: PBTheme.accent.withAlpha(90)))
            : null,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, size: 30, color: active ? PBTheme.accent : PBTheme.textMuted),
          const SizedBox(height: 4),
          Text(label, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600,
              color: active ? PBTheme.accent : PBTheme.textSecondary)),
        ]),
      ),
    );
  }

  Widget _nowPlayingStub(AppState state) {
    final playing = state.musicData['playing'] == true;
    final title = '${state.musicData['title'] ?? ''}';
    if (!playing || title.isEmpty) return const SizedBox.shrink();
    final cover = '${state.musicData['cover'] ?? state.musicData['image'] ?? ''}';
    return GestureDetector(
      onTap: () => state.goToPage(0),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 10),
        padding: const EdgeInsets.all(8),
        decoration: PBTheme.glass(opacity: 0.05),
        child: Column(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: cover.startsWith('http')
                ? Image.network(cover, width: 84, height: 84, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => _coverFallback())
                : _coverFallback(),
          ),
          const SizedBox(height: 6),
          Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: PBTheme.textPrimary)),
        ]),
      ),
    );
  }

  Widget _coverFallback() => Container(
        width: 84, height: 84, color: PBTheme.surface,
        child: Icon(Icons.music_note_rounded, color: PBTheme.textMuted, size: 28),
      );

  Widget _wsDot(AppState state) => Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        Container(width: 9, height: 9, decoration: BoxDecoration(shape: BoxShape.circle,
            color: state.wsConnected ? PBTheme.green : PBTheme.red)),
        const SizedBox(width: 6),
        Text(state.wsConnected ? 'en ligne' : 'hors ligne',
            style: TextStyle(fontSize: 11, color: state.wsConnected ? PBTheme.green : PBTheme.red)),
      ]);

  // ── Full-width voice band ─────────────────────────────────────────────────
  Widget _voiceBand(AppState state) {
    final s = state.assistantState;
    final Color tint = s == 'LISTENING'
        ? PBTheme.accent
        : s == 'PROCESSING'
            ? PBTheme.cyan
            : s == 'SPEAKING'
                ? PBTheme.green
                : PBTheme.accent;
    // En LISTENING on affiche la transcription EN LIVE (partiels Vosk/Voxtral)
    // mot a mot ; tant que rien n'est dit, on garde l'invite "J'écoute…".
    final String text = s == 'LISTENING'
        ? (state.transcript.isNotEmpty ? state.transcript : 'J\'écoute…')
        : s == 'PROCESSING'
            ? (state.transcript.isNotEmpty ? '« ${state.transcript} »' : 'Je réfléchis…')
            : (state.speakingText.isNotEmpty ? state.speakingText : 'Je parle…');
    return Container(
      height: PBTheme.voiceBandHeight,
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 28),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [tint.withAlpha(48), tint.withAlpha(12)]),
        border: Border(bottom: BorderSide(color: tint.withAlpha(120), width: 2)),
      ),
      child: Row(children: [
        WaveAnimation(state: s),
        const SizedBox(width: 22),
        Expanded(
          child: Text(text, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 30, fontWeight: FontWeight.w600, color: tint == PBTheme.accent ? PBTheme.accentLight : tint)),
        ),
      ]),
    );
  }

  // ── Fullscreen camera overlay (no blur) ───────────────────────────────────
  Widget _cameraOverlay(AppState state) {
    final snap = '${state.fullscreenCam!['snapshot'] ?? ''}';
    // Decodage defensif : un snapshot non-base64 ferait planter base64Decode
    // (FormatException) -> ecran noir fige. On retombe sur le placeholder.
    Uint8List? bytes;
    if (snap.isNotEmpty) {
      try {
        bytes = base64Decode(snap);
      } catch (_) {
        bytes = null;
      }
    }
    return Positioned.fill(
      child: GestureDetector(
        onTap: () => state.setFullscreenCam(null),
        child: Container(
          color: Colors.black,
          child: Stack(fit: StackFit.expand, children: [
            if (bytes != null)
              Image.memory(bytes, fit: BoxFit.contain, gaplessPlayback: true)
            else
              const Center(child: Icon(Icons.videocam_off_rounded, size: 64, color: PBTheme.textMuted)),
            Positioned(
              bottom: 0, left: 0, right: 0,
              child: Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(gradient: LinearGradient(
                    begin: Alignment.topCenter, end: Alignment.bottomCenter,
                    colors: [Colors.transparent, Colors.black.withAlpha(210)])),
                child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                  Text('${state.fullscreenCam!['name'] ?? ''}', style: PBTheme.h2),
                  const Text('Touchez pour fermer', style: PBTheme.caption),
                ]),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  // ── Bouton Réglages (bas du rail) ─────────────────────────────────────────
  // Grande cible OPAQUE (84px, toute la largeur du rail) — calquée sur _railItem,
  // contrairement à l'ancien petit icône 26px non-opaque difficile à viser.
  Widget _railSettings(AppState state) {
    final active = state.onSettings;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () { _bump(state); state.goSettings(); },
      child: Container(
        height: 84,
        margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: active
            ? BoxDecoration(color: PBTheme.accent.withAlpha(38), borderRadius: BorderRadius.circular(18),
                border: Border.all(color: PBTheme.accent.withAlpha(90)))
            : null,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(Icons.tune_rounded, size: 30, color: active ? PBTheme.accent : PBTheme.textMuted),
          const SizedBox(height: 4),
          Text(t('nav.settings'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600,
              color: active ? PBTheme.accent : PBTheme.textSecondary)),
        ]),
      ),
    );
  }
}

/// Halo plein écran pulsant — retour d'état INSTANT du wake word / pipeline.
/// Apparaît dès LISTENING (≈50 ms via WebSocket local), bordure + vignette
/// colorée selon l'état. Ne capte pas le tactile.
class _StatusGlow extends StatefulWidget {
  final String state;
  const _StatusGlow({required this.state});
  @override
  State<_StatusGlow> createState() => _StatusGlowState();
}

class _StatusGlowState extends State<_StatusGlow> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 850))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Color tint = widget.state == 'PROCESSING'
        ? PBTheme.cyan
        : widget.state == 'SPEAKING'
            ? PBTheme.green
            : PBTheme.accent; // LISTENING + défaut
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, __) {
          final t = 0.5 + 0.5 * _c.value; // pulsation 0.5..1.0
          return DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: tint.withOpacity(t), width: 8),
              gradient: RadialGradient(
                radius: 1.2,
                colors: [Colors.transparent, tint.withOpacity(0.14 * t)],
                stops: const [0.70, 1.0],
              ),
            ),
          );
        },
      ),
    );
  }
}
