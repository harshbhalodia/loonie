# Loonie

> Plan with purpose. Decide with clarity. Pivot with confidence.

Loonie is a private, local-first "Life OS" desktop app for Windows — track accounts, budgets,
goals and net worth, import bank statements, stress-test your finances with marketplace
blueprints, and get advice from AI that runs on your own computer. Your data never leaves your
machine unless you choose to connect an optional service.

**Website:** [loonie.ai](https://loonie.ai)

## Install

**Option 1 — Windows installer (recommended)**

1. Install [Python 3.11+](https://python.org/downloads/) if you don't have it (tick **Add to PATH**).
2. Download the latest installer from [`installer/`](installer/) (or from [loonie.ai](https://loonie.ai#download)) and run it.
3. Launch **Loonie** from the Start menu.

**Option 2 — one line in PowerShell** (installs Python for you if it's missing):

```powershell
irm https://raw.githubusercontent.com/harshbhalodia/loonie/main/install.ps1 | iex
```

## First launch

1. Loonie starts its private local engine. The very first launch can take a minute while it sets
   itself up — you'll see a "Starting…" screen.
2. **Create your account** — an email and password that live only on this computer.
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
- **Insights:** budget, risk, diversification, goal, investment and research advisor agents —
  they explain numbers Loonie already computed, never invent them.
- **Blueprint Marketplace:** free and premium stress-test blueprints (rate shock, job loss,
  market correction, inflation…). A consent screen lets you choose exactly which data categories
  each blueprint may use; every run is kept with the blueprint version so you can compare.
  **Blueprint Studio** lets you draft and test your own, no code required.
- **Decision Maker:** describe a decision and options; Jev picks the best fit for your profile.
  Add a free API key under **Settings → Decision Maker**.
- **Google Drive backup:** optional off-site backup & restore, set up under **Settings**.

## Staying up to date

Loonie checks for updates automatically. When one is available you'll see an **Update available**
pill in the header — click it, then **Update & restart now**. You can also check under
**Settings → Version & updates**. See [CHANGELOG.md](CHANGELOG.md) for what's new.

## Privacy & security

- All data lives in a private local database on your machine — never uploaded anywhere.
- Marketplace blueprints only receive the data categories you explicitly grant, enforced by the
  engine itself. Publishers never receive your data.
- AI features are opt-in; secrets you enter in Settings are never displayed back.
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
