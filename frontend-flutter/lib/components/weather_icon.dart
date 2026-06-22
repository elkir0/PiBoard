import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// Icône météo Meteocons (SVG colorées, MIT). Le backend émet un code style
/// OpenWeather (ex "01d", "10n") ; on le mappe vers un slug Meteocons présent
/// dans assets/icons/weather/. Repli emoji si l'asset tarde/manque
/// (placeholderBuilder) ou code inconnu (-> not-available).

String meteoconSlug(String icon) {
  final n = icon.endsWith('n');
  final code = icon.length >= 2 ? icon.substring(0, 2) : icon;
  switch (code) {
    case '01':
      return n ? 'clear-night' : 'clear-day';
    case '02':
      return n ? 'partly-cloudy-night' : 'partly-cloudy-day';
    case '03':
      return n ? 'partly-cloudy-night' : 'partly-cloudy-day';
    case '04':
      return n ? 'overcast-night' : 'overcast-day';
    case '09':
      return n ? 'partly-cloudy-night-drizzle' : 'partly-cloudy-day-drizzle';
    case '10':
      return n ? 'partly-cloudy-night-rain' : 'partly-cloudy-day-rain';
    case '11':
      return n ? 'thunderstorms-night' : 'thunderstorms-day';
    case '13':
      return n ? 'partly-cloudy-night-snow' : 'partly-cloudy-day-snow';
    case '50':
      return n ? 'fog-night' : 'fog-day';
  }
  return 'not-available';
}

/// Repli emoji (depuis le code icône OU le texte de condition).
String weatherEmoji(String icon, String condition) {
  final night = icon.endsWith('n');
  final code = icon.isNotEmpty ? icon.substring(0, icon.length >= 2 ? 2 : 1) : '';
  switch (code) {
    case '01':
      return night ? '🌙' : '☀️';
    case '02':
      return night ? '☁️' : '🌤️';
    case '03':
    case '04':
      return '☁️';
    case '09':
      return '🌧️';
    case '10':
      return night ? '🌧️' : '🌦️';
    case '11':
      return '⛈️';
    case '13':
      return '❄️';
    case '50':
      return '🌫️';
  }
  final c = condition.toLowerCase();
  if (c.contains('orage') || c.contains('storm') || c.contains('thunder')) return '⛈️';
  if (c.contains('neige') || c.contains('snow')) return '❄️';
  if (c.contains('pluie') || c.contains('rain') || c.contains('averse')) return '🌧️';
  if (c.contains('bruine') || c.contains('drizzle')) return '🌦️';
  if (c.contains('brume') || c.contains('brouillard') || c.contains('mist') || c.contains('fog')) return '🌫️';
  if (c.contains('nuage') || c.contains('couvert') || c.contains('cloud')) return '☁️';
  if (c.contains('dégagé') || c.contains('clair') || c.contains('clear') || c.contains('ensoleillé')) {
    return night ? '🌙' : '☀️';
  }
  return '🌤️';
}

/// Icône météo dimensionnée. SVG Meteocons natives (déjà colorées : pas de
/// colorFilter, ça les aplatirait), repli emoji.
class WeatherIcon extends StatelessWidget {
  final String icon;       // code style OpenWeather du backend (ex "10d")
  final String condition;  // texte de condition (repli)
  final double size;
  const WeatherIcon({
    super.key,
    required this.icon,
    required this.condition,
    required this.size,
  });

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      'assets/icons/weather/${meteoconSlug(icon)}.svg',
      width: size,
      height: size,
      placeholderBuilder: (_) => SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Text(weatherEmoji(icon, condition),
              style: TextStyle(fontSize: size * 0.82)),
        ),
      ),
    );
  }
}
