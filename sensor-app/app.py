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

SCRIPT_DIR = Path(__file__).parent
SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 100
CHUNK_SIZE = SAMPLE_RATE * CHUNK_DURATION_MS // 1000


def load_config():
    load_dotenv(SCRIPT_DIR.parent / ".env")
    return {
        "password": os.getenv("WS_PASSWORD", ""),
        "host": os.getenv("SERVER_HOST", "localhost"),
        "port": os.getenv("SERVER_PORT", "5000"),
    }


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
        self.connect()

        def audio_callback_wrapper(indata, frames, time_info, status):
            if status:
                print(f"Audio status: {status}", file=sys.stderr)
            audio_bytes = (indata.flatten() * 32767).astype("int16").tobytes()
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
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=audio_callback_wrapper,
        )
        self.stream.start()
        print(f"Streaming audio at {SAMPLE_RATE}Hz, {CHUNK_DURATION_MS}ms chunks")

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
    print("Test mode: capturing 3 seconds of audio...")
    audio_data = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}", file=sys.stderr)
        audio_data.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK_SIZE,
        callback=callback,
    )

    with stream:
        time.sleep(3)

    if audio_data:
        combined = np.concatenate(audio_data)
        rms = np.sqrt(np.mean(combined.astype(np.float32) ** 2))
        peak = np.max(np.abs(combined))
        print(f"RMS amplitude: {rms:.2f}")
        print(f"Peak amplitude: {peak}")
        print(f"Total samples: {len(combined)}")
    else:
        print("No audio captured")
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
