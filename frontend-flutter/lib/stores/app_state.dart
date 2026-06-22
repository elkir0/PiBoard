import 'dart:async';
import 'package:flutter/material.dart';
import '../services/ws_service.dart';
import '../i18n.dart';
import '../theme.dart';

/// Global application state — mirrors V1 Svelte store exactly
class AppState extends ChangeNotifier {
  final WSService _ws = WSService();
  late StreamSubscription _msgSub;
  late StreamSubscription _connSub;

  // true une fois dispose() appelé : garde-fou pour les Future.delayed non
  // annulables qui notifient après coup (sinon notifyListeners() lève au teardown).
  bool _disposed = false;

  // Connection
  bool wsConnected = false;

  // Navigation — 6 domain pages (0..5) keep their backend indices; "Accueil"
  // (HOME bento) is a UI-only 7th destination, so the backend page contract is
  // unchanged. onHome=true shows the bento; any domain nav clears it.
  int currentPage = 0;
  bool onHome = true;
  final PageController pageController = PageController();

  // Assistant
  String assistantState = 'IDLE';
  String transcript = '';
  String speakingText = '';

  // Music
  Map<String, dynamic> musicData = {'playing': false};
  List<Map<String, dynamic>> musicQueue = [];
  int volumeLevel = 50;
  String spotifyStatus = 'loading';
  String? spotifyReauthUrl;

  // Music progress interpolation
  Timer? _progressTimer;
  int _lastProgressMs = 0;
  DateTime _lastProgressTime = DateTime.now();
  bool _isPlaying = false;

  // Weather
  Map<String, dynamic> weatherData = {};

  // Cameras
  List<Map<String, dynamic>> cameras = [];
  Map<String, dynamic>? fullscreenCam;

  // Devialet
  Map<String, dynamic> devialetData = {};
  bool devialetRestarting = false;

  // Domotique
  Map<String, dynamic> domotiqueData = {};

  // YouTube
  List<Map<String, dynamic>> youtubeResults = [];
  Map<String, dynamic>? youtubeNowPlaying;
  String youtubeError = '';
  bool youtubeSearching = false;
  String? youtubePlayUrl;   // direct stream URL -> played in-widget (flutter-pi gstreamer)

  // Settings — page PLEINE (onSettings) rendue dans la zone de contenu, à côté
  // du rail (plus d'overlay drawer 760px). Se quitte via n'importe quel item du rail.
  bool onSettings = false;
  bool keyboardVisible = false;
  String audioSinksDefault = '';
  List<Map<String, dynamic>> audioSinks = [];
  String? connectingSink; // sink BT en cours de connexion depuis « Sortie »

  // Bluetooth (enceintes)
  List<Map<String, dynamic>> btDevices = [];
  bool btScanning = false;
  bool btAvailable = true;
  String? btActionError;
  final Set<String> btBusy = {}; // MAC dont une action est en cours (anti double-tap)

  // Config hub
  Map<String, dynamic> config = {};
  Map<String, dynamic>? systemInfo;
  final Set<String> pendingRestart = {}; // clés modifiées nécessitant un redémarrage

  /// Lecture sûre d'une valeur de config (section.key) avec valeur par défaut.
  dynamic cfg(String section, String key, [dynamic fallback]) {
    final s = config[section];
    if (s is Map && s[key] != null) return s[key];
    return fallback;
  }

  AppState() {
    _connSub = _ws.connectionStream.listen((connected) {
      wsConnected = connected;
      if (connected) {
        _ws.send({'type': 'weather_refresh'});
        _ws.send({'type': 'domotique_status'});
        _ws.send({'type': 'devialet_status'});
        _ws.send({'type': 'cameras_list'});
        _ws.send({'type': 'cameras_snapshots'});
      }
      notifyListeners();
    });

    _msgSub = _ws.messages.listen(_handleMessage);
    _ws.connect();

    // Progress interpolation timer (updates every 500ms when playing)
    _progressTimer = Timer.periodic(const Duration(milliseconds: 500), (_) {
      if (_isPlaying) {
        final elapsed = DateTime.now().difference(_lastProgressTime).inMilliseconds;
        // Clamp à la durée pour éviter un dépassement (label écoulé > durée,
        // restant négatif) entre deux pushs backend (~2 s).
        final raw = _lastProgressMs + elapsed;
        final dur = (musicData['duration_ms'] as num?)?.toInt();
        musicData = {
          ...musicData,
          'progress_ms': dur != null && dur > 0 ? raw.clamp(0, dur) : raw,
        };
        notifyListeners();
      }
    });
  }

