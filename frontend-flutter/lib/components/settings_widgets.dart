import 'package:flutter/material.dart';
import '../theme.dart';

/// Widgets réutilisables pour la page Paramètres (style "Salon", grandes cibles).

/// Section : un libellé en capitales accent + une carte glass contenant les réglages.
class SettingsSection extends StatelessWidget {
  final String title;
  final List<Widget> children;
  const SettingsSection({super.key, required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: PBTheme.label),
          const SizedBox(height: 12),
          PBTheme.glassBox(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ],
      ),
    );
  }
}

/// Ligne réglage : titre (+ sous-titre) à gauche, contrôle à droite ou dessous.
class SettingRow extends StatelessWidget {
  final String label;
  final String? sub;
  final Widget control;
  final bool stacked; // contrôle sous le label (sliders, chips larges)
  const SettingRow({
    super.key,
    required this.label,
    this.sub,
    required this.control,
    this.stacked = false,
  });

  @override
  Widget build(BuildContext context) {
    final head = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: PBTheme.h3),
        if (sub != null) ...[
          const SizedBox(height: 2),
          Text(sub!, style: PBTheme.caption),
        ],
      ],
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: stacked
          ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              head,
              const SizedBox(height: 12),
              control,
            ])
          : Row(children: [
              Expanded(child: head),
              const SizedBox(width: 16),
              control,
            ]),
    );
  }
}

/// Sélecteur en pastilles (un choix parmi N).
class ChipSelector extends StatelessWidget {
  final String value;
  final List<(String, String)> options; // (valeur, libellé)
  final ValueChanged<String> onSelect;
  const ChipSelector({
    super.key,
    required this.value,
    required this.options,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final o in options)
          GestureDetector(
            // Re-taper la pastille déjà active = no-op (sinon un configSet(restart)
            // inutile lèverait la bannière « redémarrage requis » sans rien changer).
            onTap: () { if (o.$1 != value) onSelect(o.$1); },
            child: Container(
              constraints: const BoxConstraints(minHeight: PBTheme.touchMin),
              alignment: Alignment.center,
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
              decoration: PBTheme.frosted(active: o.$1 == value, r: 16),
              child: Text(
                o.$2,
                style: PBTheme.body.copyWith(
                  color: o.$1 == value ? PBTheme.accentLight : PBTheme.textSecondary,
                  fontWeight: o.$1 == value ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Slider thémé avec valeur affichée.
class LabeledSlider extends StatelessWidget {
  final double value;
  final double min;
  final double max;
  final int? divisions;
  final String valueLabel;
  final ValueChanged<double> onChanged;
  final ValueChanged<double>? onChangeEnd;
  const LabeledSlider({
    super.key,
    required this.value,
    required this.min,
    required this.max,
    required this.valueLabel,
    required this.onChanged,
    this.divisions,
    this.onChangeEnd,
  });

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(
        child: SliderTheme(
          data: SliderTheme.of(context).copyWith(
            trackHeight: 8,
            activeTrackColor: PBTheme.accent,
            inactiveTrackColor: Colors.white.withAlpha(28),
            thumbColor: PBTheme.accentLight,
            overlayColor: PBTheme.accent.withAlpha(40),
            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 14),
            overlayShape: const RoundSliderOverlayShape(overlayRadius: 26),
          ),
          child: Slider(
            value: value.clamp(min, max),
            min: min,
            max: max,
            divisions: divisions,
            onChanged: onChanged,
            onChangeEnd: onChangeEnd,
          ),
        ),
      ),
      const SizedBox(width: 12),
      SizedBox(
        width: 64,
        child: Text(valueLabel,
            textAlign: TextAlign.right,
            style: PBTheme.h3.copyWith(color: PBTheme.accentLight)),
      ),
    ]);
  }
}

/// Bouton d'action avec confirmation optionnelle (tap -> "Confirmer ?" -> action).
class ActionButton extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color color;
  final bool confirm;
  final VoidCallback onTap;
  const ActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    this.confirm = false,
  });

  @override
  State<ActionButton> createState() => _ActionButtonState();
}

class _ActionButtonState extends State<ActionButton> {
  bool _armed = false;

  @override
  Widget build(BuildContext context) {
    final showConfirm = widget.confirm && _armed;
    return GestureDetector(
      onTap: () {
        if (widget.confirm && !_armed) {
          setState(() => _armed = true);
          Future.delayed(const Duration(seconds: 4), () {
            if (mounted) setState(() => _armed = false);
          });
        } else {
          setState(() => _armed = false);
          widget.onTap();
        }
      },
      child: Container(
        height: PBTheme.touchMin + 8,
        decoration: PBTheme.frosted(active: showConfirm, r: 16),
        alignment: Alignment.center,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(widget.icon, size: 26, color: showConfirm ? PBTheme.red : widget.color),
            const SizedBox(width: 12),
            Text(showConfirm ? 'Confirmer ?' : widget.label,
                style: PBTheme.h3.copyWith(
                    color: showConfirm ? PBTheme.red : PBTheme.textPrimary)),
          ],
        ),
      ),
    );
  }
}
