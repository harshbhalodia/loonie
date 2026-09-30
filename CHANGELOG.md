# Changelog

All notable changes to Loonie are documented here. Dates are in UTC.

## 0.6.0 -- 2026-09-30

- Richer asset records: add address, location, type, use and tags to homes, vehicles and other assets so advisors understand them better. Accounts can now be marked as available any time or available with constraints (GIC, term deposit, corporate), and the overview shows cash available now separately from cash with constraints. Add credit limits to credit cards and lines of credit to see credit available. New Risk covered summary showing how many months of essentials your cash and credit could cover.

## 0.5.0 -- 2026-09-30

- Start without an account: Loonie opens a default profile you can secure later by signing up, and your data moves with it. New guided setup that explains what Loonie is for, adds several accounts at once and adapts to whether you use AI. Guru now answers open-ended questions with your AI instead of forcing them into built-in answers, and says how each reply was produced. Eleven new advisors: emergency fund, debt payoff, mortgage, major purchase, retirement, goal funding, investment drawdown, income reduction, net worth, financial independence and job loss. Clearer Guru logo.

## 0.4.0 -- 2026-09-30

- Meet Pilot: one searchable chat for quick entries, PDF statements, questions about your data and decisions. Multi-currency net worth with live exchange rates. Advisor packs that Pilot brings in with your consent, publishable from LocalAgents. Simpler navigation.

## 0.3.3 -- 2026-09-29

- No default account is created any more; the app refuses to attach to another copy of the engine; Google sign-in without setup steps

## 0.3.2 -- 2026-09-29

- Fix first-launch engine setup: works with newer Python versions, retries failed installs, and shows what went wrong

## 0.3.1 -- 2026-09-29

- Fix restoring backups and sign-in after restore; restore now applies immediately for the signed-in account only

## 0.3.0 -- 2026-09-29

- Multiple accounts, account chooser and Loonie Cloud sync

## 0.2.0 -- 2026-09-28

- New look: Loonie coin logo, light and dark themes, quick actions on the dashboard and a smoother setup tour. Blueprint Marketplace with per-blueprint data consent, run history and Blueprint Studio. Create your account on first launch and connect AI, Jev and Google Drive from Settings - no config files.



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
