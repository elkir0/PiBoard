/// i18n léger pour PI-Board (sans codegen, adapté à flutter-pi).
///
/// Une table `clé -> {fr, en}` + `t('clé')`. La langue vient du backend
/// (`config.ui.locale`, poussé par WS) via [setAppLocale]. Repli : la clé FR,
/// puis la clé brute. Ajouter des clés ici ; les écrans appellent `t('...')`.
library;

String _locale = 'fr';

/// Définit la langue active ('fr' | 'en'). Ignore les valeurs inconnues.
void setAppLocale(String? locale) {
  final l = (locale ?? '').trim().toLowerCase();
  if (l.startsWith('en')) {
    _locale = 'en';
  } else if (l.startsWith('fr')) {
    _locale = 'fr';
  }
}

String get appLocale => _locale;

/// Traduit une clé dans la langue active (repli FR, puis la clé).
String t(String key) {
  final m = _strings[key];
  if (m == null) return key;
  return m[_locale] ?? m['fr'] ?? key;
}

const Map<String, Map<String, String>> _strings = {
  // ── Navigation (rail) ────────────────────────────────────────────────────
  'nav.home': {'fr': 'Accueil', 'en': 'Home'},
  'nav.music': {'fr': 'Musique', 'en': 'Music'},
  'nav.weather': {'fr': 'Météo', 'en': 'Weather'},
  'nav.youtube': {'fr': 'YouTube', 'en': 'YouTube'},
  'nav.cameras': {'fr': 'Caméras', 'en': 'Cameras'},
  'nav.devialet': {'fr': 'Devialet', 'en': 'Devialet'},
  'nav.house': {'fr': 'Maison', 'en': 'Home'},
  'nav.settings': {'fr': 'Réglages', 'en': 'Settings'},

  // ── Réglages : entête + sections ──────────────────────────────────────────
  'settings.title': {'fr': 'Paramètres', 'en': 'Settings'},
  'settings.section.voice': {'fr': 'VOIX / IA', 'en': 'VOICE / AI'},
  'settings.section.wakeword': {'fr': 'MOT-RÉVEIL', 'en': 'WAKE WORD'},
  'settings.section.audio': {'fr': 'AUDIO', 'en': 'AUDIO'},
  'settings.section.bluetooth': {'fr': 'BLUETOOTH', 'en': 'BLUETOOTH'},
  'settings.section.display': {'fr': 'AFFICHAGE', 'en': 'DISPLAY'},
  'settings.section.system': {'fr': 'SYSTÈME', 'en': 'SYSTEM'},
  'settings.section.admin': {'fr': 'ADMINISTRATION À DISTANCE', 'en': 'REMOTE ADMIN'},

  // ── Réglages : langue ─────────────────────────────────────────────────────
  'settings.language': {'fr': 'Langue', 'en': 'Language'},

  // ── Réglages : VOIX / IA ──────────────────────────────────────────────────
  'voice.tts': {'fr': "Voix de l'assistant", 'en': 'Assistant voice'},
  'voice.tts.sub': {'fr': 'Mac mini = gratuit · FR locale = Piper', 'en': 'Mac mini = free · local FR = Piper'},
  'voice.tts.gateway': {'fr': 'Mac mini', 'en': 'Mac mini'},
  'voice.tts.cloud': {'fr': 'Cloud', 'en': 'Cloud'},
  'voice.tts.piper': {'fr': 'FR locale', 'en': 'Local FR'},
  'voice.llm': {'fr': 'Modèle IA (cloud)', 'en': 'AI model (cloud)'},
  'voice.llm.sub': {'fr': 'Utilisé quand le cerveau est en mode cloud', 'en': 'Used when the brain runs in cloud mode'},
  'voice.length': {'fr': 'Longueur des réponses', 'en': 'Reply length'},
  'voice.note': {
    'fr': "Reconnaissance vocale et personnalité : réglables depuis l'administration à distance (QR ci-dessous).",
    'en': 'Speech recognition and personality: configurable from the remote admin (QR below).'
  },

  // ── Réglages : MOT-RÉVEIL ─────────────────────────────────────────────────
  'ww.engine': {'fr': 'Moteur de détection', 'en': 'Detection engine'},
  'ww.engine.sub': {'fr': 'Livekit = bien moins de faux déclenchements (recommandé)', 'en': 'Livekit = far fewer false triggers (recommended)'},
  'ww.livekit_model': {'fr': 'Modèle LiveKit', 'en': 'LiveKit model'},
  'ww.livekit_model.sub': {'fr': 'V2 = nouveau modèle fiable, rollback instantané vers V1', 'en': 'V2 = new reliable model, instant rollback to V1'},
  'ww.word': {'fr': 'Mot-réveil', 'en': 'Wake word'},
  'ww.word.sub': {'fr': 'Un autre mot que « terminator » passe sur openWakeWord', 'en': 'A word other than "terminator" switches to openWakeWord'},
  'ww.sensitivity': {'fr': 'Sensibilité', 'en': 'Sensitivity'},
  'ww.sensitivity.sub': {'fr': 'Plus haut = moins sensible', 'en': 'Higher = less sensitive'},
  'ww.cooldown': {'fr': 'Délai anti-répétition', 'en': 'Anti-repeat delay'},
  'ww.cooldown.sub': {'fr': 'Temps minimum entre deux réveils', 'en': 'Minimum time between two wakes'},

  // ── Réglages : AUDIO ──────────────────────────────────────────────────────
  'audio.output': {'fr': 'Sortie', 'en': 'Output'},
  'audio.volume': {'fr': 'Volume', 'en': 'Volume'},
  'audio.connect_hint': {'fr': 'Appuyez pour connecter', 'en': 'Tap to connect'},
  'audio.connecting': {'fr': 'Connexion…', 'en': 'Connecting…'},
  'audio.loading': {'fr': 'Chargement…', 'en': 'Loading…'},

  // ── Réglages : BLUETOOTH ──────────────────────────────────────────────────
  'bt.speakers': {'fr': 'Enceintes Bluetooth', 'en': 'Bluetooth speakers'},
  'bt.unavailable': {'fr': 'Bluetooth indisponible', 'en': 'Bluetooth unavailable'},
  'bt.search': {'fr': 'Rechercher', 'en': 'Search'},
  'bt.searching': {'fr': 'Recherche…', 'en': 'Searching…'},
  'bt.connect': {'fr': 'Connecter', 'en': 'Connect'},
  'bt.disconnect': {'fr': 'Déconnecter', 'en': 'Disconnect'},
  'bt.pair': {'fr': 'Appairer', 'en': 'Pair'},
  'bt.forget': {'fr': 'Oublier', 'en': 'Forget'},
  'bt.connected': {'fr': 'Connectée', 'en': 'Connected'},
  'bt.paired': {'fr': 'Appairée', 'en': 'Paired'},
  'bt.available': {'fr': 'Disponible', 'en': 'Available'},
  'bt.busy': {'fr': 'En cours…', 'en': 'Working…'},
  'bt.empty': {'fr': 'Aucun appareil. Allume ton enceinte puis lance une recherche.', 'en': 'No device. Turn on your speaker, then search.'},
  'bt.no_adapter': {'fr': 'Aucun adaptateur Bluetooth détecté sur cet appareil.', 'en': 'No Bluetooth adapter detected on this device.'},

  // ── Réglages : AFFICHAGE ──────────────────────────────────────────────────
  'display.brightness': {'fr': 'Luminosité', 'en': 'Brightness'},
  'display.sleep': {'fr': 'Veille écran', 'en': 'Screen sleep'},
  'display.sleep.sub': {'fr': "L'écran s'éteint la nuit · redémarrage requis", 'en': 'Screen turns off at night · restart required'},
  'display.screen': {'fr': 'Écran', 'en': 'Screen'},

  // ── Réglages : SYSTÈME ────────────────────────────────────────────────────
  'system.reboot': {'fr': 'Redémarrer la machine', 'en': 'Reboot the machine'},
  'system.restart': {'fr': "Redémarrer l'assistant", 'en': 'Restart the assistant'},
  'system.restart_speakers': {'fr': 'Redémarrer les enceintes', 'en': 'Restart the speakers'},
  'system.shutdown': {'fr': 'Éteindre la PiBoard', 'en': 'Shut down PiBoard'},
  'common.confirm': {'fr': 'Confirmer ?', 'en': 'Confirm?'},

  // ── Réglages : ADMIN (QR) ─────────────────────────────────────────────────
  'admin.scan': {'fr': 'Scannez avec votre téléphone (même WiFi)', 'en': 'Scan with your phone (same Wi-Fi)'},
  'admin.creds': {
    'fr': 'Réglages avancés, clés API, mot de passe · identifiants : admin / piboard',
    'en': 'Advanced settings, API keys, password · login: admin / (see logs)'
  },

  // ── Bandeau redémarrage ───────────────────────────────────────────────────
  'restart.banner': {'fr': 'Un redémarrage est requis pour appliquer certains réglages.', 'en': 'A restart is required to apply some settings.'},
  'restart.apply': {'fr': 'Appliquer & redémarrer', 'en': 'Apply & restart'},

  // ── Pastille passerelle IA ────────────────────────────────────────────────
  'gw.free': {'fr': 'IA locale · gratuit', 'en': 'Local AI · free'},
  'gw.free.sub': {'fr': 'Mac mini', 'en': 'Mac mini'},
  'gw.fallback': {'fr': 'Passerelle injoignable → cloud payant', 'en': 'Gateway unreachable → paid cloud'},
  'gw.fallback.sub': {'fr': "Le Mac mini ne répond pas · Mistral facturé à l'usage", 'en': 'Mac mini not responding · Mistral billed per use'},
  'gw.cloud': {'fr': 'Cloud Mistral · payant (choisi)', 'en': 'Mistral cloud · paid (chosen)'},
  'gw.cloud.sub': {'fr': 'Providers réglés sur le cloud', 'en': 'Providers set to cloud'},
  'gw.checking': {'fr': 'Vérification de la passerelle…', 'en': 'Checking the gateway…'},

  // ── Voix (bande d'état) ───────────────────────────────────────────────────
  'voice.listening': {'fr': 'À l\'écoute…', 'en': 'Listening…'},
  'voice.thinking': {'fr': 'Réflexion…', 'en': 'Thinking…'},
  'voice.speaking': {'fr': 'Réponse…', 'en': 'Replying…'},

  // ── admin ──
  "admin.or": {'fr': "ou", 'en': "or"},

  // ── cameras ──
  "cameras.ago": {'fr': "il y a", 'en': "ago"},
  "cameras.default_name": {'fr': "Caméra", 'en': "Camera"},
  "cameras.gate": {'fr': "Portail", 'en': "Gate"},
  "cameras.just_now": {'fr': "à l'instant", 'en': "just now"},
  "cameras.no_signal": {'fr': "signal indisponible", 'en': "signal unavailable"},
  "cameras.none": {'fr': "aucune caméra", 'en': "no camera"},
  "cameras.offline": {'fr': "hors ligne", 'en': "offline"},
  "cameras.online": {'fr': "en ligne", 'en': "online"},
  "cameras.searching": {'fr': "Recherche des caméras…", 'en': "Searching for cameras…"},
  "cameras.title": {'fr': "Caméras", 'en': "Cameras"},

  // ── devialet ──
  "devialet.equalizer": {'fr': "ÉGALISEUR", 'en': "EQUALIZER"},
  "devialet.leader": {'fr': "Leader", 'en': "Leader"},
  "devialet.muted": {'fr': "Muet", 'en': "Muted"},
  "devialet.night_mode": {'fr': "Mode nuit", 'en': "Night mode"},
  "devialet.no_speaker": {'fr': "Aucune enceinte", 'en': "No speaker"},
  "devialet.not_detected": {'fr': "Enceinte non détectée", 'en': "Speaker not detected"},
  "devialet.off": {'fr': "Désactivé", 'en': "Off"},
  "devialet.on": {'fr': "Activé", 'en': "On"},
  "devialet.out_of_100": {'fr': "SUR 100", 'en': "OUT OF 100"},
  "devialet.power": {'fr': "ALIMENTATION", 'en': "POWER"},
  "devialet.restart": {'fr': "Redémarrer", 'en': "Restart"},
  "devialet.restarting_speakers": {'fr': "Redémarrage des enceintes…", 'en': "Restarting speakers…"},
  "devialet.satellite": {'fr': "Satellite", 'en': "Satellite"},
  "devialet.source.optical": {'fr': "Optique", 'en': "Optical"},
  "devialet.source.standby": {'fr': "Veille", 'en': "Standby"},
  "devialet.speaker": {'fr': "Enceinte", 'en': "Speaker"},
  "devialet.speakers": {'fr': "ENCEINTES", 'en': "SPEAKERS"},
  "devialet.standby": {'fr': "Veille", 'en': "Standby"},
  "devialet.volume": {'fr': "VOLUME", 'en': "VOLUME"},

  // ── domotique ──
  "domotique.close_all": {'fr': "Fermer tout", 'en': "Close all"},
  "domotique.closing": {'fr': "Fermeture…", 'en': "Closing…"},
  "domotique.gate": {'fr': "Portail", 'en': "Gate"},
  "domotique.gate_garden": {'fr': "Portail du jardin", 'en': "Garden gate"},
  "domotique.off": {'fr': "Éteinte", 'en': "Off"},
  "domotique.offline": {'fr': "Hors ligne", 'en': "Offline"},
  "domotique.on": {'fr': "Allumée", 'en': "On"},
  "domotique.open": {'fr': "Ouvrir", 'en': "Open"},
  "domotique.open_all": {'fr': "Ouvrir tout", 'en': "Open all"},
  "domotique.opening": {'fr': "Ouverture…", 'en': "Opening…"},
  "domotique.position": {'fr': "Position", 'en': "Position"},
  "domotique.stopped": {'fr': "Arrêté", 'en': "Stopped"},
  "domotique.title": {'fr': "Maison", 'en': "Home"},
  "domotique.unavailable": {'fr': "Indisponible", 'en': "Unavailable"},

  // ── home ──
  "home.day.fri": {'fr': "Vendredi", 'en': "Friday"},
  "home.day.mon": {'fr': "Lundi", 'en': "Monday"},
  "home.day.sat": {'fr': "Samedi", 'en': "Saturday"},
  "home.day.sun": {'fr': "Dimanche", 'en': "Sunday"},
  "home.day.thu": {'fr': "Jeudi", 'en': "Thursday"},
  "home.day.tue": {'fr': "Mardi", 'en': "Tuesday"},
  "home.day.wed": {'fr': "Mercredi", 'en': "Wednesday"},
  "home.devialet.title": {'fr': "DEVIALET", 'en': "DEVIALET"},
  "home.house.guinguette": {'fr': "Guinguette", 'en': "String lights"},
  "home.house.guinguette_on": {'fr': "Guinguette allumée", 'en': "String lights on"},
  "home.house.shutters": {'fr': "Volets", 'en': "Shutters"},
  "home.house.title": {'fr': "MAISON", 'en': "HOME"},
  "home.month.apr": {'fr': "avril", 'en': "April"},
  "home.month.aug": {'fr': "août", 'en': "August"},
  "home.month.dec": {'fr': "décembre", 'en': "December"},
  "home.month.feb": {'fr': "février", 'en': "February"},
  "home.month.jan": {'fr': "janvier", 'en': "January"},
  "home.month.jul": {'fr': "juillet", 'en': "July"},
  "home.month.jun": {'fr': "juin", 'en': "June"},
  "home.month.mar": {'fr': "mars", 'en': "March"},
  "home.month.may": {'fr': "mai", 'en': "May"},
  "home.month.nov": {'fr': "novembre", 'en': "November"},
  "home.month.oct": {'fr': "octobre", 'en': "October"},
  "home.month.sep": {'fr': "septembre", 'en': "September"},
  "home.now_playing.empty": {'fr': "Dites « Terminator, mets de la musique »", 'en': "Say \"Terminator, play some music\""},
  "home.weather.feels_like": {'fr': "Ressenti", 'en': "Feels like"},
  "home.weather.title": {'fr': "MÉTÉO", 'en': "WEATHER"},

  // ── music ──
  "music.now_playing": {'fr': "LECTURE", 'en': "NOW PLAYING"},
  "music.playlists_empty": {'fr': "Aucune playlist", 'en': "No playlists"},
  "music.playlists_loading": {'fr': "Chargement des playlists…", 'en': "Loading playlists…"},
  "music.queue_empty": {'fr': "La file d'attente est vide", 'en': "The queue is empty"},
  "music.queue_up_next": {'fr': "À suivre", 'en': "Up next"},
  "music.search_empty": {'fr': "Tapez pour rechercher", 'en': "Type to search"},
  "music.search_hint": {'fr': "Rechercher un titre, un artiste…", 'en': "Search for a track or artist…"},
  "music.spotify_connect": {'fr': "Connecter", 'en': "Connect"},
  "music.spotify_disconnected": {'fr': "Spotify déconnecté", 'en': "Spotify disconnected"},
  "music.spotify_scan_qr": {'fr': "Scannez le QR code pour reconnecter", 'en': "Scan the QR code to reconnect"},
  "music.spotify_verify": {'fr': "Vérifier", 'en': "Check"},
  "music.tab_playlists": {'fr': "Playlists", 'en': "Playlists"},
  "music.tab_queue": {'fr': "File", 'en': "Queue"},
  "music.tab_search": {'fr': "Recherche", 'en': "Search"},
  "music.tracks_suffix": {'fr': "titres", 'en': "tracks"},
  "music.voice_hint": {'fr': "Dites « Terminator, mets de la musique »", 'en': "Say “Terminator, play some music”"},
  "music.volume_devialet": {'fr': "Volume Devialet", 'en': "Devialet volume"},
  "music.waiting": {'fr': "En attente…", 'en': "Waiting…"},

  // ── voice ──
  "voice.llm.fast": {'fr': "Rapide", 'en': "Fast"},
  "voice.llm.large": {'fr': "Large", 'en': "Large"},
  "voice.llm.small": {'fr': "Small", 'en': "Small"},

  // ── weather ──
  "weather.feels_like": {'fr': "Ressenti", 'en': "Feels like"},
  "weather.humidity": {'fr': "Humidité", 'en': "Humidity"},
  "weather.loading": {'fr': "Chargement de la météo…", 'en': "Loading weather…"},
  "weather.next_days": {'fr': "PROCHAINS JOURS", 'en': "NEXT DAYS"},
  "weather.next_hours": {'fr': "PROCHAINES HEURES", 'en': "NEXT HOURS"},
  "weather.refresh": {'fr': "Actualiser", 'en': "Refresh"},
  "weather.uv_extreme": {'fr': "Extrême", 'en': "Extreme"},
  "weather.uv_high": {'fr': "Élevé", 'en': "High"},
  "weather.uv_index": {'fr': "Indice UV", 'en': "UV index"},
  "weather.uv_low": {'fr': "Faible", 'en': "Low"},
  "weather.uv_moderate": {'fr': "Modéré", 'en': "Moderate"},
  "weather.uv_very_high": {'fr': "Très élevé", 'en': "Very high"},
  "weather.wind": {'fr': "Vent", 'en': "Wind"},

  // ── youtube ──
  "youtube.back": {'fr': "Retour", 'en': "Back"},
  "youtube.connecting": {'fr': "Connexion…", 'en': "Connecting…"},
  "youtube.idle_subtitle": {'fr': "Cherchez une vidéo à diffuser sur la TV", 'en': "Search for a video to play on the TV"},
  "youtube.loading_video": {'fr': "Chargement de la vidéo…", 'en': "Loading video…"},
  "youtube.min_chars_hint": {'fr': "Tapez au moins 2 lettres pour chercher", 'en': "Type at least 2 letters to search"},
  "youtube.playback_failed": {'fr': "Lecture impossible", 'en': "Playback failed"},
  "youtube.search_button": {'fr': "Rechercher une vidéo", 'en': "Search for a video"},
  "youtube.search_hint": {'fr': "Rechercher une vidéo…", 'en': "Search for a video…"},
  "youtube.searching": {'fr': "Recherche…", 'en': "Searching…"},
  "youtube.voice_hint": {'fr': "Dites « Terminator, mets une vidéo »", 'en': "Say \"Terminator, play a video\""},

};
