import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';

/// MAISON / DOMOTIQUE — V3 "Salon" landscape (1920×1200, content area right of the
/// 132px rail). Big touch targets, frosted panels (no blur), width-using layout.
///
/// Features preserved from the prior page:
///  - Header: house icon + "Maison"
///  - "Ouvrir tout" / "Fermer tout" → state.rollerAll('open'|'close')
///  - 3 roller cards (volet_gauche/milieu/droit): name, position %, state text,
///    up / stop(red) / down → state.rollerAction(id, 'open'|'close'|'stop')
///  - Portail card → state.triggerPortail()
///  - Guinguette plug card (color by ['on']) + ON/OFF → state.plugToggle('guinguette')
///  - One-shot {type:'domotique_status'} on mount (added — was missing before).
class DomotiquePage extends StatefulWidget {
  const DomotiquePage({super.key});

  @override
  State<DomotiquePage> createState() => _DomotiquePageState();
}

class _DomotiquePageState extends State<DomotiquePage> {
  @override
  void initState() {
    super.initState();
    // One-shot status refresh on mount.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AppState>().send({'type': 'domotique_status'});
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      final d = state.domotiqueData;
      final vg = d['volet_gauche'] as Map<String, dynamic>? ?? const {};
      final vm = d['volet_milieu'] as Map<String, dynamic>? ?? const {};
      final vd = d['volet_droit'] as Map<String, dynamic>? ?? const {};
      final portail = d['portail'] as Map<String, dynamic>? ?? const {};
      final guinguette = d['guinguette'] as Map<String, dynamic>? ?? const {};

      return Padding(
        padding: const EdgeInsets.all(PBTheme.pagePad),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── Header: title + big global open/close ──────────────────────
            Row(
              children: [
                Container(
                  width: 64,
                  height: 64,
                  decoration: PBTheme.frosted(active: true, r: 18),
                  alignment: Alignment.center,
                  child: Icon(Icons.home_rounded, size: 36, color: PBTheme.accent),
                ),
                const SizedBox(width: 20),
                Text(t('domotique.title'), style: PBTheme.h1),
                const Spacer(),
                _GlobalButton(
                  label: t('domotique.open_all'),
                  icon: Icons.keyboard_double_arrow_up_rounded,
                  color: PBTheme.green,
                  onTap: () => state.rollerAll('open'),
                ),
                const SizedBox(width: 16),
                _GlobalButton(
                  label: t('domotique.close_all'),
                  icon: Icons.keyboard_double_arrow_down_rounded,
                  color: PBTheme.accent,
                  onTap: () => state.rollerAll('close'),
                ),
              ],
            ),
            const SizedBox(height: 24),

            // ── Volets — 3 roller cards across the full width ───────────────
            Expanded(
              flex: 3,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: _RollerCard(state: state, id: 'volet_gauche', dev: vg)),
                  const SizedBox(width: 20),
                  Expanded(child: _RollerCard(state: state, id: 'volet_milieu', dev: vm)),
                  const SizedBox(width: 20),
                  Expanded(child: _RollerCard(state: state, id: 'volet_droit', dev: vd)),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ── Portail + Guinguette ────────────────────────────────────────
            Expanded(
              flex: 2,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: _PortailCard(state: state, dev: portail)),
                  const SizedBox(width: 20),
                  Expanded(child: _PlugCard(state: state, id: 'guinguette', dev: guinguette)),
                ],
              ),
            ),
          ],
        ),
      );
    });
  }
}

// ── Global open/close button ───────────────────────────────────────────────
class _GlobalButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  const _GlobalButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin,
        padding: const EdgeInsets.symmetric(horizontal: 26),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [color.withAlpha(54), color.withAlpha(26)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          border: Border.all(color: color.withAlpha(120), width: 1),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 30, color: color),
            const SizedBox(width: 12),
            Text(label, style: PBTheme.h3.copyWith(color: color)),
          ],
        ),
      ),
    );
  }
}

// ── Roller (volet) card ────────────────────────────────────────────────────
class _RollerCard extends StatelessWidget {
  final AppState state;
  final String id;
  final Map<String, dynamic> dev;
  const _RollerCard({required this.state, required this.id, required this.dev});

