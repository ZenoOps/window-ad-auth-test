# Svelte + Litestar Kerberos Test Application

A small Windows-hosted application that uses:

- Svelte and Vite for the browser UI
- Litestar and Uvicorn for the Python API
- Casdoor Kerberos authentication with an OIDC authorization-code exchange
- SQLite for opaque application sessions and local fallback accounts
- WinSW to run the compiled frontend and backend as one Windows service

Docker, WSL, and a virtual machine are not required on the Windows Server.

## Authentication flow

1. The browser opens the application on port `9090`.
2. Svelte checks for an existing application session.
3. Without a session, Litestar creates a short-lived, browser-bound state value.
4. The browser calls Casdoor's `/api/kerberos-login` endpoint directly. This allows the browser to answer the Kerberos `Negotiate` challenge.
5. Casdoor returns an authorization code in its JSON `data` field.
6. Svelte forwards the code and state to `/api/auth/callback`.
7. Litestar validates the state, exchanges the code using the Casdoor client secret, validates the returned JWT, and creates an opaque HTTP-only session cookie.
8. If Kerberos is unavailable or rejected, the browser moves to `/login` for a local SQLite account.

The Casdoor client secret and tokens are never stored in Svelte.

## Configure Casdoor

Create a dedicated Casdoor application rather than using `app-built-in`.

Add this Redirect URL, replacing the hostname with the application server's DNS name:

```text
http://WINDOWS_SERVER_HOST:9090/api/auth/callback
```

Use the same value for `CASDOOR_REDIRECT_URI`. It must match exactly.

The Windows client must resolve `casdoor.lab.hexcode.test`, and that Casdoor origin must remain in the Local Intranet zone so the browser can send Kerberos credentials silently.

The Svelte page calls Casdoor from a different origin. If the browser reports a CORS error, configure Casdoor to allow the application origin:

```text
http://WINDOWS_SERVER_HOST:9090
```

## Windows Server setup

Copy this entire folder to the server. Open PowerShell in the application directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
```

The setup script installs missing Node.js/Python prerequisites with WinGet, compiles Svelte, creates `backend\.venv`, installs Python packages, and creates `backend\.env` from the example when it does not exist.

Edit `backend\.env`:

```dotenv
CASDOOR_ENDPOINT=http://casdoor.lab.hexcode.test:8000
CASDOOR_APPLICATION=app-svelte-litestar
CASDOOR_CLIENT_ID=your-client-id
CASDOOR_CLIENT_SECRET=your-client-secret
CASDOOR_REDIRECT_URI=http://WINDOWS_SERVER_HOST:9090/api/auth/callback
CASDOOR_SCOPE=openid profile email

CASDOOR_AUDIENCE=
CASDOOR_DISCOVERY_URL=
CASDOOR_ALLOWED_ALGORITHMS=RS256

AUTH_DATABASE_PATH=data/auth.db
SESSION_TTL_SECONDS=28800
AUTH_FLOW_TTL_SECONDS=300
SESSION_COOKIE_SECURE=false
```

Use a hostname that the Windows 11 client can resolve. Kerberos and the Casdoor application configuration should not use an IP address.

## Create a local fallback account

After setup, run this from the application directory:

```powershell
& .\backend\.venv\Scripts\python.exe .\backend\create_local_user.py
```

The password is entered interactively and is stored as an Argon2 hash in `backend\data\auth.db`. Running the command again with the same username updates its password and display name.

## Test manually

Start the application:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-windows.ps1
```

Open `http://WINDOWS_SERVER_HOST:9090` from the Windows 11 VM. A domain user with a matching Casdoor Kerberos name should be signed in without clicking a button. A failed Kerberos attempt opens `http://WINDOWS_SERVER_HOST:9090/login`.

If another computer cannot connect, run this once in Administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Svelte Python Test" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9090 -RemoteAddress LocalSubnet
```

## Install as a Windows service

Run setup and complete `backend\.env` first. Stop the manually running process, then open PowerShell **as Administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows-service.ps1
```

The installer downloads WinSW, registers `SvelteLitestarApp`, and starts it. It serves both the compiled frontend and API on port `9090`.

Useful commands:

```powershell
Get-Service SvelteLitestarApp
Restart-Service SvelteLitestarApp
Stop-Service SvelteLitestarApp
Start-Service SvelteLitestarApp
```

Logs are written under `service\logs`:

```powershell
Get-Content .\service\logs\SvelteLitestarService.out.log -Wait
Get-Content .\service\logs\SvelteLitestarService.err.log -Wait
```

Remove the service without deleting the application:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall-windows-service.ps1
```

After changing code or dependencies:

```powershell
Stop-Service SvelteLitestarApp
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
Start-Service SvelteLitestarApp
```

## Endpoints

- `GET /api/health`
- `GET /api/hello?name=Zeno`
- `GET /api/auth/kerberos/start`
- `GET /api/auth/callback?code=...&state=...`
- `POST /api/auth/local-login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/verify` with `Authorization: Bearer <Casdoor JWT>`

## Production notes

This remains a test application. Before production use, terminate HTTPS in front of it, set `SESSION_COOKIE_SECURE=true`, add login rate limiting and audit logging, define account lockout/disable procedures, and move secrets out of a plaintext `.env` file into an appropriate Windows secret store.