  void _handleMessage(Map<String, dynamic> msg) {
    final type = msg['type'] as String?;
    final data = msg['data'];

    switch (type) {
      case 'state':
        assistantState = '$data';
        if (assistantState == 'IDLE' || assistantState == 'null') {
          assistantState = 'IDLE';
          transcript = '';
          speakingText = '';
        }

      case 'page':
        final p = data is int ? data : int.tryParse('$data') ?? 0;
        goToPage(p);

      case 'transcript':
        // V1: msg.data.text (object) or string
        if (data is Map) {
          transcript = '${data['text'] ?? ''}';
        } else {
          transcript = '$data';
        }

      case 'speaking':
        speakingText = '$data';

      case 'music':
        if (data is Map<String, dynamic>) {
          musicData = data;
          _isPlaying = data['playing'] == true;
          _lastProgressMs = (data['progress_ms'] as num?)?.toInt() ?? 0;
          _lastProgressTime = DateTime.now();
        }

      case 'music_progress':
        if (data is Map<String, dynamic>) {
          musicData = {...musicData, ...data};
          _isPlaying = musicData['playing'] == true;
          _lastProgressMs = (data['progress_ms'] as num?)?.toInt() ?? _lastProgressMs;
          _lastProgressTime = DateTime.now();
        }

      case 'music_queue':
        if (data is List) musicQueue = List<Map<String, dynamic>>.from(data);

      case 'volume':
        // Message canonique unique : on aligne les DEUX vues (page Musique =
        // volumeLevel ; page Devialet = devialetData['volume']).
        volumeLevel = data is int ? data : int.tryParse('$data') ?? volumeLevel;
        devialetData = {...devialetData, 'volume': volumeLevel};

      case 'spotify_status':
        spotifyStatus = '$data';
        if (spotifyStatus == 'ok') spotifyReauthUrl = null;
        // Auto-request auth URL when auth required
        if (spotifyStatus == 'auth_required') {
          _ws.send({'type': 'spotify_reauth'});
        }

      case 'spotify_reauth_url':
        spotifyReauthUrl = '$data';

      case 'spotify_auth_qr':
        // Legacy — use reauth_url instead

      case 'weather':
        if (data is Map<String, dynamic>) weatherData = data;

      case 'cameras_list' || 'cameras_snapshots':
        if (data is List) {
          cameras = List<Map<String, dynamic>>.from(data);
          // Tient l'overlay plein ecran a jour sur le rafraichissement groupe
          // (sinon il fige sur un snapshot perime). Garde si l'id disparait.
          if (fullscreenCam != null) {
            final id = fullscreenCam!['id'];
            final fresh = cameras.where((c) => c['id'] == id);
            if (fresh.isNotEmpty) fullscreenCam = fresh.first;
          }
        }

      case 'camera_snapshot':
        if (data is Map<String, dynamic>) {
          final id = data['id'];
          cameras = cameras.map((c) =>
            c['id'] == id ? {...c, 'snapshot': data['snapshot']} : c
          ).toList();
          if (fullscreenCam != null && fullscreenCam!['id'] == id) {
            fullscreenCam = {...fullscreenCam!, 'snapshot': data['snapshot']};
          }
        }

      case 'devialet_restarting':
        devialetRestarting = data == true;

      case 'devialet_status':
        if (data is Map<String, dynamic>) {
          devialetData = data;
          // Synchronise la page Musique avec le volume Devialet.
          final v = data['volume'];
          if (v is int) volumeLevel = v;
          else if (v != null) volumeLevel = int.tryParse('$v') ?? volumeLevel;
        }

      case 'domotique_status':
        if (data is Map<String, dynamic>) domotiqueData = data;

      case 'youtube_results':
        if (data is List) {
          youtubeResults = List<Map<String, dynamic>>.from(data);
          youtubeSearching = false;
        }

      case 'youtube_play_url':
        // Backend resolved a direct stream URL -> play it in-widget.
        if (data is Map<String, dynamic>) {
          youtubePlayUrl = '${data['url'] ?? ''}';
          youtubeNowPlaying = data;
          youtubeError = '';
        }

      case 'youtube_stopped':
        youtubeNowPlaying = null;
        youtubePlayUrl = null;
        if (data is Map && data['error'] != null) {
          youtubeError = '${data['error']}';
          Future.delayed(const Duration(seconds: 4), () {
            if (_disposed) return;
            youtubeError = '';
            notifyListeners();
          });
        }

      case 'config':
        if (data is Map<String, dynamic>) {
          config = data;
          final ui = data['ui'] as Map?;
          // Langue de l'UI pilotée par le backend (config.ui.locale).
          final loc = ui?['locale'];
          if (loc is String) setAppLocale(loc);
          // Thème (accent/fond) piloté par la config — rebrand sans recompiler.
          PBTheme.applyConfig(
            accentHex: ui?['accent_color'] as String?,
            bgHex: ui?['bg_color'] as String?,
          );
        }

      case 'system_info':
        if (data is Map<String, dynamic>) systemInfo = data;

      case 'screen_brightness':
        config = {
          ...config,
          'screen': {...(config['screen'] as Map? ?? {}), 'brightness': data},
        };

      case 'audio_sinks':
        if (data is Map) {
          audioSinksDefault = '${data['default'] ?? ''}';
          if (data['sinks'] is List) {
            audioSinks = List<Map<String, dynamic>>.from(data['sinks']);
          }
          connectingSink = null; // liste rafraîchie -> fin de connexion en cours
        }

      case 'audio_sink_changed':
        if (data is Map && data['success'] == true) {
          audioSinksDefault = '${data['default'] ?? audioSinksDefault}';
          audioSinks = audioSinks.map((s) =>
            {...s, 'is_default': s['name'] == audioSinksDefault}
          ).toList();
        }

      case 'bt_devices':
        if (data is Map) {
          btScanning = data['scanning'] == true;
          btAvailable = data['available'] != false;
          if (data['devices'] is List) {
            btDevices = List<Map<String, dynamic>>.from(data['devices']);
          }
        }

      case 'bt_action_result':
        if (data is Map) {
          btBusy.remove('${data['mac'] ?? ''}'); // action terminée -> réactive
          connectingSink = null; // (echec de connexion depuis « Sortie »)
          if (data['ok'] != true) {
            btActionError = '${data['error'] ?? 'Échec de l\'opération'}';
            Future.delayed(const Duration(seconds: 5), () {
              if (_disposed) return;
              btActionError = null;
              notifyListeners();
            });
          } else {
            btActionError = null;
          }
        }
    }
    notifyListeners();
  }

  // Expose raw WS messages for pages that need specific events
  Stream<Map<String, dynamic>> get messages => _ws.messages;

  // --- Actions ---
  void send(Map<String, dynamic> msg) => _ws.send(msg);
  void notify() => notifyListeners();

  void setPage(int page) {
    if (page >= 0 && page <= 5 && page != currentPage) {
      currentPage = page;
      onHome = false;
      onSettings = false;
      notifyListeners();
    }
  }

  /// Navigate to a domain page (0..5). Clears HOME. Used by rail + voice `page`.
  void goToPage(int page) {
    if (page >= 0 && page <= 5) {
      currentPage = page;
      onHome = false;
      onSettings = false;
      notifyListeners();
    }
  }

  /// Show the Accueil (HOME) bento. UI-only — no backend navigation.
  void goHome() {
    onHome = true;
    onSettings = false;
    notifyListeners();
  }

  /// Ouvre la page PLEINE Paramètres dans la zone de contenu. Précharge les
  /// données affichées (sorties audio, config, appareils BT) comme l'ancien drawer.
  void goSettings() {
    if (onSettings) return;
    onSettings = true;
    onHome = false;
    requestAudioSinks();
    requestConfig();
    requestBtDevices();
    send({'type': 'system_info'});  // rafraîchit la pastille passerelle (gratuit/cloud)
    notifyListeners();
  }

  void musicPlay(String query) => send({'type': 'music_play', 'data': query});
  void musicPause() => send({'type': 'music_pause'});
  void musicResume() => send({'type': 'music_resume'});
  void musicStop() => send({'type': 'music_stop'});
  void musicNext() => send({'type': 'music_next'});
  void musicPrev() => send({'type': 'music_prev'});

  void rollerAction(String id, String action) => send({'type': 'domotique_roller', 'data': {'id': id, 'action': action}});
  void rollerAll(String action) {
    rollerAction('volet_gauche', action);
    rollerAction('volet_milieu', action);
    rollerAction('volet_droit', action);
  }
  void triggerPortail() => send({'type': 'domotique_portail'});
  void plugToggle(String id) {
    final dev = domotiqueData[id];
    send({'type': 'domotique_plug', 'data': {'id': id, 'action': dev?['on'] == true ? 'off' : 'on'}});
  }

  void youtubeSearch(String query) {
    youtubeSearching = true;
    notifyListeners();
    send({'type': 'youtube_search', 'data': query});
  }
  bool _ytLaunching = false;
  void youtubePlay(Map<String, dynamic> video) {
    if (_ytLaunching) return; // debounce
    _ytLaunching = true;
    send({'type': 'youtube_select', 'data': video});
    Future.delayed(const Duration(seconds: 5), () => _ytLaunching = false);
  }
  void youtubeStop() => send({'type': 'youtube_stop'});

  void devialetVolume(int vol) => send({'type': 'devialet_volume', 'data': vol});
  void devialetPowerOff() => send({'type': 'devialet_power_off'});
  void devialetRestart() => send({'type': 'devialet_restart'});

  void requestAudioSinks() => send({'type': 'audio_sinks'});
  void setAudioSink(String name) => send({'type': 'audio_set_sink', 'data': name});

  /// Sélectionne une sortie. Si c'est une enceinte BT déconnectée, le backend la
  /// connecte d'abord (~quelques s) -> on affiche un spinner le temps de la connexion.
  void selectOutput(String name, {bool needsConnect = false}) {
    if (needsConnect) {
      connectingSink = name;
      notifyListeners();
      Future.delayed(const Duration(seconds: 20), () {
        if (_disposed) return;
        if (connectingSink == name) { connectingSink = null; notifyListeners(); }
      });
    }
    send({'type': 'audio_set_sink', 'data': name});
  }

  // --- Bluetooth (enceintes) ---
  void requestBtDevices() => send({'type': 'bt_devices'});
  void btScan(bool start) {
    btScanning = start;
    notifyListeners();
    send({'type': 'bt_scan', 'data': {'action': start ? 'start' : 'stop'}});
  }
  void btPair(String mac) => _btAction('bt_pair', mac);
  void btConnect(String mac) => _btAction('bt_connect', mac);
  void btDisconnect(String mac) => _btAction('bt_disconnect', mac);
  void btForget(String mac) => _btAction('bt_forget', mac);

  /// Envoie une action BT en ignorant les double-taps (l'appareil est "occupé"
  /// jusqu'au bt_action_result, ou ~25 s en sécurité). Feedback immédiat.
  void _btAction(String type, String mac) {
    if (btBusy.contains(mac)) return;
    btBusy.add(mac);
    notifyListeners();
    send({'type': type, 'data': {'mac': mac}});
    Future.delayed(const Duration(seconds: 25), () {
      if (_disposed) return;
      if (btBusy.remove(mac)) notifyListeners();
    });
  }

  // --- Config hub ---
  void requestConfig() => send({'type': 'config_get'});

  /// Écrit un réglage. restart=true -> marque qu'un redémarrage est requis.
  void configSet(String section, String key, dynamic value, {bool restart = false}) {
    send({'type': 'config_set', 'data': {'section': section, 'key': key, 'value': value}});
    // maj optimiste locale pour un feedback immédiat
    config = {...config, section: {...(config[section] as Map? ?? {}), key: value}};
    if (restart) pendingRestart.add('$section.$key');
    notifyListeners();
  }

  void screenBrightness(int pct) => send({'type': 'screen_brightness', 'data': pct});

  void systemReboot() => send({'type': 'system_reboot'});
  void systemRestartBackend() {
    pendingRestart.clear();
    send({'type': 'system_restart_backend'});
    notifyListeners();
  }

  void systemShutdown() => send({'type': 'system_shutdown'});

  void setFullscreenCam(Map<String, dynamic>? cam) {
    fullscreenCam = cam;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _progressTimer?.cancel();
    _msgSub.cancel();
    _connSub.cancel();
    pageController.dispose();
    _ws.dispose();
    super.dispose();
  }
}
