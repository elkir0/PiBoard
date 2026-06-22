import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../stores/app_state.dart';
import '../theme.dart';
import '../components/weather_icon.dart';
import '../i18n.dart';

/// MÉTÉO — landscape "Salon" layout for the 1920×1200 touchscreen.
/// LEFT: big current block (emoji, huge temp, condition, feels-like, city,
/// details row with humidity / wind / UV badge).
/// RIGHT: hourly forecast (horizontal scroll, up to 8 cards) + 3-day forecast row.
/// Triggers a one-shot {type:'weather_refresh'} on mount when weatherData is empty.
class WeatherPage extends StatefulWidget {
  const WeatherPage({super.key});

  @override
  State<WeatherPage> createState() => _WeatherPageState();
}

class _WeatherPageState extends State<WeatherPage> {
  @override
  void initState() {
    super.initState();
    // One-shot refresh when the page mounts with no data yet.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      final w = state.weatherData;
      if (w.isEmpty || w['loaded'] != true) {
        state.send({'type': 'weather_refresh'});
      }
    });
  }

  String _capitalize(String s) {
    if (s.isEmpty) return s;
    return s[0].toUpperCase() + s.substring(1);
  }

  // ── UV badge color thresholds: green<=2 yellow<=5 orange<=7 red>7 ──────────
  Color _uvColor(num uv) {
    if (uv <= 2) return PBTheme.green;
    if (uv <= 5) return PBTheme.orange.withRed(0xF5).withGreen(0xD0); // warm yellow tone
    if (uv <= 7) return PBTheme.orange;
    return PBTheme.red;
  }

  String _uvLabel(num uv) {
    if (uv <= 2) return t('weather.uv_low');
    if (uv <= 5) return t('weather.uv_moderate');
    if (uv <= 7) return t('weather.uv_high');
    if (uv <= 10) return t('weather.uv_very_high');
    return t('weather.uv_extreme');
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(builder: (_, state, __) {
      final w = state.weatherData;
      final loaded = w.isNotEmpty && w['loaded'] == true;

      final icon = w['icon'] as String? ?? '';
      final temp = w['temp'] != null ? '${w['temp']}' : '--';
      final rawCondition = (w['condition'] ?? w['description'] ?? '') as String;
      final condition = rawCondition.isNotEmpty ? _capitalize(rawCondition) : '--';
      final feelsLike = w['feels_like'] != null ? '${w['feels_like']}' : '';
      final city = (w['city'] as String? ?? 'Guadeloupe').toUpperCase();
      final humidity = w['humidity'] != null ? '${w['humidity']}' : '--';
      final wind = w['wind'] != null ? '${w['wind']}' : '--';
      final uvRaw = w['uv'] ?? w['uvi'] ?? w['uv_index'];
      final uv = (uvRaw as num?);
      final hourly = (w['hourly'] as List?) ?? const [];
      final forecast = (w['forecast'] as List?) ?? const [];

      return Container(
        decoration: PBTheme.ambient(),
        child: Padding(
          padding: const EdgeInsets.all(PBTheme.pagePad),
          child: !loaded
              ? _loadingState(state)
              : Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // ── LEFT: big current block ──────────────────────────────
                    Expanded(
                      flex: 5,
                      child: _currentBlock(
                        iconCode: icon,
                        temp: temp,
                        condition: condition,
                        feelsLike: feelsLike,
                        city: city,
                        humidity: humidity,
                        wind: wind,
                        uv: uv,
                      ),
                    ),
                    const SizedBox(width: PBTheme.pagePad),
                    // ── RIGHT: hourly + 3-day forecast ───────────────────────
                    Expanded(
                      flex: 6,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            flex: 5,
                            child: _hourlyBlock(hourly, icon),
                          ),
                          const SizedBox(height: PBTheme.pagePad),
                          Expanded(
                            flex: 4,
                            child: _forecastBlock(forecast),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
        ),
      );
    });
  }

  // ── Loading / empty placeholder ────────────────────────────────────────────
  Widget _loadingState(AppState state) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('🌤️', style: TextStyle(fontSize: 96)),
          const SizedBox(height: 24),
          Text(t('weather.loading'), style: PBTheme.h2.copyWith(color: PBTheme.textSecondary)),
          const SizedBox(height: 24),
          _refreshButton(state),
        ],
      ),
    );
  }

  Widget _refreshButton(AppState state) {
    return GestureDetector(
      onTap: () => state.send({'type': 'weather_refresh'}),
      child: Container(
        height: PBTheme.touchMin,
        padding: const EdgeInsets.symmetric(horizontal: 28),
        alignment: Alignment.center,
        decoration: PBTheme.accentButton,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.refresh, color: PBTheme.textPrimary, size: 26),
            const SizedBox(width: 12),
            Text(t('weather.refresh'), style: PBTheme.h3),
          ],
        ),
      ),
    );
  }

  // ── LEFT current block ──────────────────────────────────────────────────────
  Widget _currentBlock({
    required String iconCode,
    required String temp,
    required String condition,
    required String feelsLike,
    required String city,
    required String humidity,
    required String wind,
    required num? uv,
  }) {
    return Container(
      decoration: PBTheme.frosted(),
      padding: const EdgeInsets.all(36),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(city, style: PBTheme.label),
          const SizedBox(height: 8),
          // Emoji + huge temp on one line, using the width.
          Expanded(
            child: Center(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Flexible(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: WeatherIcon(icon: iconCode, condition: condition, size: 150),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(temp, style: PBTheme.display.copyWith(color: PBTheme.textPrimary)),
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text('°C', style: PBTheme.h1.copyWith(color: PBTheme.textSecondary)),
                          ),
                        ],
                      ),
                      Text(condition, style: PBTheme.h2),
                      if (feelsLike.isNotEmpty && feelsLike != temp) ...[
                        const SizedBox(height: 6),
                        Text(t('weather.feels_like') + ' ' + feelsLike + '°', style: PBTheme.bodyMuted),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          // Details row: humidity / wind / UV
          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: [
              _detailChip(Icons.water_drop_outlined, '$humidity%', t('weather.humidity'), PBTheme.cyan),
              _detailChip(Icons.air, '$wind km/h', t('weather.wind'), PBTheme.accentLight),
              if (uv != null) _uvChip(uv),
            ],
          ),
        ],
      ),
    );
  }

  Widget _detailChip(IconData icon, String value, String label, Color color) {
    return Container(
      constraints: const BoxConstraints(minHeight: PBTheme.touchMin),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: PBTheme.glass(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 28, color: color),
          const SizedBox(width: 14),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(value, style: PBTheme.h3),
              Text(label, style: PBTheme.caption.copyWith(color: PBTheme.textMuted)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _uvChip(num uv) {
    final color = _uvColor(uv);
    final uvText = uv == uv.roundToDouble() ? '${uv.toInt()}' : uv.toStringAsFixed(1);
    return Container(
      constraints: const BoxConstraints(minHeight: PBTheme.touchMin),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: PBTheme.glass(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: color.withAlpha(48),
              border: Border.all(color: color.withAlpha(160), width: 2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(uvText, style: PBTheme.h3.copyWith(color: color)),
          ),
          const SizedBox(width: 14),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('UV ' + _uvLabel(uv), style: PBTheme.h3.copyWith(color: color)),
              Text(t('weather.uv_index'), style: PBTheme.caption.copyWith(color: PBTheme.textMuted)),
            ],
          ),
        ],
      ),
    );
  }

  // ── RIGHT/TOP: hourly horizontal scroll (up to 8) ──────────────────────────
  Widget _hourlyBlock(List hourly, String currentIcon) {
    return Container(
      decoration: PBTheme.frosted(),
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('weather.next_hours'), style: PBTheme.label),
          const SizedBox(height: 16),
          Expanded(
            child: hourly.isEmpty
                ? Center(child: Text('--', style: PBTheme.h2.copyWith(color: PBTheme.textMuted)))
                : ListView.separated(
                    scrollDirection: Axis.horizontal,
                    physics: const BouncingScrollPhysics(),
                    itemCount: hourly.length > 8 ? 8 : hourly.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 14),
                    itemBuilder: (_, i) {
                      final h = hourly[i] as Map<String, dynamic>;
                      final hIcon = h['icon'] as String? ?? currentIcon;
                      final cond = (h['condition'] ?? h['description'] ?? '') as String;
                      final rainProb = (h['rain_prob'] as num?)?.round() ?? 0;
                      return Container(
                        width: 110,
                        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
                        decoration: PBTheme.glass(),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text('${h['hour'] ?? ''}', style: PBTheme.caption),
                            const SizedBox(height: 6),
                            WeatherIcon(icon: hIcon, condition: cond, size: 52),
                            const SizedBox(height: 6),
                            Text('${h['temp'] ?? '--'}°', style: PBTheme.h2),
                            if (rainProb >= 10) ...[
                              const SizedBox(height: 4),
                              Text('💧 $rainProb%',
                                  style: PBTheme.caption.copyWith(color: PBTheme.cyan)),
                            ],
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  // ── RIGHT/BOTTOM: 3-day forecast row ───────────────────────────────────────
  Widget _forecastBlock(List forecast) {
    return Container(
      decoration: PBTheme.frosted(),
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('weather.next_days'), style: PBTheme.label),
          const SizedBox(height: 16),
          Expanded(
            child: forecast.isEmpty
                ? Center(child: Text('--', style: PBTheme.h2.copyWith(color: PBTheme.textMuted)))
                : Row(
                    children: forecast.take(3).toList().asMap().entries.map<Widget>((e) {
                      final i = e.key;
                      final d = e.value as Map<String, dynamic>;
                      final dIcon = d['icon'] as String? ?? '';
                      final cond = (d['condition'] ?? d['description'] ?? '') as String;
                      return Expanded(
                        child: Padding(
                          padding: EdgeInsets.only(right: i < 2 ? 14 : 0),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
                            decoration: PBTheme.glass(),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(_dayName(d), style: PBTheme.h3.copyWith(color: PBTheme.accentLight)),
                                const SizedBox(height: 8),
                                WeatherIcon(icon: dIcon, condition: cond, size: 60),
                                const SizedBox(height: 8),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.baseline,
                                  textBaseline: TextBaseline.alphabetic,
                                  children: [
                                    Text('${d['high'] ?? '--'}°', style: PBTheme.h2),
                                    const SizedBox(width: 8),
                                    Text('${d['low'] ?? '--'}°',
                                        style: PBTheme.body.copyWith(color: PBTheme.textMuted)),
                                  ],
                                ),
                                if ((d['rain_prob'] as num?) != null && (d['rain_prob'] as num) >= 10) ...[
                                  const SizedBox(height: 6),
                                  Text('💧 ${(d['rain_prob'] as num).round()}%',
                                      style: PBTheme.caption.copyWith(color: PBTheme.cyan)),
                                ],
                              ],
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
          ),
        ],
      ),
    );
  }

  // French short day name. Prefer backend `day`; else derive from `dt`/`date`.
  String _dayName(Map<String, dynamic> d) {
    const fr = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
    final raw = (d['day'] ?? '').toString().trim();
    if (raw.isNotEmpty) {
      // If backend already sends a short FR name, keep it; otherwise map known forms.
      final lower = raw.toLowerCase();
      const map = {
        'monday': 'Lun', 'lundi': 'Lun', 'mon': 'Lun',
        'tuesday': 'Mar', 'mardi': 'Mar', 'tue': 'Mar',
        'wednesday': 'Mer', 'mercredi': 'Mer', 'wed': 'Mer',
        'thursday': 'Jeu', 'jeudi': 'Jeu', 'thu': 'Jeu',
        'friday': 'Ven', 'vendredi': 'Ven', 'fri': 'Ven',
        'saturday': 'Sam', 'samedi': 'Sam', 'sat': 'Sam',
        'sunday': 'Dim', 'dimanche': 'Dim', 'sun': 'Dim',
      };
      if (map.containsKey(lower)) return map[lower]!;
      // Already short (e.g. "Mar") or any custom string — show as-is, capped.
      return _capitalize(raw.length > 4 ? raw.substring(0, 3) : raw);
    }
    final dt = d['dt'];
    if (dt is num) {
      final date = DateTime.fromMillisecondsSinceEpoch(dt.toInt() * 1000);
      return fr[date.weekday % 7];
    }
    final dateStr = d['date'];
    if (dateStr is String) {
      final parsed = DateTime.tryParse(dateStr);
      if (parsed != null) return fr[parsed.weekday % 7];
    }
    return '--';
  }
}
