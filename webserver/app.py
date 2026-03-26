import os
import base64
from pathlib import Path

import numpy as np
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

AUDIO_BUFFER = []


def load_config():
    load_dotenv(SCRIPT_DIR.parent / ".env")
    return {
        "password": os.getenv("WS_PASSWORD", ""),
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "5000")),
    }


config = load_config()


def process_audio(audio_data: np.ndarray) -> np.ndarray:
    audio_float = audio_data.astype(np.float32) / 32768.0
    audio_float = audio_float - np.mean(audio_float)
    max_val = np.max(np.abs(audio_float))
    if max_val > 0:
        audio_float = audio_float / max_val
    return (audio_float * 32767).astype(np.int16)


@socketio.on("auth")
def handle_auth(data):
    password = data.get("password", "")
    if password == config["password"]:
        emit("auth_response", {"status": "ok"})
    else:
        emit("auth_response", {"status": "error", "message": "Invalid password"})


@socketio.on("audio_data")
def handle_audio_data(data):
    try:
        audio_bytes = base64.b64decode(data)
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        processed = process_audio(audio_array)
        processed_bytes = processed.tobytes()
        encoded = base64.b64encode(processed_bytes).decode("utf-8")
        emit("audio_data", {"data": encoded}, broadcast=True)
    except Exception as e:
        print(f"Audio processing error: {e}")


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=config["port"],
        debug=False,
        allow_unsafe_werkzeug=True,
    )
