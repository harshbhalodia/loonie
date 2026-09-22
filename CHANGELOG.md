# Changelog

All notable changes to Loonie are documented here. Dates are in UTC.

## 0.1.5 -- 2026-09-22

- Update button is now a prominent blue 'Update' button (header pill + Settings) that downloads and installs the latest version directly, instead of just a message pointing elsewhere

## 0.1.4 -- 2026-09-22

- Rebrand from LifeOS to Loonie across the app, and add a first-run onboarding flow (welcome, set your first goal, add your first account, quick-start checklist) for the Wealth module

## 0.1.3 -- 2026-09-22

- Fix backend crash on fresh installs: config.example.yaml is now bundled as a resource so the packaged app can bootstrap config.yaml (was FileNotFoundError before)

## 0.1.2 -- 2026-09-22

- Fix install.ps1 404 (auto-detect latest installer instead of a hardcoded filename); install.ps1 now only downloads backend source files instead of the whole repo; daily updates skip reinstalling Python deps unless requirements.txt changed



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
