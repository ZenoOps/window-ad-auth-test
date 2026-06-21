# Simple Svelte + Python Web App

A minimal web application with:

- Svelte and Vite for the browser UI
- Litestar and Uvicorn for the Python API
- No database, Docker, WSL, or virtual machine required

## Quick Windows Server test

Install a current Node.js LTS release and Python 3, then copy this entire folder to the server.

Open PowerShell in this directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
powershell -ExecutionPolicy Bypass -File .\run-windows.ps1
```

Open <http://localhost:9090> on the server, or `http://SERVER_IP:9090` from another computer.

If another computer cannot connect, run this once in an Administrator PowerShell window:

```powershell
New-NetFirewallRule -DisplayName "Svelte Python Test" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9090 -RemoteAddress LocalSubnet
```

The setup script compiles Svelte and installs the Python packages. The run script starts one Python process that serves both the frontend and API.

## Development

### Start the Python API

PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 9090
```

Linux/macOS:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 9090
```

### Start the Svelte development server

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite forwards `/api` requests to Python on port 9090.

## Run as one application

Build the frontend:

```powershell
cd frontend
npm install
npm run build
cd ..\backend
```

Then start Python:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 9090
```

Open <http://localhost:9090>. Litestar serves both the API and the compiled Svelte frontend.

## Endpoints

- `GET /api/health`
- `GET /api/hello?name=Zeno`
