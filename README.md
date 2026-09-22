# Loonie

> Plan with purpose. Decide with clarity. Pivot with confidence.

Loonie is a private, local-first "Life OS" desktop app — track wealth, budgets, goals and net
worth, import bank statements, and get AI-assisted insights from your own local LLM (or the Jev
API). Everything runs on your own machine: a self-hosted FastAPI backend + SQLite database, no
cloud account required.

## Quick install (recommended)

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/harshbhalodia/loonie/main/install.ps1 | iex
```

This single command:
- Installs Python automatically if it's missing (via `winget`, no manual download needed)
- Sets up the Loonie backend under `%LOCALAPPDATA%\Loonie`
- Creates your local config with a unique, randomly generated security key
- Downloads and launches the Loonie desktop installer

When it finishes, launch **Loonie** from the Start Menu and log in with:

- Email: `admin@example.com`
- Password: `change-me`

Change this password after your first login (edit `%LOCALAPPDATA%\Loonie\config\config.yaml`,
then fully restart Loonie for it to take effect — this only affects newly-created accounts, not
existing ones, since the password is only set once on first startup).

## Manual install

If you'd rather not run the one-liner:

1. Install [Python 3.11+](https://python.org/downloads/) if you don't already have it.
2. Download this repo (Code → Download ZIP, or `git clone`).
3. Copy `backend/` to `%LOCALAPPDATA%\Loonie\backend` and `config/` to `%LOCALAPPDATA%\Loonie\config`.
4. Open a terminal in `%LOCALAPPDATA%\Loonie\backend` and run:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   copy ..\config\config.example.yaml ..\config\config.yaml
   .venv\Scripts\python.exe -m alembic upgrade head
   ```
5. Run the installer from [`installer/Loonie_0.1.1_x64-setup.exe`](installer/Loonie_0.1.1_x64-setup.exe)
   (or the `.msi` in the same folder).
6. Launch Loonie — it auto-starts the backend for you.

## Staying up to date

Loonie checks for new versions automatically (every 30 minutes, and once on launch). When one is
available you'll see an **Update available** pill in the header — click it, then "Update &
restart now", and Loonie downloads the update, restarts the backend, and relaunches itself on the
new version. No need to re-run the installer or visit this page again.

You can also check manually any time from **Settings → Version & updates**. See
[CHANGELOG.md](CHANGELOG.md) for what's new in each release.

## Requirements

- Windows 10/11 (macOS/Linux packaging not available yet)
- Python 3.11+ (installed automatically by the quick-install script)
- Optional: a local LLM server (e.g. LM Studio) for AI insights — every core feature works
  without AI enabled

## How it works

Loonie is a native desktop shell (Tauri) around a React frontend. On launch, it automatically
starts your local FastAPI backend (or reuses one already running on port 8000) and shuts it down
again when you close the app. Your data lives entirely in a local SQLite file under
`%LOCALAPPDATA%\Loonie\backend\data\lifeos.db` — nothing is sent anywhere unless you explicitly
enable an AI provider. The backend source ships inside the installer itself, so app updates keep
the backend in sync automatically — nothing extra to download or copy.

## Jumpstart tutorials

- [ ] Setting up your first budget and categories
- [ ] Importing a bank statement (CSV/PDF)
- [ ] Setting goals and tracking net worth
- [ ] Connecting a local LLM for AI insights
- [ ] Using the Decision Maker

## Extensions / try these

- [ ] Custom category rules for auto-categorizing statement imports
- [ ] Scenario sandbox (best/expected/worst-case net worth projections)
- [ ] Investment watchlist & research topics
- [ ] Wealth agents (budget analyzer, risk/diversification, asset advisor, goal planner)

## Privacy & security

- All data lives in a local SQLite file on your machine — never uploaded anywhere.
- AI features are opt-in and can be fully disabled in `config.yaml`.
- Each install generates its own random JWT signing key (never shared across installs).
- This is single-user, local-network software — don't expose port 8000 to the public internet
  without adding proper hardening first.

## Known limitations (early access)

- Windows only for now.
- No in-app "change password" screen yet — the bootstrap admin password is only set once, on the
  very first run. Edit `config.yaml` *before* first launch if you want a different password.

## License

See [LICENSE](LICENSE).
