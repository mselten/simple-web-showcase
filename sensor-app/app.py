#!/usr/bin/env python3
import argparse
import os
import sys
import time
from pathlib import Path

import base64
import io

import numpy as np
import sounddevice as sd
import socketio
from dotenv import load_dotenv
from scipy import signal

SCRIPT_DIR = Path(__file__).parent
TARGET_SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 100


def load_config():
    load_dotenv(SCRIPT_DIR.parent / ".env")
    return {
        "password": os.getenv("WS_PASSWORD", ""),
        "host": os.getenv("SERVER_HOST", "localhost"),
        "port": os.getenv("SERVER_PORT", "5000"),
        "device": int(os.getenv("AUDIO_DEVICE")) if os.getenv("AUDIO_DEVICE") else None,
    }


def get_device_sample_rate(device_index):
    if device_index is None:
        dev = sd.query_devices(kind="input")
    else:
        dev = sd.query_devices(device_index)
    return int(dev.get("default_sample_rate", dev.get("sample_rate", 16000)))


def resample_audio(audio_data, orig_rate, target_rate):
    if orig_rate == target_rate:
        return audio_data
    num_samples = int(len(audio_data) * target_rate / orig_rate)
    resampled = signal.resample_poly(
        audio_data, target_rate, orig_rate, num=num_samples
    )
    return resampled.astype(np.int16)


class AudioStreamer:
    def __init__(self, config):
        self.config = config
        self.sio = socketio.Client()
        self.running = False
        self.stream = None

        @self.sio.event
        def connect():
            print("Connected to server")

        @self.sio.event
        def disconnect():
            print("Disconnected from server")

    def connect(self):
        url = f"http://{self.config['host']}:{self.config['port']}"
        print(f"Connecting to {url}...")
        self.sio.connect(url, wait_timeout=10)
        self.sio.emit("auth", {"password": self.config["password"]})

    def reconnect(self):
        while self.running:
            try:
                self.connect()
                return
            except Exception as e:
                print(f"Reconnect failed: {e}, retrying in 5s...")
                time.sleep(5)

    def start(self):
        self.running = True
        device_rate = get_device_sample_rate(self.config.get("device"))
        device_chunk_size = device_rate * CHUNK_DURATION_MS // 1000

        def audio_callback_wrapper(indata, frames, time_info, status):
            if status:
                print(f"Audio status: {status}", file=sys.stderr)
            audio_int16 = (indata.flatten() * 32767).astype(np.int16)
            resampled = resample_audio(audio_int16, device_rate, TARGET_SAMPLE_RATE)

            # Noise gate - skip near-silent audio
            rms = np.sqrt(np.mean(resampled.astype(np.float32) ** 2))
            if rms < 100:  # Threshold for quiet room noise
                return

            audio_bytes = resampled.tobytes()
            try:
                if self.sio.connected:
                    encoded = base64.b64encode(audio_bytes).decode("utf-8")
                    self.sio.emit("audio_data", encoded)
                else:
                    self.reconnect()
            except Exception as e:
                print(f"Send error: {e}, reconnecting...")
                self.reconnect()

        self.stream = sd.InputStream(
            samplerate=device_rate,
            channels=1,
            dtype="int16",
            blocksize=device_chunk_size,
            callback=audio_callback_wrapper,
            device=self.config["device"],
        )
        self.stream.start()
        print(
            f"Captured at {device_rate}Hz, resampled to {TARGET_SAMPLE_RATE}Hz, {CHUNK_DURATION_MS}ms chunks"
        )

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            self.stop()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.sio.connected:
            self.sio.disconnect()
        print("Stopped")


def test_mode(config):
    print("=== Available Input Devices ===")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"  {i}: {dev['name']} ({dev['max_input_channels']} ch)")

    device = config.get("device")
    device_info = (
        sd.query_devices(device)
        if device is not None
        else sd.query_devices(kind="input")
    )
    sample_rate = int(
        device_info.get("default_sample_rate", device_info.get("sample_rate", 48000))
    )
    device_name = device_info.get("name", "unknown")

    print()
    print(f"Test mode: capturing 3 seconds of audio...")
    print(f"Using device: {device_name} (index: {device})")
    print(f"Sample rate: {sample_rate} Hz")
    print()
    print(f"Test mode: capturing 3 seconds of audio...")
    print(f"Using device: {device_name} (index: {device})")
    print(f"Sample rate: {sample_rate} Hz")
    print()

    audio_data = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}", file=sys.stderr)
        audio_data.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=sample_rate * CHUNK_DURATION_MS // 1000,
        callback=callback,
        device=device,
    )

    with stream:
        time.sleep(3)

    if audio_data:
        combined = np.concatenate(audio_data)
        rms = np.sqrt(np.mean(combined.astype(np.float32) ** 2))
        peak = np.max(np.abs(combined))
        min_val = np.min(combined)
        max_val = np.max(combined)
        std_val = np.std(combined)

        print("=== Results ===")
        print(f"Total samples: {len(combined)}")
        print(f"RMS amplitude: {rms:.2f}")
        print(f"Peak amplitude: {peak}")
        print(f"Min value: {min_val}")
        print(f"Max value: {max_val}")
        print(f"Std deviation: {std_val:.2f}")
        print()
        print("First 10 samples:", combined[:10].tolist())
        print()

        # Assessment
        if std_val < 100:
            print("❌ DEAD MIC: Very low variation (std < 100)")
        elif std_val < 500:
            print("⚠️  QUIET: Low variation (std 100-500), may need gain adjustment")
        elif rms > 5000:
            print("✅ GOOD: Strong signal with good variation")
        elif rms > 1000:
            print("✅ OK: Decent signal")
        else:
            print("⚠️  WEAK: Low RMS, but mic appears to be working")
    else:
        print("No audio captured")
    print()
    print("Test complete")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run test mode")
    args = parser.parse_args()

    config = load_config()
    if args.test:
        test_mode(config)
    else:
        streamer = AudioStreamer(config)
        streamer.start()


if __name__ == "__main__":
    main()
