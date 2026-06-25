# PI-Board Flutter UI

Interface native V3 de PI-Board pour **flutter-pi**. C'est l'UI vivante du device `.152`; l'ancien
frontend Svelte `../frontend/` est un artefact V1 mort.

## Rôle

- Écran de salon HDMI paysage, design de référence **1920x1200**.
- Rendu natif via `flutter-pi`, pas Chromium.
- WebSocket vers le backend FastAPI : `ws://127.0.0.1:8000/ws`.
- Rail gauche persistant, Accueil + pages Musique, Météo, YouTube, Caméras, Devialet, Maison, Réglages.
- Theming live via `ui.accent_color` / `ui.bg_color`.
- i18n FR/EN via `lib/i18n.dart`.
- Indépendance de résolution paysage via `_DesignSizeScaler` dans `lib/main.dart`.

## Build / déploiement

Depuis la racine du repo privé :

```bash
scripts/deploy-flutter-v3.sh
```

Le script lance `flutter pub get`, construit le bundle AOT arm64 avec `flutterpi_tool`, rsync vers
`piboard@192.168.1.152:/home/piboard/piboard-v3/`, puis redémarre `piboard-v3.service`.

Voir [`../CLAUDE.md`](../CLAUDE.md) pour les règles complètes de déploiement, services systemd et caveats
hardware. Ne pas utiliser les scripts V1 `deploy-pi.sh`, `start.sh` ou les services kiosk Chromium pour V3.
