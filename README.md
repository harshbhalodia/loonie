# Loonie

> Plan with purpose. Decide with clarity. Pivot with confidence.

Loonie is a private, local-first "Life OS" desktop app for Windows — track accounts, budgets,
goals and net worth, import bank statements, stress-test your finances with marketplace
blueprints, and get advice from AI that runs on your own computer. Your financial data stays on
your machine unless you choose to connect an optional service. Installed builds send privacy-filtered
diagnostics to Sentry by default; reporting can be disabled in Settings.

**Website:** [loonie.ai](https://loonie.ai)

## Install

1. Install [Python 3.11+](https://python.org/downloads/) if you don't have it (tick **Add to PATH**).
2. Download the latest installer from [`installer/`](installer/) (or from [loonie.ai](https://loonie.ai#download)) and run it.
   Use the `.exe` for a normal install, or the `.msi` if you deploy with Windows tools.
3. Launch **Loonie** from the Start menu. It opens full screen and keeps the taskbar visible.

## First launch

1. Loonie starts its private local engine. The very first launch can take a minute while it sets
   itself up — you'll see a "Starting…" screen.
2. **Create your account** — an email and password. Each account has its own separate workspace,
   so several people can share one PC. Next time, pick your account from the chooser (or sign in
   as a different user).
3. A short guided tour helps you add a goal and an account, and optionally connect an AI model.

No config files to edit — everything is set up inside the app.

## Connecting AI (optional)

Every calculation in Loonie works without AI. To unlock advisor agents, marketplace stress tests
and PDF statement import, go to **Settings → AI model**, pick **LM Studio** or **Ollama** (or any
OpenAI-compatible server), enter the model name, and click **Save & test connection**.

- **LM Studio:** Developer tab → Start server, then copy the model name.
- **Ollama:** `ollama pull llama3.1` — it serves automatically.

## What's inside

- **Wealth:** accounts & net worth, monthly/yearly budgets with history, goals with on-track
  verdicts, CSV/PDF statement import with keyword rules, reminders, credit-card statements,
  scenario sandbox, watchlist & research topics.
- **Guru:** your guide across every part of your life. Ask in plain words, drop a statement, or
  run a stress test with the right advisor. Guru asks for your agreement before first use, works
  on several requests at once, and lets you pin answers you want to keep.
- **Insights:** budget, risk, diversification, goal, investment and research advisor agents —
  they explain numbers Loonie already computed, never invent them.
- **Blueprint Marketplace:** free and premium stress-test blueprints (rate shock, job loss,
  market correction, inflation…). A consent screen lets you choose exactly which data categories
  each blueprint may use; every run is kept with the blueprint version so you can compare.
  **Blueprint Studio** lets you draft and test your own, no code required.
- **Decision Maker:** describe a decision and options; Jev picks the best fit for your profile.
  Add a free API key under **Settings → Decision Maker**.
- **Google Drive backup:** optional off-site backup & restore, set up under **Settings**.
- **Loonie Cloud sync:** optional. Link an account under **Settings → Loonie Cloud** and its data
  syncs automatically across your devices.

## Staying up to date

Loonie checks for updates automatically. When one is available you'll see an **Update available**
pill in the header — click it, then **Update & restart now**. You can also check under
**Settings → Version & updates**. See [CHANGELOG.md](CHANGELOG.md) for what's new.

## Privacy & security

- Your data stays on your machine, in a separate folder per account, unless you choose to link
  Loonie Cloud or Google Drive backup.
- Marketplace blueprints only receive the data categories you explicitly grant, enforced by the
  engine itself. Publishers never receive your data.
- AI features are opt-in; secrets you enter in Settings are never displayed back.
- Privacy-filtered backend errors and sampled feature usage are sent to Sentry in the United States
  by default. Financial records, statements, AI conversations, credentials and account identities
  are excluded from reports. Sentry receives connection metadata during delivery. Disable reporting
  under **Settings > Anonymous diagnostics**; this applies to all accounts on the installation.
- Each install generates its own random signing key.

## Requirements

- Windows 10/11 (macOS/Linux coming later)
- Python 3.11+
- Optional: LM Studio, Ollama or another local model server for AI features

## Built with

Loonie's agent and marketplace patterns are shared as open source in
[LocalAgents](https://localagents.ai).

## License

See [LICENSE](LICENSE).
