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
3. Guru opens the guided setup in chat: it helps you choose your AI (built-in, your own, or just
   the numbers), then gets to know you one quick question at a time.

No config files to edit — everything is set up inside the app.

## Connecting AI (optional)

Every calculation in Loonie works without AI. **Loonie AI** (built-in) is the default from version 0.8.0:
Loonie's own model, **Loonie Guru**, fine-tuned for exactly what Guru does — understanding requests,
short grounded answers, advice from your numbers, research reviews and reading statements. The
installer includes its runtime; first use downloads the model and its vision encoder (about 6 GB)
from [Loonie's Hugging Face page](https://huggingface.co/harshbhalodia/loonie-guru-gguf), with no
financial data sent. Allow 8 GB of free disk space. It uses memory and processor only while Guru is
answering (it unloads about 20 seconds after the last answer). View progress, cancel or retry,
**Unload from memory** or **Delete model** under **Settings > AI model**. Once downloaded, built-in
inference works offline. CPU speed varies.

**Verified before it runs:** Loonie only ever installs files listed in a release signed with Loonie's
key. It checks the signature, the exact version, and every file's size and checksum, and never goes
back to an older version. Nothing else is downloaded as built-in AI.

**Gets better over time:** Loonie checks for a new model version at start-up and every 12 hours and
downloads it in the background (turn this off under **Settings > AI model**). The version you have
keeps answering until the new one is verified; then Guru switches by itself. **Check for updates**
looks right away.

**Upgrading from 0.7.x:** your data and settings carry over. The stock Gemma 4 model used by 0.7 is
removed to free its disk space, and Loonie downloads its own model once. LM Studio setups keep working.

Guru can retrieve computed financial facts through read-only tools. Statement extraction works
page by page, including scanned PDFs. Always review the extracted rows before applying them.

To use a model you run yourself, select **LM Studio** in Settings (any OpenAI-compatible server
address works), enter its model name, and save. This stops the built-in runtime. Existing saved
server settings are preserved when upgrading.

- **LM Studio:** Developer tab → Start server, then copy the model name.

## What's inside

- **Wealth:** accounts & net worth, monthly/yearly budgets with history, goals with on-track
  verdicts, CSV/PDF statement import with keyword rules, reminders, credit-card statements,
  scenario sandbox, watchlist & research topics.
- **Guru:** one assistant with two speeds. **Ask Guru** is for deep thinking: questions, advisors,
  stress tests and decisions. **Quick setup** (Guru memory) is instant: it fills things in and keeps
  what it knows in step with your real numbers. Every answer is tagged Quick or Deep and shows
  what it used; Guru asks inline when it is missing a fact; and **What Guru knows about you** lets
  you change or forget anything. Guru asks for your agreement before first use, works on several
  requests at once, and lets you pin answers you want to keep.
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
- AI can be disabled in Settings; Guru requires acceptance of its terms before use. Built-in
  inference stays on your computer. Model downloads contact Hugging Face and its delivery
  providers, which receive connection metadata. Secrets entered in Settings are never displayed back.
- Privacy-filtered backend errors and sampled feature usage are sent to Sentry in the United States
  by default. Financial records, statements, AI conversations, credentials and account identities
  are excluded from reports. Sentry receives connection metadata during delivery. Disable reporting
  under **Settings > Anonymous diagnostics**; this applies to all accounts on the installation.
- Each install generates its own random signing key.

## Requirements

- Windows 10/11 (macOS/Linux coming later)
- Python 3.11+
- Built-in AI: recommended 16 GB RAM, 8 GB free disk space, and internet for the initial model
  download. Performance varies by CPU; complex documents may need a stronger external model.
- Optional: LM Studio (or another OpenAI-compatible server) instead of built-in AI

## Built with

Loonie's agent and marketplace patterns are shared as open source in
[LocalAgents](https://localagents.ai).

## License

See [LICENSE](LICENSE).
