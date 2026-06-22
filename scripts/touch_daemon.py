#!/usr/bin/env python3
"""Daemon d'injection de touches pour tester l'UI flutter-pi en autonomie.
Cree un ecran tactile virtuel (uinput) et lit des commandes sur un FIFO :
  - "x y"        -> tap aux coords ecran (px, 1920x1200)
  - "swipe x1 y1 x2 y2" -> glissement
Le device reste ouvert (persistant) pour que libinput/flutter-pi le detecte.
Usage : sudo python3 touch_daemon.py   (lit /tmp/pb_touch)
"""
import os
import sys
import time

from evdev import UInput, AbsInfo, ecodes as e

W, H = 1920, 1200
FIFO = "/tmp/pb_touch"

cap = {
    e.EV_ABS: [
        (e.ABS_MT_SLOT, AbsInfo(0, 0, 9, 0, 0, 0)),
        (e.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
        (e.ABS_MT_POSITION_X, AbsInfo(0, 0, W - 1, 0, 0, 0)),
        (e.ABS_MT_POSITION_Y, AbsInfo(0, 0, H - 1, 0, 0, 0)),
        (e.ABS_X, AbsInfo(0, 0, W - 1, 0, 0, 0)),
        (e.ABS_Y, AbsInfo(0, 0, H - 1, 0, 0, 0)),
    ],
    e.EV_KEY: [e.BTN_TOUCH],
}

ui = UInput(cap, name="pb-virt-touch", version=0x3)
sys.stderr.write("[touch] device cree, attente hotplug libinput...\n")
sys.stderr.flush()
time.sleep(2.5)  # laisse flutter-pi/libinput ajouter le device


def _down(x, y):
    ui.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
    ui.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, 1)
    ui.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
    ui.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
    ui.write(e.EV_ABS, e.ABS_X, x)
    ui.write(e.EV_ABS, e.ABS_Y, y)
    ui.write(e.EV_KEY, e.BTN_TOUCH, 1)
    ui.syn()


def _move(x, y):
    ui.write(e.EV_ABS, e.ABS_MT_POSITION_X, x)
    ui.write(e.EV_ABS, e.ABS_MT_POSITION_Y, y)
    ui.write(e.EV_ABS, e.ABS_X, x)
    ui.write(e.EV_ABS, e.ABS_Y, y)
    ui.syn()


def _up():
    ui.write(e.EV_ABS, e.ABS_MT_SLOT, 0)
    ui.write(e.EV_ABS, e.ABS_MT_TRACKING_ID, -1)
    ui.write(e.EV_KEY, e.BTN_TOUCH, 0)
    ui.syn()


def tap(x, y):
    _down(x, y)
    time.sleep(0.07)
    _up()


def swipe(x1, y1, x2, y2, steps=14, dur=0.4):
    _down(x1, y1)
    for i in range(1, steps + 1):
        _move(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(dur / steps)
    _up()


def main():
    if os.path.exists(FIFO):
        os.remove(FIFO)
    os.mkfifo(FIFO)
    os.chmod(FIFO, 0o666)
    sys.stderr.write("[touch] pret, FIFO %s\n" % FIFO)
    sys.stderr.flush()
    while True:
        with open(FIFO, "r") as f:
            for line in f:
                parts = line.split()
                try:
                    if not parts:
                        continue
                    if parts[0] == "swipe" and len(parts) == 5:
                        swipe(int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
                    elif parts[0] == "quit":
                        ui.close()
                        return
                    elif len(parts) == 2:
                        tap(int(parts[0]), int(parts[1]))
                except Exception as ex:
                    sys.stderr.write("[touch] err: %s\n" % ex)
                    sys.stderr.flush()


if __name__ == "__main__":
    main()
