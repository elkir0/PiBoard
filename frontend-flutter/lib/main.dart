import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart' show kIsWeb, defaultTargetPlatform, TargetPlatform;
import 'package:provider/provider.dart';
import 'package:flutterpi_gstreamer_video_player/flutterpi_gstreamer_video_player.dart';
import 'stores/app_state.dart';
import 'theme.dart';
import 'app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Use flutter-pi's native gstreamer backend for video_player (HW-decoded video
  // inside the Flutter UI). Only on the device — on web/desktop preview keep the
  // default platform impl so screenshots still work.
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.linux) {
    FlutterpiVideoPlayer.registerWith();
  }
  // Lock to landscape for 1280x720 Pi screen
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);
  // Hide system UI (fullscreen kiosk)
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(),
      // Le MaterialApp se reconstruit UNIQUEMENT quand le thème change
      // (PBTheme.revision), pas à chaque message WS — pour que
      // scaffoldBackgroundColor / colorScheme suivent un rebrand à chaud.
      child: ValueListenableBuilder<int>(
        valueListenable: PBTheme.revision,
        builder: (_, __, ___) => MaterialApp(
          title: 'PI-Board V2',
          debugShowCheckedModeBanner: false,
          theme: ThemeData.dark().copyWith(
            scaffoldBackgroundColor: PBTheme.bg,
            colorScheme: ColorScheme.dark(primary: PBTheme.accent),
          ),
          home: const _DesignSizeScaler(child: PiBoardApp()),
        ),
      ),
    ),
  );
}

/// Indépendance de résolution. L'UI « Salon » est dessinée pour **1920×1200
/// paysage** (typo, rail, espacements calés sur cette taille). Plutôt que de
/// reflower chaque page, on rend TOUJOURS à cette taille de référence puis on met
/// l'ensemble à l'échelle proportionnellement (sans déformation) pour remplir
/// n'importe quel écran. Les éventuelles bandes (ratio différent du 16:10) sont
/// peintes au fond du thème → quasi invisibles. `MediaQuery` est forcé à la taille
/// de référence pour que tout code lisant la taille reste cohérent.
///
/// Sur le device natif 1920×1200 : échelle **1.0** → rendu identique au pixel
/// (zéro changement / zéro risque). Permet d'autres résolutions paysage (720p,
/// 900p, 1440p…) sans recompiler la mise en page. (Reflow portrait = à venir.)
class _DesignSizeScaler extends StatelessWidget {
  final Widget child;
  const _DesignSizeScaler({required this.child});

  static const Size _design = Size(1920, 1200);

  @override
  Widget build(BuildContext context) {
    return Container(
      color: PBTheme.bg,
      alignment: Alignment.center,
      child: FittedBox(
        fit: BoxFit.contain,
        child: SizedBox.fromSize(
          size: _design,
          child: MediaQuery(
            data: MediaQuery.of(context).copyWith(size: _design),
            child: child,
          ),
        ),
      ),
    );
  }
}
