import 'dart:math';
import 'package:flutter/material.dart';

/// Animated weather background — draws clouds, rain, sun, moon, stars based on weather condition
class WeatherBackground extends StatefulWidget {
  final String icon; // OpenWeather icon code (01d, 02n, 09d, 10n, 11d, 13d, 50d)
  const WeatherBackground({super.key, required this.icon});

  @override
  State<WeatherBackground> createState() => _WeatherBackgroundState();
}

class _WeatherBackgroundState extends State<WeatherBackground> with TickerProviderStateMixin {
  late AnimationController _ctrl;
  late List<_Particle> _particles;
  final _rng = Random();

  // Lightning flash state (driven by elapsed time, not per-frame rng — see _onTick)
  double _flashIntensity = 0.0; // current flash alpha factor 0..1
  double _nextFlashAt = 0.0;    // next scheduled flash time (controller seconds)
  Duration _lastElapsed = Duration.zero;

  bool get _isNight => widget.icon.endsWith('n');
  String get _condition {
    if (widget.icon.isEmpty) return 'cloud';
    final code = widget.icon.substring(0, min(2, widget.icon.length));
    switch (code) {
      case '01': return 'clear';
      case '02': return 'fewclouds';
      case '03': case '04': return 'clouds';
      case '09': case '10': return 'rain';
      case '11': return 'storm';
      case '13': return 'snow';
      case '50': return 'mist';
      default: return 'clouds';
    }
  }

  // Only 'clear' is fully static (no drifting clouds / no particles) → no animation needed.
  bool get _needsAnimation => _condition != 'clear';

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(seconds: 1));
    _ctrl.addListener(_onTick);
    _particles = List.generate(40, (_) => _Particle.random(_rng));
    _nextFlashAt = 4.0 + _rng.nextDouble() * 8.0; // first flash in 4..12s
    if (_needsAnimation) _ctrl.repeat();
  }

  @override
  void didUpdateWidget(WeatherBackground old) {
    super.didUpdateWidget(old);
    // Re-evaluate whether the controller should run when the icon (condition) changes.
    if (_needsAnimation && !_ctrl.isAnimating) {
      _ctrl.repeat();
    } else if (!_needsAnimation && _ctrl.isAnimating) {
      _ctrl.stop();
    }
  }

  // Single source of per-frame mutation: advance particles (dt-scaled) + lightning timing.
  // Keeps the CustomPainter pure (read-only view of state).
  void _onTick() {
    final elapsed = _ctrl.lastElapsedDuration ?? Duration.zero;
    double dt = (elapsed - _lastElapsed).inMicroseconds / 1e6;
    _lastElapsed = elapsed;
    if (dt < 0 || dt > 0.25) dt = 0.016; // clamp on first tick / hiccups

    final cond = _condition;

    // Advance falling particles here (not in paint) so paint() stays pure.
    if (cond == 'rain' || cond == 'storm') {
      for (final p in _particles) {
        p.y += p.speed * 1.2 * dt;
        if (p.y > 1) { p.y = 0; p.x = _rng.nextDouble(); }
      }
    } else if (cond == 'snow') {
      for (final p in _particles) {
        p.y += p.speed * 0.3 * dt;
        p.x += sin(_ctrl.value * 2 * pi + p.speed * 10) * 0.06 * dt;
        if (p.y > 1) { p.y = 0; p.x = _rng.nextDouble(); }
      }
    }

    // Lightning: schedule occasional flashes by elapsed time (storm only).
    if (cond == 'storm') {
      final t = elapsed.inMicroseconds / 1e6;
      if (_flashIntensity > 0) {
        _flashIntensity = max(0.0, _flashIntensity - dt * 4.0); // fade over ~0.25s
      }
      if (t >= _nextFlashAt) {
        _flashIntensity = 1.0;
        _nextFlashAt = t + 4.0 + _rng.nextDouble() * 8.0; // next in 4..12s
      }
    } else if (_flashIntensity > 0) {
      _flashIntensity = 0.0;
    }

    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _ctrl.removeListener(_onTick);
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.infinite,
      painter: _WeatherPainter(
        condition: _condition,
        isNight: _isNight,
        time: _ctrl.value,
        particles: _particles,
        flashIntensity: _flashIntensity,
      ),
    );
  }
}

class _Particle {
  double x, y, speed, size, opacity;
  _Particle(this.x, this.y, this.speed, this.size, this.opacity);

  static _Particle random(Random rng) => _Particle(
    rng.nextDouble(),
    rng.nextDouble(),
    0.2 + rng.nextDouble() * 0.8,
    1 + rng.nextDouble() * 3,
    0.2 + rng.nextDouble() * 0.6,
  );
}

class _WeatherPainter extends CustomPainter {
  final String condition;
  final bool isNight;
  final double time;
  // Read-only view: paint() only reads particle positions, never mutates them.
  final List<_Particle> particles;
  final double flashIntensity;

  _WeatherPainter({required this.condition, required this.isNight, required this.time, required this.particles, required this.flashIntensity});

