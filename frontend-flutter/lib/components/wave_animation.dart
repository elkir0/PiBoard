import 'dart:math';
import 'package:flutter/material.dart';
import '../theme.dart';

/// Animated wave bars for voice feedback
class WaveAnimation extends StatefulWidget {
  final String state; // LISTENING, PROCESSING, SPEAKING
  const WaveAnimation({super.key, required this.state});

  @override
  State<WaveAnimation> createState() => _WaveAnimationState();
}

class _WaveAnimationState extends State<WaveAnimation> with TickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isProcessing = widget.state == 'PROCESSING';
    final color = widget.state == 'SPEAKING' ? PBTheme.accentLight : PBTheme.accent;

    return AnimatedBuilder(
      animation: _controller,
      builder: (_, __) => Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(5, (i) {
          final phase = (i / 5) * pi;
          final t = sin(_controller.value * pi + phase);
          final height = isProcessing ? 4.0 : 4.0 + t.abs() * 14.0;
          return Container(
            margin: const EdgeInsets.symmetric(horizontal: 1.5),
            width: 3,
            height: height,
            decoration: BoxDecoration(
              color: color.withAlpha((150 + (t.abs() * 105).toInt()).clamp(0, 255)),
              borderRadius: BorderRadius.circular(2),
            ),
          );
        }),
      ),
    );
  }
}
