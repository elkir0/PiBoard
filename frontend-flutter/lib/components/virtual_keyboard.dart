import 'package:flutter/material.dart';
import '../theme.dart';

/// AZERTY on-screen keyboard for the Salon (1920×1200). Keys FILL the available
/// width (Expanded) with big touch targets (~68px) — finger-friendly from the
/// couch. Same public API as before (Music + YouTube reuse it).
class VirtualKeyboard extends StatefulWidget {
  final TextEditingController controller;
  final VoidCallback onSubmit;
  final VoidCallback onClose;
  final VoidCallback onChanged;

  const VirtualKeyboard({
    super.key,
    required this.controller,
    required this.onSubmit,
    required this.onClose,
    required this.onChanged,
  });

  @override
  State<VirtualKeyboard> createState() => _VirtualKeyboardState();
}

class _VirtualKeyboardState extends State<VirtualKeyboard> {
  static const _row1 = ['a', 'z', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'];
  static const _row2 = ['q', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm'];
  static const _row3 = ['w', 'x', 'c', 'v', 'b', 'n', "'"];

  static const double _keyH = 68;   // touch target
  static const double _gap = 7;

  bool _caps = false;

  void _type(String key) {
    widget.controller.text += _caps ? key.toUpperCase() : key;
    if (_caps) _caps = false;
    setState(() {});
    widget.onChanged();
  }

  void _backspace() {
    final t = widget.controller.text;
    if (t.isNotEmpty) {
      widget.controller.text = t.substring(0, t.length - 1);
      widget.onChanged();
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 12, 10, 14),
      decoration: BoxDecoration(
        color: PBTheme.bgElevated,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withAlpha(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _row(_row1.map(_letterKey).toList()),
          SizedBox(height: _gap),
          // Row 2 inset slightly (classic AZERTY offset) via half-key spacers.
          _row([const Spacer(flex: 5), ..._row2.map(_letterKey), const Spacer(flex: 5)]),
          SizedBox(height: _gap),
          _row([
            _specialKey(_caps ? Icons.keyboard_capslock_rounded : Icons.keyboard_arrow_up_rounded,
                () => setState(() => _caps = !_caps), active: _caps, flex: 16),
            ..._row3.map(_letterKey),
            _specialKey(Icons.backspace_rounded, _backspace, flex: 16),
          ]),
          SizedBox(height: _gap),
          _row([
            _textKey('Fermer', widget.onClose, color: PBTheme.textSecondary, flex: 18),
            _textKey('espace', () { widget.controller.text += ' '; if (_caps) _caps = false; setState(() {}); widget.onChanged(); }, flex: 54),
            _textKey('OK', widget.onSubmit, color: PBTheme.accent, accent: true, flex: 18),
          ]),
        ],
      ),
    );
  }

  Widget _row(List<Widget> children) => SizedBox(height: _keyH, child: Row(children: children));

  Widget _letterKey(String key) {
    final label = _caps ? key.toUpperCase() : key;
    return Expanded(
      flex: 10,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: _gap / 2),
        child: _KeyCap(
          onTap: () => _type(key),
          child: Text(label, style: const TextStyle(
              fontSize: 28, fontWeight: FontWeight.w500, color: PBTheme.textPrimary)),
        ),
      ),
    );
  }

  Widget _specialKey(IconData icon, VoidCallback onTap, {bool active = false, int flex = 16}) {
    return Expanded(
      flex: flex,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: _gap / 2),
        child: _KeyCap(
          onTap: onTap,
          active: active,
          child: Icon(icon, size: 28, color: active ? PBTheme.accent : PBTheme.textSecondary),
        ),
      ),
    );
  }

  Widget _textKey(String label, VoidCallback onTap, {Color? color, bool accent = false, int flex = 20}) {
    return Expanded(
      flex: flex,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: _gap / 2),
        child: _KeyCap(
          onTap: onTap,
          active: accent,
          child: Text(label, style: TextStyle(
              fontSize: 20, fontWeight: FontWeight.w600, color: color ?? PBTheme.textPrimary)),
        ),
      ),
    );
  }
}

/// A single key cap with a press highlight (opacity/transform only — GPU-cheap).
class _KeyCap extends StatefulWidget {
  final Widget child;
  final VoidCallback onTap;
  final bool active;
  const _KeyCap({required this.child, required this.onTap, this.active = false});
  @override
  State<_KeyCap> createState() => _KeyCapState();
}

class _KeyCapState extends State<_KeyCap> {
  bool _down = false;
  @override
  Widget build(BuildContext context) {
    final base = widget.active ? PBTheme.accent.withAlpha(46) : Colors.white.withAlpha(14);
    return GestureDetector(
      onTapDown: (_) => setState(() => _down = true),
      onTapUp: (_) => setState(() => _down = false),
      onTapCancel: () => setState(() => _down = false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _down ? 0.94 : 1.0,
        duration: const Duration(milliseconds: 70),
        child: Container(
          decoration: BoxDecoration(
            color: _down ? PBTheme.accent.withAlpha(70) : base,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withAlpha(_down ? 60 : 20)),
          ),
          alignment: Alignment.center,
          child: widget.child,
        ),
      ),
    );
  }
}
