import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';

/// DEVIALET — "Salon" landscape control surface for a 1920×1200 screen.
///
/// Two-column split: left = big circular volume ring + transport, right = system
/// header, source/connection status, night-mode + EQ presets, and stereo L/R
/// speaker pills. All commands go over WS via AppState.
class DevialetPage extends StatefulWidget {
  const DevialetPage({super.key});

  @override
  State<DevialetPage> createState() => _DevialetPageState();
}

class _DevialetPageState extends State<DevialetPage> {
  Timer? _volDebounce;
  // While the user is dragging, render the local value so the ring/number track
  // the finger smoothly; keep it after release until the backend echo confirms
  // (anti snap-back), then clear it.
  double? _dragVolume;
  // True tant que le doigt est sur le slider ; on ne libere la valeur optimiste
  // qu'apres le relacher (sinon on couperait le suivi du doigt).
  bool _dragging = false;
  // Anti-blocage : si l'echo WS ne matche jamais exactement (clamping appareil,
  // valeur jamais confirmee), on libere quand meme la valeur optimiste.
  Timer? _dragRelease;

  @override
  void initState() {
    super.initState();
    // One-shot status on mount.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AppState>().send({'type': 'devialet_status'});
    });
  }

  @override
  void dispose() {
    _volDebounce?.cancel();
    _dragRelease?.cancel();
    super.dispose();
  }

  void _sendVolumeDebounced(AppState state, int v) {
    _volDebounce?.cancel();
    _volDebounce = Timer(const Duration(milliseconds: 150), () {
      state.devialetVolume(v);
    });
  }

  // spotifyconnect->Spotify, airplay2->AirPlay, etc.
  String _sourceLabel(String? raw) {
    switch (raw) {
      case 'spotifyconnect':
        return 'Spotify';
      case 'airplay2':
      case 'airplay':
        return 'AirPlay';
      case 'bluetooth':
        return 'Bluetooth';
      case 'optical':
        return t('devialet.source.optical');
      case 'upnp':
        return 'UPnP';
      case 'raat':
        return 'Roon';
      case null:
      case '':
        return t('devialet.source.standby');
      default:
        return raw[0].toUpperCase() + raw.substring(1);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      final d = state.devialetData;

      final online = d['connected'] == true || d['online'] == true;
      final name =
          (d['systemName'] as String?) ?? (d['name'] as String?) ?? 'Devialet';
      final model = (d['model'] as String?) ?? '';
      final firmware = (d['firmware'] as String?) ?? '';
      final nightMode = d['nightMode'] == true || d['night_mode'] == true;
      final eqPreset =
          ((d['eqPreset'] as String?) ?? (d['eq_preset'] as String?) ?? 'flat')
              .toLowerCase();
      final sourceRaw =
          (d['currentSource'] as String?) ?? (d['source'] as String?);
      final sourceLabel = _sourceLabel(sourceRaw);

      // Volume: backend value, overridden by an in-flight (or just-released)
      // drag. Once the backend echo matches the optimistic value, drop it so we
      // track the device again.
      final backendVol =
          (d['volume'] as num?)?.toInt() ?? state.volumeLevel;
      if (!_dragging &&
          _dragVolume != null &&
          backendVol == _dragVolume!.round()) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (!_dragging &&
              _dragVolume != null &&
              backendVol == _dragVolume!.round()) {
            _dragRelease?.cancel();
            setState(() => _dragVolume = null);
          }
        });
      }
      final volume = (_dragVolume ?? backendVol.toDouble()).clamp(0.0, 100.0);
      final volInt = volume.round();
      final muted = volInt == 0;

      final devices = (d['devices'] is List)
          ? List<Map<String, dynamic>>.from(d['devices'])
          : <Map<String, dynamic>>[];

      final enabled = online;

      return Padding(
        padding: const EdgeInsets.all(PBTheme.pagePad),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _Header(
              name: name,
              model: model,
              firmware: firmware,
              online: online,
              sourceLabel: sourceLabel,
            ),
            const SizedBox(height: 24),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ── LEFT: big volume + transport ───────────────────────
                  Expanded(
                    flex: 5,
                    child: _VolumePanel(
                      enabled: enabled,
                      volume: volume,
                      volInt: volInt,
                      muted: muted,
                      onDragStart: () {
                        _dragRelease?.cancel();
                        setState(() {
                          _dragging = true;
                          _dragVolume = volume;
                        });
                      },
                      onDrag: (v) {
                        setState(() => _dragVolume = v);
                        _sendVolumeDebounced(state, v.round());
                      },
                      onDragEnd: (v) {
                        _volDebounce?.cancel();
                        state.devialetVolume(v.round());
                        // Garder la valeur optimiste jusqu'a confirmation par
                        // l'echo WS (efface dans build()) — evite le snap-back.
                        setState(() {
                          _dragging = false;
                          _dragVolume = v;
                        });
                        // Filet anti-blocage : libere quoi qu'il arrive.
                        _dragRelease?.cancel();
                        _dragRelease = Timer(
                          const Duration(milliseconds: 1800),
                          () {
                            if (mounted) setState(() => _dragVolume = null);
                          },
                        );
                      },
                      onMinus: () =>
                          state.send({'type': 'devialet_volume_down'}),
                      onPlus: () => state.send({'type': 'devialet_volume_up'}),
                      onPrev: () => state.send({'type': 'devialet_prev'}),
                      onPlayPause: () {
                        final playing = d['playingState'] == 'playing';
                        state.send({
                          'type': playing ? 'devialet_pause' : 'devialet_play'
                        });
                      },
                      isPlaying: d['playingState'] == 'playing',
                      onNext: () => state.send({'type': 'devialet_next'}),
                      onMute: () => state.send({
                        'type': muted ? 'devialet_unmute' : 'devialet_mute'
                      }),
                    ),
                  ),
                  const SizedBox(width: 24),
                  // ── RIGHT: modes, EQ, speakers ─────────────────────────
                  Expanded(
                    flex: 4,
                    child: _SidePanel(
                      enabled: enabled,
                      nightMode: nightMode,
                      eqPreset: eqPreset,
                      devices: devices,
                      restarting: state.devialetRestarting,
                      onNightToggle: () => state.send({
                        'type': 'devialet_night_mode',
                        'data': !nightMode,
                      }),
                      onEqPreset: (name) => state.send({
                        'type': 'devialet_eq_preset',
                        'data': name,
                      }),
                      onPowerOff: () => state.devialetPowerOff(),
                      onRestart: () => state.devialetRestart(),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────────────────────

class _Header extends StatelessWidget {
  final String name;
  final String model;
  final String firmware;
  final bool online;
  final String sourceLabel;

  const _Header({
    required this.name,
    required this.model,
    required this.firmware,
    required this.online,
    required this.sourceLabel,
  });

  @override
  Widget build(BuildContext context) {
    final sub = [
      if (model.isNotEmpty) model,
      if (firmware.isNotEmpty) 'v$firmware',
    ].join('  ·  ');

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // "D" logo mark.
        Container(
          width: 72,
          height: 72,
          decoration: PBTheme.frosted(active: online, r: 18),
          alignment: Alignment.center,
          child: Text(
            'D',
            style: PBTheme.display.copyWith(
              fontSize: 44,
              color: online ? PBTheme.accent : PBTheme.textMuted,
            ),
          ),
        ),
        const SizedBox(width: 20),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(name, style: PBTheme.h1, overflow: TextOverflow.ellipsis),
              const SizedBox(height: 4),
              Text(
                sub.isEmpty ? 'Devialet' : sub,
                style: PBTheme.caption,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
        const SizedBox(width: 16),
        _StatusBadge(online: online, sourceLabel: sourceLabel),
      ],
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final bool online;
  final String sourceLabel;
  const _StatusBadge({required this.online, required this.sourceLabel});

  @override
  Widget build(BuildContext context) {
    final color = online ? PBTheme.green : PBTheme.red;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: PBTheme.frosted(r: 18),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 14,
            height: 14,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color,
              boxShadow: [
                BoxShadow(color: color.withAlpha(120), blurRadius: 8),
              ],
            ),
          ),
          const SizedBox(width: 14),
          Text(
            online ? sourceLabel : t('devialet.not_detected'),
            style: PBTheme.h3.copyWith(
              color: online ? PBTheme.textPrimary : PBTheme.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Left panel — volume ring + transport
// ─────────────────────────────────────────────────────────────────────────────

class _VolumePanel extends StatelessWidget {
  final bool enabled;
  final double volume; // 0..100
  final int volInt;
  final bool muted;
  final bool isPlaying;
  final VoidCallback onDragStart;
  final ValueChanged<double> onDrag;
  final ValueChanged<double> onDragEnd;
  final VoidCallback onMinus;
  final VoidCallback onPlus;
  final VoidCallback onPrev;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;
  final VoidCallback onMute;

  const _VolumePanel({
    required this.enabled,
    required this.volume,
    required this.volInt,
    required this.muted,
    required this.isPlaying,
    required this.onDragStart,
    required this.onDrag,
    required this.onDragEnd,
    required this.onMinus,
    required this.onPlus,
    required this.onPrev,
    required this.onPlayPause,
    required this.onNext,
    required this.onMute,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1.0 : 0.45,
      child: IgnorePointer(
        ignoring: !enabled,
        child: PBTheme.glassBox(
          padding: const EdgeInsets.all(32),
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Text(t('devialet.volume'), style: PBTheme.label),
              ),
              const SizedBox(height: 12),
              // The ring fills the available square space.
              Expanded(
                child: LayoutBuilder(builder: (context, c) {
                  final ringSize = min(c.maxWidth, c.maxHeight);
                  return Center(
                    child: SizedBox(
                      width: ringSize,
                      height: ringSize,
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          CustomPaint(
                            size: Size.square(ringSize),
                            painter: _VolumeRingPainter(
                              volume / 100,
                              muted ? PBTheme.textMuted : PBTheme.accent,
                            ),
                          ),
                          Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                muted ? t('devialet.muted') : '$volInt',
                                style: PBTheme.clock.copyWith(
                                  fontSize: ringSize * 0.34,
                                  color: muted
                                      ? PBTheme.textMuted
                                      : PBTheme.textPrimary,
                                ),
                              ),
                              if (!muted)
                                Text(t('devialet.out_of_100'),
                                    style: PBTheme.caption),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                }),
              ),
              const SizedBox(height: 20),
              // [-]  slider  [+]
              Row(
                children: [
                  _RoundBtn(icon: Icons.remove, onTap: onMinus),
                  const SizedBox(width: 16),
                  Expanded(
                    child: SliderTheme(
                      data: SliderTheme.of(context).copyWith(
                        trackHeight: 10,
                        activeTrackColor: PBTheme.accent,
                        inactiveTrackColor: Colors.white.withAlpha(28),
                        thumbColor: PBTheme.accentLight,
                        overlayColor: PBTheme.accent.withAlpha(40),
                        thumbShape: const RoundSliderThumbShape(
                            enabledThumbRadius: 16),
                        overlayShape: const RoundSliderOverlayShape(
                            overlayRadius: 30),
                      ),
                      child: Slider(
                        min: 0,
                        max: 100,
                        value: volume,
                        onChangeStart: (_) => onDragStart(),
                        onChanged: onDrag,
                        onChangeEnd: onDragEnd,
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  _RoundBtn(icon: Icons.add, onTap: onPlus),
                ],
              ),
              const SizedBox(height: 24),
              // Transport row: prev / play-pause / next / mute
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _RoundBtn(
                      icon: Icons.skip_previous_rounded, onTap: onPrev),
                  const SizedBox(width: 20),
                  _RoundBtn(
                    icon: isPlaying
                        ? Icons.pause_rounded
                        : Icons.play_arrow_rounded,
                    onTap: onPlayPause,
                    primary: true,
                    size: 84,
                  ),
                  const SizedBox(width: 20),
                  _RoundBtn(icon: Icons.skip_next_rounded, onTap: onNext),
                  const SizedBox(width: 20),
                  _RoundBtn(
                    icon: muted ? Icons.volume_off_rounded : Icons.volume_up_rounded,
                    onTap: onMute,
                    active: muted,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Right panel — night mode, EQ presets, speakers
// ─────────────────────────────────────────────────────────────────────────────

class _SidePanel extends StatelessWidget {
  final bool enabled;
  final bool nightMode;
  final String eqPreset; // lowercase
  final List<Map<String, dynamic>> devices;
  final bool restarting;
  final VoidCallback onNightToggle;
  final ValueChanged<String> onEqPreset;
  final VoidCallback onPowerOff;
  final VoidCallback onRestart;

  const _SidePanel({
    required this.enabled,
    required this.nightMode,
    required this.eqPreset,
    required this.devices,
    required this.restarting,
    required this.onNightToggle,
    required this.onEqPreset,
    required this.onPowerOff,
    required this.onRestart,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      // Les boutons d'alimentation restent actifs même hors-ligne (pour réveiller).
      opacity: enabled ? 1.0 : 0.55,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          IgnorePointer(
            ignoring: !enabled,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              _NightModeCard(active: nightMode, onTap: onNightToggle),
              const SizedBox(height: 20),
              _EqCard(preset: eqPreset, onSelect: onEqPreset),
              const SizedBox(height: 20),
            ]),
          ),
          // Alimentation — toujours cliquable (réveil possible depuis la veille).
          _PowerCard(
            restarting: restarting,
            onPowerOff: onPowerOff,
            onRestart: onRestart,
          ),
          const SizedBox(height: 20),
          Expanded(
            child: IgnorePointer(
              ignoring: !enabled,
              child: _SpeakersCard(devices: devices),
            ),
          ),
        ],
      ),
    );
  }
}

/// Carte alimentation : Mise en veille + Redémarrer (veille + réveil par l'audio).
/// "Redémarrer" demande une confirmation (coupe le son) ; "Veille" est direct.
class _PowerCard extends StatefulWidget {
  final bool restarting;
  final VoidCallback onPowerOff;
  final VoidCallback onRestart;
  const _PowerCard({
    required this.restarting,
    required this.onPowerOff,
    required this.onRestart,
  });

  @override
  State<_PowerCard> createState() => _PowerCardState();
}

class _PowerCardState extends State<_PowerCard> {
  bool _confirm = false;

  @override
  Widget build(BuildContext context) {
    return PBTheme.glassBox(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('devialet.power'), style: PBTheme.label),
          const SizedBox(height: 16),
          if (widget.restarting)
            Row(children: [
              SizedBox(
                width: 26, height: 26,
                child: CircularProgressIndicator(strokeWidth: 3, color: PBTheme.accent),
              ),
              const SizedBox(width: 16),
              Text(t('devialet.restarting_speakers'), style: PBTheme.body),
            ])
          else
            Row(children: [
              Expanded(
                child: _PowerBtn(
                  icon: Icons.power_settings_new_rounded,
                  label: t('devialet.standby'),
                  color: PBTheme.textSecondary,
                  onTap: widget.onPowerOff,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _PowerBtn(
                  icon: Icons.restart_alt_rounded,
                  label: _confirm ? t('common.confirm') : t('devialet.restart'),
                  color: _confirm ? PBTheme.red : PBTheme.orange,
                  active: _confirm,
                  onTap: () {
                    if (!_confirm) {
                      setState(() => _confirm = true);
                      Future.delayed(const Duration(seconds: 4), () {
                        if (mounted) setState(() => _confirm = false);
                      });
                    } else {
                      setState(() => _confirm = false);
                      widget.onRestart();
                    }
                  },
                ),
              ),
            ]),
        ],
      ),
    );
  }
}

class _PowerBtn extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool active;
  final VoidCallback onTap;
  const _PowerBtn({
    required this.icon,
    required this.label,
    required this.color,
    this.active = false,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin + 12,
        decoration: PBTheme.frosted(active: active, r: 18),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 28, color: color),
            const SizedBox(width: 12),
            Text(label,
                style: PBTheme.h3.copyWith(
                    color: active ? color : PBTheme.textPrimary)),
          ],
        ),
      ),
    );
  }
}

class _NightModeCard extends StatelessWidget {
  final bool active;
  final VoidCallback onTap;
  const _NightModeCard({required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        constraints: const BoxConstraints(minHeight: PBTheme.touchMin + 12),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
        decoration: PBTheme.frosted(active: active),
        child: Row(
          children: [
            Icon(
              Icons.nightlight_round,
              size: 32,
              color: active ? PBTheme.orange : PBTheme.textMuted,
            ),
            const SizedBox(width: 18),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(t('devialet.night_mode'), style: PBTheme.h3),
                  Text(
                    active ? t('devialet.on') : t('devialet.off'),
                    style: PBTheme.caption.copyWith(
                      color: active ? PBTheme.orange : PBTheme.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            _MiniSwitch(on: active),
          ],
        ),
      ),
    );
  }
}

class _MiniSwitch extends StatelessWidget {
  final bool on;
  const _MiniSwitch({required this.on});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      width: 64,
      height: 36,
      decoration: BoxDecoration(
        color: on ? PBTheme.orange.withAlpha(180) : Colors.white.withAlpha(28),
        borderRadius: BorderRadius.circular(18),
      ),
      child: AnimatedAlign(
        duration: const Duration(milliseconds: 180),
        alignment: on ? Alignment.centerRight : Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.all(4),
          width: 28,
          height: 28,
          decoration: const BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
          ),
        ),
      ),
    );
  }
}

class _EqCard extends StatelessWidget {
  final String preset; // lowercase
  final ValueChanged<String> onSelect;
  const _EqCard({required this.preset, required this.onSelect});

  static const _presets = [
    ('flat', 'Flat', Icons.horizontal_rule_rounded),
    ('custom', 'Custom', Icons.tune_rounded),
    ('voice', 'Voice', Icons.record_voice_over_rounded),
  ];

  @override
  Widget build(BuildContext context) {
    return PBTheme.glassBox(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('devialet.equalizer'), style: PBTheme.label),
          const SizedBox(height: 16),
          Row(
            children: [
              for (final p in _presets) ...[
                Expanded(
                  child: _EqChip(
                    label: p.$2,
                    icon: p.$3,
                    active: preset == p.$1,
                    onTap: () => onSelect(p.$1),
                  ),
                ),
                if (p != _presets.last) const SizedBox(width: 14),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _EqChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool active;
  final VoidCallback onTap;
  const _EqChip({
    required this.label,
    required this.icon,
    required this.active,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin + 16,
        decoration: PBTheme.frosted(active: active, r: 18),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 30,
              color: active ? PBTheme.accentLight : PBTheme.textSecondary,
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: PBTheme.caption.copyWith(
                color: active ? PBTheme.accentLight : PBTheme.textSecondary,
                fontWeight: active ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SpeakersCard extends StatelessWidget {
  final List<Map<String, dynamic>> devices;
  const _SpeakersCard({required this.devices});

  // Best-effort L/R from the role string.
  String _channel(Map<String, dynamic> d) {
    final role = '${d['role'] ?? ''}'.toLowerCase();
    if (role.contains('left') || role == 'l') return 'L';
    if (role.contains('right') || role == 'r') return 'R';
    return '';
  }

  @override
  Widget build(BuildContext context) {
    if (devices.isEmpty) {
      return PBTheme.glassBox(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t('devialet.speakers'), style: PBTheme.label),
            const SizedBox(height: 16),
            Expanded(
              child: Center(
                child: Text(t('devialet.no_speaker'), style: PBTheme.bodyMuted),
              ),
            ),
          ],
        ),
      );
    }

    return PBTheme.glassBox(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('devialet.speakers'), style: PBTheme.label),
          const SizedBox(height: 16),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var i = 0; i < devices.length; i++) ...[
                  Expanded(
                    child: _SpeakerPill(
                      device: devices[i],
                      channel: _channel(devices[i]),
                    ),
                  ),
                  if (i != devices.length - 1) const SizedBox(width: 16),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SpeakerPill extends StatelessWidget {
  final Map<String, dynamic> device;
  final String channel;
  const _SpeakerPill({required this.device, required this.channel});

  @override
  Widget build(BuildContext context) {
    final name = '${device['name'] ?? t('devialet.speaker')}';
    final leader = device['isLeader'] == true;
    final serial = '${device['serial'] ?? ''}';

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: PBTheme.frosted(active: leader),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: PBTheme.accent.withAlpha(40),
                  borderRadius: BorderRadius.circular(14),
                ),
                alignment: Alignment.center,
                child: Text(
                  channel.isEmpty ? '•' : channel,
                  style: PBTheme.h2.copyWith(color: PBTheme.accentLight),
                ),
              ),
              const Spacer(),
              Icon(Icons.speaker_rounded,
                  size: 28, color: PBTheme.textSecondary),
            ],
          ),
          const SizedBox(height: 14),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(name,
                  style: PBTheme.h3,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              const SizedBox(height: 4),
              Text(
                leader
                    ? t('devialet.leader')
                    : (serial.isNotEmpty ? serial : t('devialet.satellite')),
                style: PBTheme.caption.copyWith(
                  color: leader ? PBTheme.accentLight : PBTheme.textMuted,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Reusable round button
// ─────────────────────────────────────────────────────────────────────────────

class _RoundBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final bool primary;
  final bool active;
  final double size;
  const _RoundBtn({
    required this.icon,
    required this.onTap,
    this.primary = false,
    this.active = false,
    this.size = PBTheme.touchMin + 8,
  });

  @override
  Widget build(BuildContext context) {
    final Color fillBorder =
        active ? PBTheme.accent : Colors.white.withAlpha(22);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: primary
              ? LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    PBTheme.accent.withAlpha(150),
                    PBTheme.accentDim.withAlpha(120),
                  ],
                )
              : LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: active
                      ? [PBTheme.accent.withAlpha(70), PBTheme.accent.withAlpha(30)]
                      : [Colors.white.withAlpha(16), Colors.white.withAlpha(6)],
                ),
          border: Border.all(
            color: primary ? PBTheme.accent.withAlpha(160) : fillBorder,
            width: 1,
          ),
        ),
        child: Icon(
          icon,
          size: primary ? size * 0.5 : size * 0.42,
          color: primary
              ? Colors.white
              : (active ? PBTheme.accentLight : PBTheme.textPrimary),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Volume ring painter (GPU-cheap, transform-free)
// ─────────────────────────────────────────────────────────────────────────────

class _VolumeRingPainter extends CustomPainter {
  final double progress; // 0..1
  final Color color;
  _VolumeRingPainter(this.progress, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final stroke = size.width * 0.06;
    final radius = size.width / 2 - stroke;

    // Background ring
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi * 0.75,
      pi * 1.5,
      false,
      Paint()
        ..color = Colors.white.withAlpha(16)
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.round,
    );

    // Progress arc
    final p = progress.clamp(0.0, 1.0);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi * 0.75,
      pi * 1.5 * p,
      false,
      Paint()
        ..color = color.withAlpha(220)
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.round,
    );

    // End dot
    if (p > 0.02) {
      final angle = -pi * 0.75 + pi * 1.5 * p;
      final dot = Offset(
        center.dx + radius * cos(angle),
        center.dy + radius * sin(angle),
      );
      canvas.drawCircle(dot, stroke * 0.85, Paint()..color = color);
      canvas.drawCircle(
          dot, stroke * 1.6, Paint()..color = color.withAlpha(40));
    }
  }

  @override
  bool shouldRepaint(covariant _VolumeRingPainter old) =>
      old.progress != progress || old.color != color;
}
