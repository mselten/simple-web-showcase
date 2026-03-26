# Audio Streaming Project

Real-time audio visualization with sensor-app streaming to webserver.

## Structure

```
.
├── .env                 # Configuration (passwords, host, port)
├── docker-compose.yml   # Webserver container
├── sensor-app/          # Microphone client
│   ├── app.py           # Main application
│   └── requirements.txt
└── webserver/           # Flask server
    ├── app.py           # Backend
    ├── templates/index.html
    ├── Dockerfile
    └── requirements.txt
```

## Quick Start

### 1. Install dependencies

```bash
# sensor-app
cd sensor-app && pip install -r requirements.txt

# webserver
cd webserver && pip install -r requirements.txt
```

### 2. Configure

Edit `.env`:
```
WS_PASSWORD=your_password
SERVER_HOST=localhost
SERVER_PORT=5000
```

### 3. Run

**Option A: Docker (recommended)**
```bash
docker compose up --build
# Open http://localhost:5000
```

**Option B: Manual**
```bash
# Terminal 1: Start webserver
cd webserver && python app.py

# Terminal 2: Start sensor-app
cd sensor-app && python app.py
```

### 4. Test sensor

```bash
cd sensor-app && python app.py --test
```

## Usage

- **Webserver**: Open `http://localhost:5000` in browser to see real-time waveform visualization
- **sensor-app**: Captures microphone and streams to webserver
- **--test mode**: Captures 3 seconds, prints RMS/peak amplitude, exits

## Troubleshooting

- Port 80 requires root; default is 5000
- Check microphone permissions if sensor-app fails
- Ensure `.env` is in project root