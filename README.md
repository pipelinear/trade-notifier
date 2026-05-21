# 🟦 Bloxware Trade Notifier V1

**Discord + Slack Roblox trade notifier — made by lomi**

Bloxware Trade Notifier is a local-only notifier for Roblox inbound trades. It can send rich Discord trade cards, detailed Slack alerts, optional Slack PNG panels, and it also has a built-in terminal trade panel so you can view trades without opening Discord or Slack.

---

## What it can do

### Trade scanning
- Scans current inbound Roblox trades.
- Sends every current inbound trade one-by-one on startup when initial scan is enabled.
- Keeps live checking after startup.
- Handles inaccessible/expired trades without crashing.
- Tracks declined/status changes locally while live mode is running.

### Discord
- Full rich embeds.
- You Give / You Receive sections.
- PNG image panels with item photos.
- Multiple Discord webhooks.
- Webhook routing:
  - inbound trades
  - declined/status-change trades
  - all trade notifications

### Slack
- Detailed text summaries with:
  - trade link
  - trader
  - profit/value difference
  - RAP difference
  - item names
  - RAP/value
  - demand/trend
  - projected/hyped/rare
- Optional advanced image upload so Slack can receive the PNG panels too.
- Slack is good for iPhone notifications.
- Discord is still best for the full visual layout.

### Terminal panel
- View current inbound trades directly from the program.
- View declined/status history.
- See profit, values, projected warnings, and trade links in the terminal.

### Safety
- `.env` is created locally if missing.
- The program asks you for missing setup info.
- No `.env`, webhooks, or saved state files are included in this zip.
- The script does not accept, decline, send, or counter trades.

---

## First setup

### 1. Install requirements

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
python notifier.py
```

### 3. Follow the built-in setup checklist

If there is no `.env`, Bloxware starts a first-run setup wizard:

1. A red joke screen says **"You've been hacked!"**
2. After Enter, it reveals it is kidding and explains that setup is missing.
3. It creates a local `.env`.
4. It walks you through the Roblox cookie, basic settings, and notification setup.
5. It validates the cookie against Roblox before continuing.
6. It shows progress bars as you complete each step.

Cookie format check:
- If the pasted value starts with Roblox's `.ROBLOSECURITY` warning prefix, it says **Cookie pasted!**
- If not, it tells you that the panel is not seeing the correct value.

The cookie is saved only locally in `.env`.

---


---

## Admin permission required

Bloxware now requires admin/root permissions before it runs.

### Windows setup

1. Press the **Windows key**.
2. Search **Terminal** or **Command Prompt**.
3. Right-click it.
4. Click **Run as administrator**.
5. Go to the notifier folder:

```bat
cd "C:\Users\nicky\Downloads\bloxware_trade_notifier_v17"
```

6. Run:

```bat
python notifier.py
```

You should see **Administrator:** in the terminal title bar.

### macOS / Linux

Run:

```bash
sudo python notifier.py
```

If you do not run it as admin, the program stops immediately and tells you how to fix it.

## Main menu

```text
1) Normal boot
2) Timed task
3) Trade panel
4) Settings
5) Discord setup guide
6) Slack setup guide
7) Contact
8) Exit
```

When you choose **Normal boot** or **Timed task**, it asks whether to send notifications to:

```text
1) Discord only
2) Slack only
3) Both Discord + Slack
```

---

## Discord setup

Use Discord for the full detailed view.

Inside Discord:
1. Create a channel like `#trade-alerts`.
2. Open channel settings.
3. Go to **Integrations → Webhooks**.
4. Create a webhook.
5. Copy the webhook URL.

Inside Bloxware:
```text
Settings → Manage Discord webhooks
```

You can route each webhook to:
```text
Inbound trades
Declined/status-change trades
All trade notifications
```

Example:
```text
#trade-alerts       → inbound
#trade-declined     → declined
#trade-archive      → all
```

---

## Slack setup

Use Slack for iPhone-friendly alerts.

### Basic Slack text alerts

