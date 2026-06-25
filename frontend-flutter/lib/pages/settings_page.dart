import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';
import '../components/settings_widgets.dart';

/// Page PARAMÈTRES PLEINE (zone de contenu, à côté du rail — plus d'overlay).
/// Réglages directement modifiables, sur DEUX COLONNES de cartes pour tout voir
/// d'un coup. Style "Salon".
class SettingsPage extends StatefulWidget {
  final AppState state;
  const SettingsPage({super.key, required this.state});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  // Valeurs transitoires pendant un drag (rendu fluide, commit au relâcher).
  double? _bright, _vol, _len, _thr, _cool;

  AppState get s => widget.state;

  /// Lecture défensive d'une valeur config numérique. cfg() ne garantit que la
  /// non-nullité (pas le type) : si la clé existe avec un type non numérique
  /// (String/bool/Map), un `as num` lèverait et casserait toute la page. Ici on
  /// retombe silencieusement sur [def] (zéro-crash).
  num _num(String section, String key, num def) {
    final v = s.cfg(section, key, def);
    if (v is num) return v;
    return num.tryParse('$v') ?? def;
  }

  @override
  Widget build(BuildContext context) {
    final restartNeeded = s.pendingRestart.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // En-tête de page (le rail reste à gauche pour sortir des Réglages).
        Padding(
          padding: const EdgeInsets.fromLTRB(32, 26, 32, 14),
          child: Row(children: [
            Icon(Icons.tune_rounded, color: PBTheme.accent, size: 34),
            const SizedBox(width: 16),
            Text(t('settings.title'), style: PBTheme.h1),
          ]),
        ),
        // DEUX COLONNES indépendamment défilables -> aucune section n'est coupée
        // même si AUDIO/BLUETOOTH s'allongent (listes de sorties/appareils).
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    children: [
                      _voiceSection(),
                      _wakewordSection(),
                      _displaySection(),
                      _systemSection(),
                    ],
                  ),
                ),
                const SizedBox(width: 20),
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    children: [
                      _audioSection(),
                      _bluetoothSection(),
                      _remoteSection(),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        if (restartNeeded) _restartBanner(),
      ],
    );
  }

  // ── VOIX / IA ───────────────────────────────────────────────────────────
  Widget _voiceSection() {
    final ttsProvider = '${s.cfg('tts', 'provider', 'gateway')}';
    final llmModel = '${s.cfg('llm', 'model', 'mistral-small-latest')}';
    final maxTokens = (_len ?? _num('llm', 'max_tokens', 200).toDouble());
    return SettingsSection(title: t('settings.section.voice'), children: [
      _gatewayPill(),
      const SizedBox(height: 14),
      SettingRow(
        label: t('settings.language'),
        stacked: true,
        control: ChipSelector(
          value: appLocale,
          options: const [('fr', 'Français'), ('en', 'English')],
          onSelect: (v) {
            setAppLocale(v);            // bascule immédiate de l'UI
            s.configSet('ui', 'locale', v);
            s.notify();
          },
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('voice.tts'),
        sub: t('voice.tts.sub'),
        stacked: true,
        control: ChipSelector(
          value: ttsProvider,
          options: [
            ('gateway', t('voice.tts.gateway')),
            ('voxtral', t('voice.tts.cloud')),
            ('piper', t('voice.tts.piper')),
          ],
          onSelect: (v) => s.configSet('tts', 'provider', v),
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('voice.llm'),
        sub: t('voice.llm.sub'),
        stacked: true,
        control: ChipSelector(
          value: llmModel,
          options: [
            ('mistral-small-latest', t('voice.llm.small')),
            ('ministral-8b-latest', t('voice.llm.fast')),
            ('mistral-large-latest', t('voice.llm.large')),
          ],
          onSelect: (v) => s.configSet('llm', 'model', v),
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('voice.length'),
        stacked: true,
        control: LabeledSlider(
          value: maxTokens, min: 60, max: 400, divisions: 17,
          valueLabel: '${maxTokens.round()}',
          onChanged: (v) => setState(() => _len = v),
          onChangeEnd: (v) {
            setState(() => _len = null);
            s.configSet('llm', 'max_tokens', v.round());
          },
        ),
      ),
      const SizedBox(height: 6),
      Text(
        t('voice.note'),
        style: PBTheme.caption,
      ),
    ]);
  }

  // ── Pastille passerelle IA (gratuit local vs cloud payant) ────────────────
  Widget _gatewayPill() {
    final g = (s.systemInfo?['gateway'] as Map?) ?? const {};
    final eff = '${g['effective'] ?? 'unknown'}';
    final model = '${g['model'] ?? ''}';
    late final Color c;
    late final IconData ic;
    late final String title;
    String? sub;
    switch (eff) {
      case 'free':
        c = PBTheme.green;
        ic = Icons.bolt_rounded;
        title = t('gw.free');
        sub = model.isNotEmpty ? t('gw.free.sub') + ' · ' + model : t('gw.free.sub');
        break;
      case 'fallback':
        c = PBTheme.orange;
        ic = Icons.warning_amber_rounded;
        title = t('gw.fallback');
        sub = t('gw.fallback.sub');
        break;
      case 'cloud':
        c = PBTheme.cyan;
        ic = Icons.cloud_rounded;
        title = t('gw.cloud');
        sub = t('gw.cloud.sub');
        break;
      default:
        c = PBTheme.textMuted;
        ic = Icons.sync_rounded;
        title = t('gw.checking');
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: c.withAlpha(28),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: c.withAlpha(110)),
      ),
      child: Row(children: [
        Icon(ic, color: c, size: 28),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: PBTheme.body.copyWith(color: c, fontWeight: FontWeight.w700),
                maxLines: 2, overflow: TextOverflow.ellipsis),
            if (sub != null) ...[
              const SizedBox(height: 2),
              Text(sub, style: PBTheme.caption, maxLines: 2, overflow: TextOverflow.ellipsis),
            ],
          ]),
        ),
      ]),
    );
  }

  // ── MOT-RÉVEIL ────────────────────────────────────────────────────────────
  // Moteur + mot + sensibilité + délai. Tout est lu au démarrage du détecteur
  // -> chaque changement marque « redémarrage requis ».
  Widget _wakewordSection() {
    final engine = '${s.cfg('wakeword', 'engine', 'livekit')}';
    final word = '${s.cfg('wakeword', 'name', 'terminator')}';
    final livekitModel = '${s.cfg('wakeword', 'livekit_model', 'terminator_v1')}';
    final thr = (_thr ?? _num('wakeword', 'threshold', 0.42).toDouble());
    final cooldown = (_cool ?? _num('wakeword', 'cooldown_s', 10).toDouble());
    return SettingsSection(title: t('settings.section.wakeword'), children: [
      SettingRow(
        label: t('ww.engine'),
        sub: t('ww.engine.sub'),
        stacked: true,
        control: ChipSelector(
          value: engine,
          options: const [
            ('livekit', 'Livekit ✓'),
            ('oww', 'openWakeWord'),
          ],
          // Livekit ne connaît que « terminator » : choisir Livekit force le mot.
          onSelect: (v) {
            if (v == 'livekit' && word != 'terminator') {
              s.configSet('wakeword', 'name', 'terminator', restart: true);
            }
            s.configSet('wakeword', 'engine', v, restart: true);
          },
        ),
      ),
      const Divider(height: 1),
      if (engine == 'livekit') ...[
        SettingRow(
          label: t('ww.livekit_model'),
          sub: t('ww.livekit_model.sub'),
          stacked: true,
          control: ChipSelector(
            value: livekitModel,
            options: const [
              ('terminator_v1', 'Terminator v1'),
              ('terminator_v2', 'Terminator v2'),
            ],
            onSelect: (v) => s.configSet('wakeword', 'livekit_model', v, restart: true),
          ),
        ),
        const Divider(height: 1),
      ],
      SettingRow(
        label: t('ww.word'),
        sub: t('ww.word.sub'),
        stacked: true,
        control: ChipSelector(
          value: word,
          options: const [
            ('terminator', 'Terminator'),
            ('hey_jarvis', 'Hey Jarvis'),
            ('hey_mycroft', 'Hey Mycroft'),
            ('alexa', 'Alexa'),
          ],
          // Seul openWakeWord sait changer de mot -> on bascule le moteur si besoin.
          onSelect: (v) {
            if (v != 'terminator' && engine != 'oww') {
              s.configSet('wakeword', 'engine', 'oww', restart: true);
            }
            s.configSet('wakeword', 'name', v, restart: true);
          },
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('ww.sensitivity'),
        sub: t('ww.sensitivity.sub'),
        stacked: true,
        control: LabeledSlider(
          value: thr, min: 0.30, max: 0.95, divisions: 65,
          valueLabel: thr.toStringAsFixed(2),
          onChanged: (v) => setState(() => _thr = v),
          onChangeEnd: (v) {
            setState(() => _thr = null);
            final nv = double.parse(v.toStringAsFixed(2));
            // Ne marque « redémarrage requis » que si la valeur change vraiment.
            if (nv != _num('wakeword', 'threshold', 0.42).toDouble()) {
              s.configSet('wakeword', 'threshold', nv, restart: true);
            }
          },
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('ww.cooldown'),
        sub: t('ww.cooldown.sub'),
        stacked: true,
        control: LabeledSlider(
          value: cooldown, min: 2, max: 30, divisions: 28,
          valueLabel: '${cooldown.round()}s',
          onChanged: (v) => setState(() => _cool = v),
          onChangeEnd: (v) {
            setState(() => _cool = null);
            if (v.round() != _num('wakeword', 'cooldown_s', 10).round()) {
              s.configSet('wakeword', 'cooldown_s', v.round(), restart: true);
            }
          },
        ),
      ),
    ]);
  }

  // ── AUDIO ───────────────────────────────────────────────────────────────
  Widget _audioSection() {
    final vol = (_vol ?? s.volumeLevel.toDouble());
    return SettingsSection(title: t('settings.section.audio'), children: [
      Text(t('audio.output'), style: PBTheme.h3),
      const SizedBox(height: 10),
      ...s.audioSinks.map((sink) {
        final name = '${sink['name'] ?? ''}';
        final isDefault = sink['is_default'] == true;
        final isBt = sink['bluetooth'] == true;
        final connected = sink['connected'] != false;
        final connecting = s.connectingSink == name;
        final lower = name.toLowerCase();
        final IconData icon = isBt
            ? Icons.speaker_rounded
            : (lower.contains('hdmi') ? Icons.tv_rounded : Icons.airplay_rounded);
        return GestureDetector(
          onTap: connecting
              ? null
              : () => s.selectOutput(name, needsConnect: isBt && !connected),
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(14),
            decoration: PBTheme.frosted(active: isDefault, r: 14),
            child: Row(children: [
              Icon(icon, size: 24,
                  color: isDefault ? PBTheme.accent : PBTheme.textSecondary),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${sink['description'] ?? name}',
                      style: PBTheme.body, maxLines: 1, overflow: TextOverflow.ellipsis),
                  if (isBt && !connected)
                    Text(connecting ? t('audio.connecting') : t('audio.connect_hint'),
                        style: PBTheme.caption),
                ]),
              ),
              const SizedBox(width: 10),
              if (connecting)
                SizedBox(
                    width: 24, height: 24,
                    child: CircularProgressIndicator(
                        strokeWidth: 2.5, color: PBTheme.accentLight))
              else if (isDefault)
                Icon(Icons.check_circle_rounded, color: PBTheme.accent, size: 24),
            ]),
          ),
        );
      }),
      if (s.audioSinks.isEmpty)
        Padding(padding: const EdgeInsets.all(8), child: Text(t('audio.loading'), style: PBTheme.caption)),
      const Divider(height: 24),
      SettingRow(
        label: t('audio.volume'),
        stacked: true,
        control: LabeledSlider(
          value: vol, min: 0, max: 100, divisions: 100,
          valueLabel: '${vol.round()}',
          onChanged: (v) => setState(() => _vol = v),
          onChangeEnd: (v) {
            s.devialetVolume(v.round());
            // Garde la valeur optimiste un court instant (l'echo backend lag) pour
            // eviter un retour visuel en arriere, puis libere.
            Future.delayed(const Duration(milliseconds: 1500), () {
              if (mounted) setState(() => _vol = null);
            });
          },
        ),
      ),
    ]);
  }

  // ── BLUETOOTH ───────────────────────────────────────────────────────────
  Widget _bluetoothSection() {
    return SettingsSection(title: t('settings.section.bluetooth'), children: [
      Row(children: [
        Expanded(
          child: Text(
            s.btAvailable ? t('bt.speakers') : t('bt.unavailable'),
            style: PBTheme.h3,
          ),
        ),
        const SizedBox(width: 12),
        GestureDetector(
          onTap: (s.btAvailable && !s.btScanning) ? () => s.btScan(true) : null,
          child: Container(
            height: PBTheme.touchMin,
            padding: const EdgeInsets.symmetric(horizontal: 20),
            decoration: PBTheme.frosted(active: s.btScanning, r: 16),
            alignment: Alignment.center,
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              if (s.btScanning)
                SizedBox(
                  width: 20, height: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2.5, color: PBTheme.accentLight),
                )
              else
                Icon(Icons.bluetooth_searching_rounded,
                    size: 24,
                    color: s.btAvailable ? PBTheme.accentLight : PBTheme.textSecondary),
              const SizedBox(width: 10),
              Text(
                s.btScanning ? t('bt.searching') : t('bt.search'),
                style: PBTheme.body.copyWith(
                  color: s.btAvailable ? PBTheme.accentLight : PBTheme.textSecondary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ]),
          ),
        ),
      ]),
      if (s.btActionError != null) ...[
        const SizedBox(height: 12),
        Text(s.btActionError!,
            style: PBTheme.caption.copyWith(color: PBTheme.red)),
      ],
      const SizedBox(height: 16),
      ...s.btDevices.map(_btDeviceRow),
      if (s.btDevices.isEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(
            s.btAvailable
                ? t('bt.empty')
                : t('bt.no_adapter'),
            style: PBTheme.caption,
          ),
        ),
    ]);
  }

  Widget _btDeviceRow(Map<String, dynamic> d) {
    final mac = '${d['mac'] ?? ''}';
    final connected = d['connected'] == true;
    final paired = d['paired'] == true;
    final audio = d['audio'] == true;
    final busy = s.btBusy.contains(mac);
    final state = busy
        ? t('bt.busy')
        : (connected ? t('bt.connected') : (paired ? t('bt.paired') : t('bt.available')));
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: PBTheme.frosted(active: connected, r: 14),
      child: Row(children: [
        Icon(
          audio ? Icons.speaker_rounded : Icons.bluetooth_rounded,
          size: 26,
          color: connected ? PBTheme.accent : PBTheme.textSecondary,
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${d['name'] ?? mac}',
                style: PBTheme.body, maxLines: 1, overflow: TextOverflow.ellipsis),
            Text(state, style: PBTheme.caption),
          ]),
        ),
        const SizedBox(width: 10),
        if (busy)
          SizedBox(
            width: PBTheme.touchMin, height: PBTheme.touchMin,
            child: Center(
              child: SizedBox(
                width: 22, height: 22,
                child: CircularProgressIndicator(
                    strokeWidth: 2.5, color: PBTheme.accentLight),
              ),
            ),
          )
        else ...[
          if (connected)
            _btPill(t('bt.disconnect'), () => s.btDisconnect(mac))
          else if (paired)
            _btPill(t('bt.connect'), () => s.btConnect(mac))
          else
            _btPill(t('bt.pair'), () => s.btPair(mac)),
          if (paired) ...[
            const SizedBox(width: 8),
            _btPill(t('bt.forget'), () => s.btForget(mac), muted: true),
          ],
        ],
      ]),
    );
  }

  Widget _btPill(String label, VoidCallback onTap, {bool muted = false}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: PBTheme.touchMin,
        padding: const EdgeInsets.symmetric(horizontal: 18),
        alignment: Alignment.center,
        decoration: PBTheme.frosted(r: 12),
        child: Text(
          label,
          style: PBTheme.body.copyWith(
            color: muted ? PBTheme.textSecondary : PBTheme.accentLight,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  // ── AFFICHAGE ───────────────────────────────────────────────────────────
  Widget _displaySection() {
    final bright = (_bright ?? _num('screen', 'brightness', 100).toDouble());
    final start = _num('screen', 'sleep_hour_start', 22).toInt();
    final end = _num('screen', 'sleep_hour_end', 6).toInt();
    return SettingsSection(title: t('settings.section.display'), children: [
      SettingRow(
        label: t('display.brightness'),
        stacked: true,
        control: LabeledSlider(
          value: bright, min: 10, max: 100, divisions: 18,
          valueLabel: '${bright.round()}%',
          onChanged: (v) => setState(() => _bright = v),
          onChangeEnd: (v) {
            setState(() => _bright = null);
            s.screenBrightness(v.round());
          },
        ),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('display.sleep'),
        sub: t('display.sleep.sub'),
        control: Row(mainAxisSize: MainAxisSize.min, children: [
          _HourStepper(value: start, onChanged: (h) =>
              s.configSet('screen', 'sleep_hour_start', h, restart: true)),
          const Padding(padding: EdgeInsets.symmetric(horizontal: 8),
              child: Text('→', style: PBTheme.h3)),
          _HourStepper(value: end, onChanged: (h) =>
              s.configSet('screen', 'sleep_hour_end', h, restart: true)),
        ]),
      ),
      const Divider(height: 1),
      SettingRow(
        label: t('display.screen'),
        control: Row(mainAxisSize: MainAxisSize.min, children: [
          _SmallBtn(icon: Icons.light_mode_rounded, onTap: () => s.send({'type': 'screen_wake'})),
          const SizedBox(width: 12),
          _SmallBtn(icon: Icons.bedtime_rounded, onTap: () => s.send({'type': 'screen_sleep'})),
        ]),
      ),
    ]);
  }

  // ── SYSTÈME ─────────────────────────────────────────────────────────────
  Widget _systemSection() {
    return SettingsSection(title: t('settings.section.system'), children: [
      ActionButton(
        icon: Icons.restart_alt_rounded, label: t('system.reboot'),
        color: PBTheme.orange, confirm: true, onTap: s.systemReboot),
      const SizedBox(height: 12),
      ActionButton(
        icon: Icons.sync_rounded, label: t('system.restart'),
        color: PBTheme.cyan, confirm: true, onTap: s.systemRestartBackend),
      const SizedBox(height: 12),
      ActionButton(
        icon: Icons.speaker_rounded, label: t('system.restart_speakers'),
        color: PBTheme.accent, confirm: true, onTap: s.devialetRestart),
      const SizedBox(height: 12),
      ActionButton(
        icon: Icons.power_settings_new_rounded, label: t('system.shutdown'),
        color: PBTheme.red, confirm: true, onTap: s.systemShutdown),
    ]);
  }

  // ── ADMIN À DISTANCE (QR) ───────────────────────────────────────────────
  Widget _remoteSection() {
    final url = '${s.systemInfo?['admin_url'] ?? 'http://PiBoardV2.local:8000/admin/'}';
    final ipUrl = '${s.systemInfo?['admin_url_ip'] ?? ''}';
    return SettingsSection(title: t('settings.section.admin'), children: [
      Center(
        child: Column(children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
            ),
            child: QrImageView(data: url, size: 200),
          ),
          const SizedBox(height: 16),
          Text(t('admin.scan'),
              style: PBTheme.body, textAlign: TextAlign.center),
          const SizedBox(height: 6),
          Text(url.replaceFirst('http://', ''),
              style: PBTheme.caption.copyWith(color: PBTheme.accentLight)),
          if (ipUrl.isNotEmpty)
            Text(t('admin.or') + ' ' + ipUrl.replaceFirst('http://', ''), style: PBTheme.caption),
          const SizedBox(height: 8),
          Text(t('admin.creds'),
              style: PBTheme.caption, textAlign: TextAlign.center),
        ]),
      ),
    ]);
  }

  Widget _restartBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
      decoration: BoxDecoration(
        color: PBTheme.orange.withAlpha(36),
        border: Border(top: BorderSide(color: PBTheme.orange.withAlpha(120), width: 2)),
      ),
      child: Row(children: [
        const Icon(Icons.info_outline_rounded, color: PBTheme.orange, size: 26),
        const SizedBox(width: 14),
        Expanded(
          child: Text(t('restart.banner'),
              style: PBTheme.body),
        ),
        const SizedBox(width: 14),
        GestureDetector(
          onTap: s.systemRestartBackend,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            decoration: PBTheme.frosted(active: true, r: 14),
            child: Text(t('restart.apply'),
                style: PBTheme.h3.copyWith(color: PBTheme.accentLight)),
          ),
        ),
      ]),
    );
  }
}

/// Petit sélecteur d'heure -/valeur/+ (0–23).
class _HourStepper extends StatelessWidget {
  final int value;
  final ValueChanged<int> onChanged;
  const _HourStepper({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      _SmallBtn(icon: Icons.remove, onTap: () => onChanged((value - 1 + 24) % 24)),
      Container(
        width: 56, alignment: Alignment.center,
        child: Text('${value}h', style: PBTheme.h3),
      ),
      _SmallBtn(icon: Icons.add, onTap: () => onChanged((value + 1) % 24)),
    ]);
  }
}

class _SmallBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _SmallBtn({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 52, height: 52,
        decoration: PBTheme.frosted(r: 14),
        child: Icon(icon, size: 24, color: PBTheme.textPrimary),
      ),
    );
  }
}
