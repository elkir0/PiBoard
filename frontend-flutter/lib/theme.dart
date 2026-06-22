import 'package:flutter/material.dart';

/// PI-Board V3 — "Salon" design system, tuned for a 1920×1200 landscape screen
/// viewed from the couch (2-3 m). Rules:
///  - NO realtime BackdropFilter blur anywhere (kills the Pi 4 GPU at 1200p).
///    "Faux glass" = flat translucent fill + a frozen gradient + 1px border.
///  - Typography rebased BIG for distance: clock 220, titles 40, lists 18-22,
///    nothing below 15. Touch targets >= 64.
///  - Animations: transform/opacity only, and only when something is active.
class PBTheme {
  PBTheme._();

  // ── Core palette ─────────────────────────────────────────────────────────
  // Brand defaults (calm, dark, on-brand). `accent`/`bg` (+ their derived
  // shades) are NOT const : ils sont pilotés à chaud par la config
  // (`ui.accent_color`/`ui.bg_color`) via [applyConfig], pour permettre un
  // rebrand sans recompiler. Les valeurs par défaut ci-dessous reproduisent
  // EXACTEMENT l'apparence historique (zéro changement visuel par défaut).
  static const Color _accentDefault = Color(0xFF7C6FFF);
  static const Color _accentLightDefault = Color(0xFFA78BFA);
  static const Color _accentDimDefault = Color(0xFF4F46E5);
  static const Color _bgDefault = Color(0xFF060610);
  static const Color _bgElevatedDefault = Color(0xFF0C0C18);

  static Color bg = _bgDefault;
  static Color bgElevated = _bgElevatedDefault;
  static Color accent = _accentDefault;
  static Color accentLight = _accentLightDefault;
  static Color accentDim = _accentDimDefault;

  // Couleurs non thématiques (texte, états) — restent constantes.
  static const Color textPrimary = Color(0xFFF0F0F0);
  static const Color textSecondary = Color(0xFF9CA3AF);
  static const Color textMuted = Color(0xFF6B7280);
  static const Color surface = Color(0xFF0F0F1A);
  static const Color green = Color(0xFF34D399);
  static const Color red = Color(0xFFEF4444);
  static const Color orange = Color(0xFFF59E0B);
  static const Color cyan = Color(0xFF22D3EE);
  static const Color spotifyGreen = Color(0xFF1DB954);

  /// Incrémenté à chaque changement de thème. Le `MaterialApp` (main.dart)
  /// écoute ce notifier via un ValueListenableBuilder pour se reconstruire
  /// UNIQUEMENT quand le thème change (pas à chaque message WS).
  static final ValueNotifier<int> revision = ValueNotifier<int>(0);

  /// Applique les couleurs de la config (`ui.accent_color`/`ui.bg_color`).
  /// Hex invalide ou null = ignoré (on garde la couleur courante → zéro-crash).
  /// Les teintes dérivées (accentLight/Dim, bgElevated) sont recalculées en HSL
  /// quand l'utilisateur s'écarte du défaut ; au défaut elles restent IDENTIQUES.
  static void applyConfig({String? accentHex, String? bgHex}) {
    bool changed = false;
    final a = _parseHex(accentHex);
    if (a != null && a != accent) {
      accent = a;
      if (a == _accentDefault) {
        accentLight = _accentLightDefault;
        accentDim = _accentDimDefault;
      } else {
        final hsl = HSLColor.fromColor(a);
        accentLight = hsl.withLightness((hsl.lightness + 0.06).clamp(0.0, 1.0)).toColor();
        accentDim = hsl.withLightness((hsl.lightness - 0.14).clamp(0.0, 1.0)).toColor();
      }
      changed = true;
    }
    final b = _parseHex(bgHex);
    if (b != null && b != bg) {
      bg = b;
      bgElevated = (b == _bgDefault)
          ? _bgElevatedDefault
          : HSLColor.fromColor(b)
              .withLightness((HSLColor.fromColor(b).lightness + 0.03).clamp(0.0, 1.0))
              .toColor();
      changed = true;
    }
    if (changed) revision.value++;
  }

  /// Parse "#RRGGBB" / "RRGGBB" -> Color OPAQUE. null si invalide.
  /// Strictement 6 chiffres (même contrat que le validateur backend `_hex_color`) :
  /// on n'accepte PAS 8 chiffres, pour ne jamais rendre l'accent translucide via un
  /// hex AARRGGBB inattendu. Un hex invalide est ignoré (la couleur courante reste).
  static Color? _parseHex(String? hex) {
    if (hex == null) return null;
    var h = hex.trim();
    if (h.startsWith('#')) h = h.substring(1);
    if (h.length != 6) return null;
    final v = int.tryParse(h, radix: 16);
    return v == null ? null : Color(0xFF000000 | v);
  }