  @override
  void paint(Canvas canvas, Size size) {
    // Sky gradient
    final skyColors = isNight
        ? [const Color(0xFF0A1030), const Color(0xFF151845)]
        : condition == 'clear'
            ? [const Color(0xFF1A3A8A), const Color(0xFF2952CC)]
            : condition == 'rain' || condition == 'storm'
                ? [const Color(0xFF15182E), const Color(0xFF252840)]
                : [const Color(0xFF162050), const Color(0xFF1E2E6A)];

    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: skyColors,
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height)),
    );

    // Stars at night
    if (isNight) _drawStars(canvas, size);

    // Sun or Moon
    if (condition == 'clear' || condition == 'fewclouds') {
      if (isNight) {
        _drawMoon(canvas, size);
      } else {
        _drawSun(canvas, size);
      }
    }

    // Clouds
    if (condition != 'clear') {
      _drawClouds(canvas, size);
    }

    // Rain
    if (condition == 'rain' || condition == 'storm') {
      _drawRain(canvas, size);
    }

    // Snow
    if (condition == 'snow') {
      _drawSnow(canvas, size);
    }

    // Mist
    if (condition == 'mist') {
      _drawMist(canvas, size);
    }

    // Lightning flash (intensity computed in State, faded over a few frames — no per-frame rng)
    if (flashIntensity > 0) {
      canvas.drawRect(
        Rect.fromLTWH(0, 0, size.width, size.height),
        Paint()..color = Colors.white.withAlpha((40 * flashIntensity).toInt()),
      );
    }
  }

  void _drawStars(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white;
    for (int i = 0; i < 25; i++) {
      final x = (i * 137.5 + 50) % size.width;
      final y = (i * 97.3 + 20) % (size.height * 0.6);
      final twinkle = (sin(time * 2 * pi + i * 0.7) + 1) / 2;
      paint.color = Colors.white.withAlpha((60 + twinkle * 120).toInt());
      canvas.drawCircle(Offset(x, y), 1.2 + twinkle * 0.8, paint);
    }
  }

  void _drawSun(Canvas canvas, Size size) {
    final cx = size.width * 0.18;
    final cy = size.height * 0.25;

    // Faux-glow = stacked solid translucent circles (no MaskFilter.blur — GPU blur banned on Pi4)
    canvas.drawCircle(Offset(cx, cy), 50, Paint()..color = const Color(0xFFFFD54F).withAlpha(12));
    canvas.drawCircle(Offset(cx, cy), 38, Paint()..color = const Color(0xFFFFD54F).withAlpha(22));
    canvas.drawCircle(Offset(cx, cy), 26, Paint()..color = const Color(0xFFFFD54F).withAlpha(45));
    // Core
    canvas.drawCircle(Offset(cx, cy), 16, Paint()..color = const Color(0xFFFFD54F).withAlpha(120));
  }

  void _drawMoon(Canvas canvas, Size size) {
    final cx = size.width * 0.18;
    final cy = size.height * 0.22;

    // Faux-glow = stacked solid translucent circles (no MaskFilter.blur)
    canvas.drawCircle(Offset(cx, cy), 35, Paint()..color = const Color(0xFFE0E0E0).withAlpha(12));
    canvas.drawCircle(Offset(cx, cy), 24, Paint()..color = const Color(0xFFE0E0E0).withAlpha(22));
    // Moon
    canvas.drawCircle(Offset(cx, cy), 15, Paint()..color = const Color(0xFFE0E0E0).withAlpha(80));
    // Dark side (crescent)
    canvas.drawCircle(Offset(cx + 5, cy - 2), 12, Paint()..color = const Color(0xFF0A0A2E));
  }

  void _drawClouds(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white.withAlpha(isNight ? 15 : 25);
    final drift = time * size.width * 0.3;

    for (int i = 0; i < 4; i++) {
      final x = ((i * 220 + drift) % (size.width + 200)) - 100;
      final y = 30.0 + i * 35 + sin(i * 1.5) * 20;
      final w = 120.0 + i * 30;
      final h = 30.0 + i * 8;
      // Flat fill (no MaskFilter.blur); soft edge approximated by the rounded radius.
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x, y), width: w, height: h), Radius.circular(h / 2)),
        paint,
      );
    }
  }

  void _drawRain(Canvas canvas, Size size) {
    final paint = Paint()..strokeWidth = 1.2..strokeCap = StrokeCap.round;

    // Read-only: positions are advanced by the State's _onTick, never here.
    for (final p in particles) {
      final x = p.x * size.width;
      final y = p.y * size.height;
      paint.color = const Color(0xFF64B5F6).withAlpha((p.opacity * 150).toInt());
      canvas.drawLine(Offset(x, y), Offset(x - 2, y + p.size * 4), paint);
    }
  }

  void _drawSnow(Canvas canvas, Size size) {
    final paint = Paint();
    // Read-only: positions are advanced by the State's _onTick, never here.
    for (final p in particles) {
      paint.color = Colors.white.withAlpha((p.opacity * 120).toInt());
      canvas.drawCircle(Offset(p.x * size.width, p.y * size.height), p.size * 0.8, paint);
    }
  }

  void _drawMist(Canvas canvas, Size size) {
    final paint = Paint();
    for (int i = 0; i < 5; i++) {
      final x = ((i * 180 + time * size.width * 0.2) % (size.width + 300)) - 150;
      final y = size.height * (0.3 + i * 0.12);
      // Flat fill (no MaskFilter.blur); stacked translucent bands for a soft look.
      paint.color = Colors.white.withAlpha(6);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x, y), width: 250, height: 40), const Radius.circular(20)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WeatherPainter old) =>
      time != old.time ||
      condition != old.condition ||
      isNight != old.isNight ||
      flashIntensity != old.flashIntensity;
}