1. Create/sign into any Slack account.
2. Create/open any workspace. The name does not matter.
3. Create a public channel like `#trade-alerts`.
4. Open `https://api.slack.com/apps`.
5. Click **Create an App**.
6. Choose **From scratch**.
7. Name it `Bloxware Trade Notifier`.
8. Choose your workspace.
9. Click **Create App**.
10. Open **Incoming Webhooks**.
11. Turn **Activate Incoming Webhooks** on.
12. Click **Add New Webhook to Workspace**.
13. Pick your public alert channel.
14. Click **Allow**.
15. Copy the URL that starts with `https://hooks.slack.com/services/`.
16. In Bloxware:
```text
Settings → Slack setup/notifications
```
17. Enable Slack, paste the URL, and send the test.

Test message:
```text
✅ Lomi's Notifier is active!
```

### Advanced Slack image upload

Slack webhooks are great for text, but local PNG image uploads require a Slack bot token and channel ID.

To enable image upload:
```text
Settings → Slack setup/notifications → Enable Slack PNG image upload
```

You need:
- Slack bot token, starts with `xoxb-`
- Slack channel ID, usually starts with `C`

The app uses `slack_sdk` for this, included in `requirements.txt`.

---

## High alert

High alert is for trades that look clearly profitable.

If the estimated value gain reaches your threshold and the incoming side has **no projected items**, Bloxware sends multiple extra pings.

If the trade is a big win but the incoming side is projected, the summary warns you clearly, like:

```text
Big win on paper, but the incoming side has projected item(s). Decline this trade unless you manually verify it first.
```

---

## Files safe for GitHub

Safe to upload:
```text
README.md
notifier.py
requirements.txt
.env.example
.gitignore
```

Do not upload:
```text
.env
webhooks.json
seen_trades.json
active_inbound_ids.json
declined_trade_history.json
```

---

## .env example

```env
ROBLOSECURITY=put_your_roblox_cookie_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
DISCORD_USER_ID=
CHECK_INTERVAL_SECONDS=60
LOCAL_TIMEZONE=America/Los_Angeles
ADD_UNVALUED_TO_TOTAL=true
HIGH_VALUE_ALERT_THRESHOLD=500
HIGH_VALUE_ALERT_REPEAT=3
INITIAL_SCAN_NOTIFY=true
SLACK_ENABLED=false
SLACK_WEBHOOK_URL=
SLACK_UPLOAD_IMAGES=false
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

made by lomi


---

## V14 updates

- First-run setup has a red joke screen followed by a required typed confirmation.
- Confirmation phrase is: `yes lomi, create my env file`.
- Cookie input is visible while typing/pasting.
- Cookie format is checked first, then validated with Roblox immediately.
- Trade detail fetch retries up to 3 times before skipping.
- Terrible trades under 40% of your outgoing value get a clear warning.
- Terminal trade panel can now analyze a selected inbound trade.
- Analysis uses available Roblox/Rolimons data, value math, projected risk, demand/trend, and current value comparison bars.


---

## V15 updates

- Live mode uses one updating progress line instead of stacking a new bar every check.
- You can start the scanner in the background and return to the home menu.
- First-run red screen fills the terminal and runs longer diagnostic-style output.
- Setup confirmation uses a neutral typed phrase: `yes lomi, i have read your message. please create the env file for me`
- Setup progress no longer duplicates the subtitle line.
- Slack test asks whether the message actually arrived and lets you paste a different webhook URL if it did not.
- Slack/Discord send status is reported separately.
- Trade panel description now clearly includes analytics.
- Trade analysis is paged: verdict/math, item breakdown, and graphs/links.
- Requirements are checked before the setup wizard.


---

## V16 updates

- Setup uses one progress bar at the top only.
- Setup asks for an area code and maps it to a timezone.
- Live mode keeps one updating progress line instead of stacking bars.
- Background mode shows an active scanner note on the home menu.
- Added a Background Tracker page to view active scanner logs.
- Slack test asks if the message arrived and lets you enter a new webhook if not.
- Slack image upload remains supported through Slack bot token + channel ID.
- Analysis page attempts a best-effort public history sparkline if public chart data is accessible.

---

## V17 update

- The notifier now requires admin/root permissions to run.
- If it is not run as admin, it stops immediately with a clear tutorial.
- README now includes a simple Windows and macOS/Linux admin setup guide.