  @override
  Widget build(BuildContext context) {
    // STRICT form: a device never discovered is seeded to const {} -> online null.
    final online = dev['online'] == true;
    final name = dev['name'] as String? ?? id;
    final position = (dev['position'] as num?)?.toInt() ?? 0;
    final s = dev['state'] as String? ?? 'stop';
    final isOpening = online && (s == 'open' || s == 'opening');
    final isClosing = online && (s == 'close' || s == 'closing');
    final isMoving = isOpening || isClosing;
    final stateLabel = !online
        ? t('domotique.offline')
        : isOpening
            ? t('domotique.opening')
            : isClosing
                ? t('domotique.closing')
                : t('domotique.stopped');
    final stateColor =
        !online ? PBTheme.textMuted : (isMoving ? PBTheme.orange : PBTheme.textMuted);

    return Opacity(
      opacity: online ? 1.0 : 0.45,
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: PBTheme.frosted(active: isMoving),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Name + state pill
            Row(
              children: [
                Expanded(
                  child: Text(
                    name,
                    style: PBTheme.h3,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: stateColor.withAlpha(28),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    stateLabel,
                    style: PBTheme.caption.copyWith(
                      color: stateColor,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),

            // Big position % centered
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      online ? '$position%' : '—',
                      style: PBTheme.display.copyWith(
                        color: !online
                            ? PBTheme.textMuted
                            : (isMoving ? PBTheme.orange : PBTheme.accent),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(online ? t('domotique.position') : t('domotique.unavailable'), style: PBTheme.bodyMuted),
                  ],
                ),
              ),
            ),

            // Up / Stop / Down — no-op when the device is offline
            Row(
              children: [
                Expanded(
                  child: _RollerBtn(
                    icon: Icons.keyboard_arrow_up_rounded,
                    active: isOpening,
                    onTap: online ? () => state.rollerAction(id, 'open') : () {},
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _RollerBtn(
                    icon: Icons.stop_rounded,
                    isStop: true,
                    onTap: online ? () => state.rollerAction(id, 'stop') : () {},
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _RollerBtn(
                    icon: Icons.keyboard_arrow_down_rounded,
                    active: isClosing,
                    onTap: online ? () => state.rollerAction(id, 'close') : () {},
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RollerBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final bool isStop;
  final bool active;
  const _RollerBtn({
    required this.icon,
    required this.onTap,
    this.isStop = false,
    this.active = false,
  });

  @override
  Widget build(BuildContext context) {
    final Color tint = isStop ? PBTheme.red : PBTheme.accent;
    final bool lit = isStop || active;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin,
        decoration: BoxDecoration(
          color: lit ? tint.withAlpha(isStop ? 30 : 40) : Colors.white.withAlpha(10),
          border: Border.all(
            color: lit ? tint.withAlpha(120) : Colors.white.withAlpha(22),
            width: 1,
          ),
          borderRadius: BorderRadius.circular(16),
        ),
        alignment: Alignment.center,
        child: Icon(icon, size: 40, color: lit ? tint : PBTheme.textPrimary),
      ),
    );
  }
}

// ── Portail card ───────────────────────────────────────────────────────────
class _PortailCard extends StatelessWidget {
  final AppState state;
  final Map<String, dynamic> dev;
  const _PortailCard({required this.state, required this.dev});

  @override
  Widget build(BuildContext context) {
    // STRICT form: a device never discovered is seeded to const {} -> online null.
    final online = dev['online'] == true;
    final name = dev['name'] as String? ?? t('domotique.gate');
    final btnColor = online ? PBTheme.cyan : PBTheme.textMuted;
    return Opacity(
      opacity: online ? 1.0 : 0.45,
      child: Container(
        padding: const EdgeInsets.all(28),
        decoration: PBTheme.frosted(),
        child: Row(
          children: [
            Container(
              width: 96,
              height: 96,
              decoration: PBTheme.frosted(r: 20),
              alignment: Alignment.center,
              child: Icon(Icons.sensor_door_outlined, size: 52, color: btnColor),
            ),
            const SizedBox(width: 24),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(name, style: PBTheme.h2, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 6),
                  Text(
                    online ? t('domotique.gate_garden') : t('domotique.offline'),
                    style: PBTheme.bodyMuted.copyWith(
                      color: online ? null : PBTheme.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            GestureDetector(
              // No-op when the device is offline.
              onTap: online ? () => state.triggerPortail() : () {},
              child: Container(
                height: PBTheme.touchMin,
                padding: const EdgeInsets.symmetric(horizontal: 28),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [btnColor.withAlpha(54), btnColor.withAlpha(24)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  border: Border.all(color: btnColor.withAlpha(120), width: 1),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.lock_open_rounded, size: 30, color: btnColor),
                    const SizedBox(width: 12),
                    Text(t('domotique.open'), style: PBTheme.h3.copyWith(color: btnColor)),
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

// ── Guinguette plug card ───────────────────────────────────────────────────
class _PlugCard extends StatelessWidget {
  final AppState state;
  final String id;
  final Map<String, dynamic> dev;
  const _PlugCard({required this.state, required this.id, required this.dev});

  @override
  Widget build(BuildContext context) {
    // STRICT form: a device never discovered is seeded to const {} -> online null.
    final online = dev['online'] == true;
    final name = dev['name'] as String? ?? id;
    final isOn = online && dev['on'] == true;
    final accent = isOn ? PBTheme.green : PBTheme.textMuted;

    return Opacity(
      opacity: online ? 1.0 : 0.45,
      child: GestureDetector(
        // No-op when the device is offline.
        onTap: online ? () => state.plugToggle(id) : () {},
        child: Container(
          padding: const EdgeInsets.all(28),
          decoration: PBTheme.frosted(active: isOn),
          child: Row(
            children: [
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(
                  color: isOn ? PBTheme.green.withAlpha(34) : Colors.white.withAlpha(10),
                  border: Border.all(
                    color: isOn ? PBTheme.green.withAlpha(120) : Colors.white.withAlpha(22),
                    width: 1,
                  ),
                  borderRadius: BorderRadius.circular(20),
                ),
                alignment: Alignment.center,
                child: Icon(
                  isOn ? Icons.lightbulb : Icons.lightbulb_outline,
                  size: 52,
                  color: accent,
                ),
              ),
              const SizedBox(width: 24),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(name, style: PBTheme.h2, maxLines: 1, overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 6),
                    Text(
                      !online ? t('domotique.offline') : (isOn ? t('domotique.on') : t('domotique.off')),
                      style: PBTheme.bodyMuted.copyWith(color: accent),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              // ON / OFF toggle
              Container(
                height: PBTheme.touchMin,
                width: 132,
                decoration: BoxDecoration(
                  color: isOn ? PBTheme.green.withAlpha(30) : Colors.white.withAlpha(10),
                  border: Border.all(
                    color: isOn ? PBTheme.green.withAlpha(120) : Colors.white.withAlpha(22),
                    width: 1,
                  ),
                  borderRadius: BorderRadius.circular(18),
                ),
                alignment: Alignment.center,
                child: Text(
                  !online ? '—' : (isOn ? 'ON' : 'OFF'),
                  style: PBTheme.h2.copyWith(
                    color: isOn ? PBTheme.green : PBTheme.textMuted,
                    letterSpacing: 2,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