  // ── Layout constants ─────────────────────────────────────────────────────
  static const double railWidth = 132;       // left nav rail
  static const double voiceBandHeight = 92;   // full-width top band when active
  static const double touchMin = 64;          // minimum interactive target
  static const double pagePad = 32;           // page content padding
  static const double radius = 24;            // default card radius

  // ── Faux-glass (NO blur) ─────────────────────────────────────────────────
  /// Flat translucent card. `active` tints it with the accent.
  static BoxDecoration glass({bool active = false, double opacity = 0.05, double r = radius}) =>
      BoxDecoration(
        color: active ? accent.withAlpha(34) : Colors.white.withAlpha((opacity * 255).round()),
        border: Border.all(color: active ? accent.withAlpha(110) : Colors.white.withAlpha(20), width: 1),
        borderRadius: BorderRadius.circular(r),
      );

  // Backward-compat aliases used by ported pages.
  static BoxDecoration card({bool active = false}) => glass(active: active);
  static BoxDecoration glassCard({bool active = false}) => glass(active: active);

  /// Faux-glass with a FROZEN diagonal gradient (reads like frosted glass at 2 m,
  /// costs one normal draw — no BackdropFilter).
  static BoxDecoration frosted({bool active = false, double r = radius}) => BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: active
              ? [accent.withAlpha(54), accent.withAlpha(20)]
              : [Colors.white.withAlpha(16), Colors.white.withAlpha(6)],
        ),
        border: Border.all(color: active ? accent.withAlpha(120) : Colors.white.withAlpha(22), width: 1),
        borderRadius: BorderRadius.circular(r),
      );

  /// Static ambient backdrop for a page/HOME (replaces the animated radial glow).
  static BoxDecoration ambient({bool playing = false}) => BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(-0.5, -0.7),
          radius: 1.4,
          colors: [accent.withAlpha(playing ? 26 : 16), bg],
          stops: const [0.0, 0.7],
        ),
      );

  // Getter (et non champ) : recalculé avec l'accent COURANT après un rebrand.
  static BoxDecoration get accentButton => BoxDecoration(
        gradient: LinearGradient(colors: [accent.withAlpha(60), accentDim.withAlpha(48)]),
        border: Border.all(color: accent.withAlpha(90)),
        borderRadius: BorderRadius.circular(16),
      );

  /// Replacement for the old blur-based glassBox: a static frosted panel.
  /// `blur` kept in the signature for source-compat with ported pages but ignored.
  static Widget glassBox({
    required Widget child,
    bool active = false,
    double blur = 0,
    EdgeInsets padding = const EdgeInsets.all(16),
    double borderRadius = radius,
  }) =>
      Container(padding: padding, decoration: frosted(active: active, r: borderRadius), child: child);

  // ── Typography (rebased for 1200p @ 2-3 m) ──────────────────────────────
  static const TextStyle clock = TextStyle(
      fontSize: 220, fontWeight: FontWeight.w300, color: textPrimary, height: 1.0,
      letterSpacing: -4, fontFeatures: [FontFeature.tabularFigures()]);
  // Styles dépendant de l'accent = getters (couleur recalculée après rebrand).
  static TextStyle get display => TextStyle(
      fontSize: 88, fontWeight: FontWeight.w700, color: accent, height: 1.0,
      fontFeatures: const [FontFeature.tabularFigures()]);
  static const TextStyle h1 = TextStyle(fontSize: 40, fontWeight: FontWeight.w700, color: textPrimary, letterSpacing: -0.5);
  static const TextStyle h2 = TextStyle(fontSize: 28, fontWeight: FontWeight.w600, color: textPrimary);
  static const TextStyle h3 = TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: textPrimary);
  static const TextStyle body = TextStyle(fontSize: 20, fontWeight: FontWeight.w400, color: textPrimary);
  static const TextStyle bodyMuted = TextStyle(fontSize: 18, fontWeight: FontWeight.w400, color: textSecondary);
  static const TextStyle caption = TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: textSecondary);
  static TextStyle get label => TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: accent, letterSpacing: 2.5);
  static TextStyle get bigNumber => TextStyle(
      fontSize: 64, fontWeight: FontWeight.w700, color: accent,
      fontFeatures: const [FontFeature.tabularFigures()]);
}
