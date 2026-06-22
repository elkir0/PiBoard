#!/bin/bash
# Prerequis SYSTEME (one-shot) pour l'audio Bluetooth (enceintes A2DP) sur le Pi4.
# A lancer SUR LE PI (piboard@192.168.1.152). Idempotent.
#
# Pourquoi : sans le plugin SPA bluez, PipeWire ne cree AUCUN sink quand une
# enceinte BT se connecte. Et sans la config WirePlumber ci-dessous, les enceintes
# type JBL restent CONNECTEES mais MUETTES (volume absolu AVRCP decouple + contention
# des roles casque HSP/HFP qui bloque l'acquisition du transport A2DP).
set -e
export XDG_RUNTIME_DIR=/run/user/1000

echo "[1/3] Paquet libspa-0.2-bluetooth (codecs SBC/aptX/LDAC/LC3/Opus + cree les sinks A2DP)"
sudo apt-get install -y libspa-0.2-bluetooth

echo "[2/3] Config WirePlumber (0.4.x = format Lua) : hw-volume OFF + roles casque OFF"
# - bluez5.enable-hw-volume=false : le slider PipeWire devient un attenuateur logiciel
#   pleine echelle (sinon le volume absolu AVRCP peut rester coince a 0 -> enceinte muette).
# - bluez5.headset-roles="[ ]" : enceinte sans micro -> evite la contention profil/AVDTP
#   qui laissait le transport A2DP a moitie negocie (transport "idle" -> aucun son).
mkdir -p "$HOME/.config/wireplumber/bluetooth.lua.d"
cat > "$HOME/.config/wireplumber/bluetooth.lua.d/99-jbl-fix.lua" <<'EOF'
-- Correctif enceintes BT muettes (ex: JBL Xtreme 4). Se charge APRES 50-bluez-config.lua
-- et MUTE la table existante (merge). Reversible : supprimer ce fichier + restart wireplumber.
bluez_monitor.properties["bluez5.enable-hw-volume"] = false
bluez_monitor.properties["bluez5.headset-roles"] = "[ ]"
EOF

echo "[3/3] Recharge l'audio"
systemctl --user restart wireplumber pipewire pipewire-pulse
sleep 4
echo "  default sink : $(pactl get-default-sink)"
echo "Termine. Une enceinte BT appairee + connectee cree maintenant un sink audible."
echo "NB sur Pi4 : WiFi et BT partagent la puce BCM43455 ; eviter d'empiler les"
echo "    restarts audio/BT sous charge (le wake word occupe deja ~3 coeurs)."
