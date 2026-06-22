import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../i18n.dart';
import '../components/weather_icon.dart';

/// HOME — a glanceable bento that aggregates the room: giant clock, now-playing,
/// weather, and quick domotique/devialet tiles. Readable from the couch; tap a
/// tile to drill into its domain.
class AccueilPage extends StatefulWidget {
  const AccueilPage({super.key});
  @override
  State<AccueilPage> createState() => _AccueilPageState();
}

class _AccueilPageState extends State<AccueilPage> {
  Timer? _clock;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _now = DateTime.now());
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  static const _dayKeys = [
    'home.day.mon', 'home.day.tue', 'home.day.wed', 'home.day.thu',
    'home.day.fri', 'home.day.sat', 'home.day.sun',
  ];
  static const _monthKeys = [
    '', 'home.month.jan', 'home.month.feb', 'home.month.mar', 'home.month.apr',
    'home.month.may', 'home.month.jun', 'home.month.jul', 'home.month.aug',
    'home.month.sep', 'home.month.oct', 'home.month.nov', 'home.month.dec',
  ];

  String get _hhmm => '${_now.hour.toString().padLeft(2, '0')}:${_now.minute.toString().padLeft(2, '0')}';
  String get _date => '${t(_dayKeys[_now.weekday - 1])} ${_now.day} ${t(_monthKeys[_now.month])}';

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      return Padding(
        padding: const EdgeInsets.all(PBTheme.pagePad),
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // Left column (wider): clock hero + now-playing.
          Expanded(
            flex: 6,
            child: Column(children: [
              Expanded(flex: 5, child: _clockTile()),
              const SizedBox(height: 24),
              Expanded(flex: 4, child: _nowPlayingTile(state)),
            ]),
          ),
          const SizedBox(width: 24),
          // Right column: weather + maison + devialet.
          Expanded(
            flex: 4,
            child: Column(children: [
              Expanded(flex: 4, child: _weatherTile(state)),
              const SizedBox(height: 24),
              Expanded(flex: 3, child: Row(children: [
                Expanded(child: _maisonTile(state)),
                const SizedBox(width: 24),
                Expanded(child: _devialetTile(state)),
              ])),
            ]),
          ),
        ]),
      );
    });
  }

  Widget _tile({required Widget child, VoidCallback? onTap, bool active = false}) => GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(28),
          decoration: PBTheme.frosted(active: active),
          child: child,
        ),
      );

  Widget _clockTile() => _tile(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
          FittedBox(fit: BoxFit.scaleDown, child: Text(_hhmm, style: PBTheme.clock)),
          const SizedBox(height: 8),
          Text(_date, style: PBTheme.h2.copyWith(color: PBTheme.textSecondary)),
        ]),
      );

  Widget _nowPlayingTile(AppState state) {
    final m = state.musicData;
    final playing = m['playing'] == true;
    final title = '${m['title'] ?? ''}';
    final cover = '${m['cover'] ?? m['image'] ?? ''}';
    return _tile(
      onTap: () => state.goToPage(0),
      active: playing,
      child: title.isEmpty
          ? Row(children: [
              Icon(Icons.music_note_rounded, size: 56, color: PBTheme.textMuted),
              const SizedBox(width: 20),
              Expanded(child: Text(t('home.now_playing.empty'), style: PBTheme.bodyMuted)),
            ])
          : Row(children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: cover.startsWith('http')
                    ? Image.network(cover, width: 130, height: 130, fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _coverFallback())
                    : _coverFallback(),
              ),
              const SizedBox(width: 24),
              Expanded(
                child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(title, style: PBTheme.h2, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 6),
                  Text('${m['artist'] ?? ''}', style: PBTheme.bodyMuted, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 16),
                  Row(children: [
                    _miniBtn(Icons.skip_previous_rounded, state.musicPrev),
                    const SizedBox(width: 12),
                    _miniBtn(playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                        () => playing ? state.musicPause() : state.musicResume(), big: true),
                    const SizedBox(width: 12),
                    _miniBtn(Icons.skip_next_rounded, state.musicNext),
                  ]),
                ]),
              ),
            ]),
    );
  }

  Widget _miniBtn(IconData icon, VoidCallback onTap, {bool big = false}) => GestureDetector(
        onTap: onTap,
        child: Container(
          width: big ? 64 : 56, height: big ? 64 : 56,
          decoration: BoxDecoration(shape: BoxShape.circle,
              color: big ? PBTheme.accent.withAlpha(50) : Colors.white.withAlpha(14),
              border: Border.all(color: big ? PBTheme.accent.withAlpha(120) : Colors.white.withAlpha(24))),
          child: Icon(icon, color: big ? PBTheme.accent : PBTheme.textPrimary, size: big ? 36 : 28),
        ),
      );

  Widget _coverFallback() => Container(width: 130, height: 130, color: PBTheme.surface,
      child: Icon(Icons.music_note_rounded, color: PBTheme.textMuted, size: 48));

  Widget _weatherTile(AppState state) {
    final w = state.weatherData;
    final has = w.isNotEmpty && w['temp'] != null;
    final cond = '${w['condition'] ?? w['description'] ?? ''}';
    final wIcon = '${w['icon'] ?? ''}';
    return _tile(
      onTap: () => state.goToPage(1),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Row(children: [
          Text(t('home.weather.title'), style: PBTheme.label),
          const Spacer(),
          Text('${w['city'] ?? ''}'.toUpperCase(), style: PBTheme.caption),
        ]),
        const SizedBox(height: 12),
        if (!has)
          Text('—', style: PBTheme.display)
        else
          Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            WeatherIcon(icon: wIcon, condition: cond, size: 96),
            const SizedBox(width: 20),
            Text('${(w['temp'] as num?)?.round() ?? '--'}°', style: PBTheme.display.copyWith(color: PBTheme.textPrimary)),
          ]),
        const SizedBox(height: 10),
        Text(cond.isEmpty ? '' : cond[0].toUpperCase() + cond.substring(1),
            style: PBTheme.h3.copyWith(color: PBTheme.textSecondary)),
        if (w['feels_like'] != null) ...[
          const SizedBox(height: 6),
          Text(t('home.weather.feels_like') + ' ' + ((w['feels_like'] as num?)?.round()).toString() + '°', style: PBTheme.caption),
        ],
      ]),
    );
  }

  Widget _maisonTile(AppState state) {
    final d = state.domotiqueData;
    final guinguette = d['guinguette'];
    final lampOn = guinguette is Map && guinguette['on'] == true;
    return _tile(
      onTap: () => state.goToPage(5),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(t('home.house.title'), style: PBTheme.label),
        const SizedBox(height: 16),
        Row(children: [
          Icon(Icons.blinds_rounded, size: 40, color: PBTheme.accent),
          const SizedBox(width: 14),
          Expanded(child: Text(t('home.house.shutters'), style: PBTheme.h3)),
        ]),
        const SizedBox(height: 14),
        Row(children: [
          Icon(Icons.lightbulb_rounded, size: 40, color: lampOn ? PBTheme.orange : PBTheme.textMuted),
          const SizedBox(width: 14),
          Expanded(child: Text(lampOn ? t('home.house.guinguette_on') : t('home.house.guinguette'), style: PBTheme.h3)),
        ]),
      ]),
    );
  }

  Widget _devialetTile(AppState state) {
    final vol = state.volumeLevel;
    return _tile(
      onTap: () => state.goToPage(4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(t('home.devialet.title'), style: PBTheme.label),
        const SizedBox(height: 16),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text('$vol', style: PBTheme.display.copyWith(color: PBTheme.textPrimary)),
          const Padding(padding: EdgeInsets.only(bottom: 12), child: Text('%', style: PBTheme.h2)),
        ]),
        const SizedBox(height: 12),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: vol / 100, minHeight: 10,
            backgroundColor: Colors.white.withAlpha(20),
            valueColor: AlwaysStoppedAnimation(PBTheme.accent),
          ),
        ),
      ]),
    );
  }
}
