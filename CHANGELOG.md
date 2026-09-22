# Changelog

All notable changes to Loonie are documented here. Dates are in UTC.

## 0.1.1 — 2026-09-22

- **Auto-update support.** Loonie now periodically checks for new versions and shows an
  "Update available" pill in the header. One click downloads, installs, restarts the backend,
  and relaunches the app on the new version — no manual re-install needed ever again.
- Added a **Version & updates** card in Settings: shows the installed version, a manual
  "Check for updates" button, and a link to this changelog.
- The backend bundled inside the installer now stays in sync with the app version
  automatically — no separate backend download/copy step is needed for updates.
- Backend self-configures on first run: database migrations run automatically, and a unique
  random JWT signing key is generated per install.

## 0.1.0 — Initial release

- First installable build of Loonie: wealth tracking, budgets, goals, decisions, statement
  imports, and optional local/Jev AI insights, packaged as a Windows desktop app (NSIS + MSI).
