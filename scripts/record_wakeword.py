#!/usr/bin/env python3
"""Record wake word samples for EfficientWord-Net.

Usage: python record_wakeword.py [wakeword_name] [num_samples]

Records N audio samples of you saying the wake word.
Saves them as WAV files in backend/audio/hotword_samples/<wakeword>/
Then generates the reference file for EfficientWord-Net.
"""
import os
import sys
import time
import wave
import pyaudio

WAKEWORD = sys.argv[1] if len(sys.argv) > 1 else "terminator"
NUM_SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 5
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
RECORD_SECONDS = 2.0

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES_DIR = os.path.join(BASE_DIR, "backend", "audio", "hotword_samples", WAKEWORD)
REFS_DIR = os.path.join(BASE_DIR, "backend", "audio", "hotword_refs")

os.makedirs(SAMPLES_DIR, exist_ok=True)
os.makedirs(REFS_DIR, exist_ok=True)

pa = pyaudio.PyAudio()

# Find USB mic
device_idx = None
device_rate = SAMPLE_RATE
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0 and "usb" in info["name"].lower():
        device_idx = i
        device_rate = int(info["defaultSampleRate"])
        print(f"Micro: {info['name']} (index {i}, rate={device_rate})")
        break

if device_idx is None:
    # Try AI-Voice
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and "ai" in info["name"].lower():
            device_idx = i
            device_rate = int(info["defaultSampleRate"])
            print(f"Micro: {info['name']} (index {i}, rate={device_rate})")
            break

if device_idx is None:
    print("Aucun micro USB trouve!")
    sys.exit(1)

print(f"\n=== Enregistrement du wake word: '{WAKEWORD}' ===")
print(f"Tu vas enregistrer {NUM_SAMPLES} echantillons de {RECORD_SECONDS}s chacun.")
print(f"Dis '{WAKEWORD}' clairement a chaque fois.\n")

for i in range(NUM_SAMPLES):
    input(f"[{i+1}/{NUM_SAMPLES}] Appuie sur ENTREE puis dis '{WAKEWORD}'... ")

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=device_rate,
        input=True,
        input_device_index=device_idx,
        frames_per_buffer=CHUNK,
    )

    print("  Enregistrement...", end="", flush=True)
    frames = []
    for _ in range(int(device_rate * RECORD_SECONDS / CHUNK)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    print(" OK!")

    # Save as WAV (at native rate — EfficientWord-Net handles resampling)
    filepath = os.path.join(SAMPLES_DIR, f"{WAKEWORD}_{i+1}.wav")
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(device_rate)
        wf.writeframes(b"".join(frames))
    print(f"  Sauvegarde: {filepath}")

pa.terminate()

print(f"\n=== Generation du fichier de reference ===")

from eff_word_net.generate_reference import generate_reference_file
generate_reference_file(
    input_dir=SAMPLES_DIR,
    output_dir=REFS_DIR,
    wakeword=WAKEWORD,
    debug=True,
)

ref_file = os.path.join(REFS_DIR, f"{WAKEWORD}_ref.json")
if os.path.exists(ref_file):
    print(f"\nReference generee: {ref_file}")
    print("Tu peux maintenant redemarrer le backend!")
else:
    print("\nErreur: fichier de reference non genere")
