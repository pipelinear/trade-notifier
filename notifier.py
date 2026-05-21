"""
Bloxware Trade Notifier V17

Local-only read-only Roblox trade notifier.

Does:
- Checks inbound trades
- Sends Discord notifications
- Uses Rolimons itemdetails
- Generates readable PNG item panels
- Supports multiple active/inactive webhooks
- Has a terminal preflight checklist, menu, and countdown bars

Does NOT:
- Accept trades
- Decline trades
- Send trades
- Counter trades
- Print or send your Roblox cookie
"""

from __future__ import annotations

import getpass
import importlib.util
import io
import json
import os
import ctypes
import random
import shutil
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from requests.exceptions import HTTPError
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont


INBOUND_TRADES_URL = "https://trades.roblox.com/v1/trades/inbound?sortOrder=Desc&limit=25"
TRADE_DETAILS_URL = "https://trades.roblox.com/v1/trades/{trade_id}"
AUTHENTICATED_USER_URL = "https://users.roblox.com/v1/users/authenticated"
ROLIMONS_ITEMDETAILS_URL = "https://www.rolimons.com/itemapi/itemdetails"
ASSET_THUMBNAILS_URL = "https://thumbnails.roblox.com/v1/assets"
USER_HEADSHOT_URL = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
ROBLOX_PROFILE_URL = "https://www.roblox.com/users/{user_id}/profile"
TRADE_PAGE_URL = "https://www.roblox.com/trades#/{trade_id}"
CONTACT_URL = "https://discord.gg/d6gm5j5eG8"

ENV_FILE = Path(".env")
WEBHOOKS_FILE = Path("webhooks.json")
SEEN_FILE = Path("seen_trades.json")
ACTIVE_INBOUND_FILE = Path("active_inbound_ids.json")
DECLINED_HISTORY_FILE = Path("declined_trade_history.json")
ROBLOSECURITY_PREFIX = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items."
BACKGROUND_THREADS: List[threading.Thread] = []
BACKGROUND_STATUS = {
    "active": False,
    "mode": "",
    "providers": "",
    "checks": 0,
    "sent": 0,
    "last": "not started",
}
BACKGROUND_LOGS: List[str] = []


# ---------- terminal UI ----------

class Term:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


def enable_ansi() -> None:
    # Helps Windows terminals handle ANSI colors.
    if os.name == "nt":
        os.system("")


def c(text: str, color: str) -> str:
    return f"{color}{text}{Term.RESET}"



def require_admin() -> None:
    """
    Require admin/root permissions before running Bloxware.

    Windows:
      Run Terminal / Command Prompt as Administrator.

    macOS/Linux:
      Run with sudo.
    """
    try:
        if os.name == "nt":
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            is_admin = os.geteuid() == 0
    except Exception:
        is_admin = False

    if not is_admin:
        print()
        print("ADMIN PERMISSION REQUIRED")
        print("Bloxware Trade Notifier must be run as Administrator.")
        print()
        print("macOS {or linux!}:")
        print("  1) open the directory")
        print("  2) run sudo python notifier.py")
        print("Windows")
        print("  1) Kill yourself if you can't run this yourself as admin in windows")
        raise SystemExit(1)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def section(title: str, subtitle: str = "") -> None:
    print()
    print(c(f"╭─ {title}", Term.BOLD + Term.CYAN))
    if subtitle:
        print(c(f"│  {subtitle}", Term.GRAY))
    print(c("╰" + "─" * 58, Term.CYAN))


def print_banner() -> None:
    banner = r"""
██████╗ ██╗      ██████╗ ██╗  ██╗██╗    ██╗ █████╗ ██████╗ ███████╗
██╔══██╗██║     ██╔═══██╗╚██╗██╔╝██║    ██║██╔══██╗██╔══██╗██╔════╝
██████╔╝██║     ██║   ██║ ╚███╔╝ ██║ █╗ ██║███████║██████╔╝█████╗  
██╔══██╗██║     ██║   ██║ ██╔██╗ ██║███╗██║██╔══██║██╔══██╗██╔══╝  
██████╔╝███████╗╚██████╔╝██╔╝ ██╗╚███╔███╔╝██║  ██║██║  ██║███████╗
╚═════╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
"""
    print(c(banner, Term.CYAN))
    print(c("discord trade notifier", Term.BOLD + Term.WHITE) + "  " + c("made by lomi", Term.MAGENTA))


def print_features() -> None:
    section("Feature stack", "what this run can do")
    features = [
        "read inbound Roblox trades only",
        "rapid startup scan or ignore old inbound trades",
        "Rolimons RAP / value / demand / trend checks",
        "projected, hyped, and rare warnings",
        "Discord support with full embeds and PNG item panels",
        "Slack support with detailed text summaries for phone/workspace alerts",
        "multiple Discord webhook manager with event routing",
        "high-value clean-deal multi-ping alerts",
        "timed task mode",
    ]
    for feature in features:
        print(f"  {c('●', Term.GREEN)} {feature}")


def pause() -> None:
    input(c("\nPress Enter to continue...", Term.GRAY))


def progress_line(label: str, current: int, total: int, width: int = 28, color: str = Term.CYAN) -> None:
    total = max(total, 1)
    current = min(current, total)
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = int((current / total) * 100)
    print(f"  {label:<24} {color}{bar}{Term.RESET}  {pct:>3}%")


def countdown_bar(seconds: int, checks_ran: int = 0) -> None:
    seconds = max(1, seconds)
    width = 30
    for remaining in range(seconds, 0, -1):
        done = seconds - remaining
        filled = int(width * done / seconds)
        bar = "█" * filled + "░" * (width - filled)
        line = (
            f"  {c('Next check', Term.BOLD + Term.WHITE)} "
            f"{Term.MAGENTA}{bar}{Term.RESET}  {remaining:>3}s left  "
            f"{c('|', Term.GRAY)} checks ran: {checks_ran:<4}"
        )
        sys.stdout.write("\r" + line + "\033[K")
        sys.stdout.flush()
        time.sleep(1)

    done_line = (
        f"  {c('Checking now', Term.BOLD + Term.GREEN)} "
        f"{'█' * width}  {c('|', Term.GRAY)} checks ran: {checks_ran:<4}"
    )
    sys.stdout.write("\r" + done_line + "\033[K")
    sys.stdout.flush()


def status_line(ok: bool, label: str, value: str = "") -> None:
    icon = c("✓", Term.GREEN) if ok else c("!", Term.YELLOW)
    print(f"  {icon} {label:<26} {c(value, Term.GRAY) if value else ''}")


# ---------- env / webhooks ----------

def valid_discord_webhook_format(url: str) -> bool:
    return url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")


def valid_slack_webhook_format(url: str) -> bool:
    return url.startswith("https://hooks.slack.com/services/")


def read_env_file() -> Dict[str, str]:
    load_dotenv(ENV_FILE, override=True)
    return {
        "ROBLOSECURITY": os.getenv("ROBLOSECURITY", "").strip(),
        "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        "DISCORD_USER_ID": os.getenv("DISCORD_USER_ID", "").strip(),
        "CHECK_INTERVAL_SECONDS": os.getenv("CHECK_INTERVAL_SECONDS", "60").strip(),
        "LOCAL_TIMEZONE": os.getenv("LOCAL_TIMEZONE", "America/Los_Angeles").strip(),
        "ADD_UNVALUED_TO_TOTAL": os.getenv("ADD_UNVALUED_TO_TOTAL", "true").strip(),
        "HIGH_VALUE_ALERT_THRESHOLD": os.getenv("HIGH_VALUE_ALERT_THRESHOLD", "500").strip(),
        "HIGH_VALUE_ALERT_REPEAT": os.getenv("HIGH_VALUE_ALERT_REPEAT", "3").strip(),
        "INITIAL_SCAN_NOTIFY": os.getenv("INITIAL_SCAN_NOTIFY", "true").strip(),
        "SLACK_ENABLED": os.getenv("SLACK_ENABLED", "false").strip(),
        "SLACK_WEBHOOK_URL": os.getenv("SLACK_WEBHOOK_URL", "").strip(),
        "SLACK_UPLOAD_IMAGES": os.getenv("SLACK_UPLOAD_IMAGES", "false").strip(),
        "SLACK_BOT_TOKEN": os.getenv("SLACK_BOT_TOKEN", "").strip(),
        "SLACK_CHANNEL_ID": os.getenv("SLACK_CHANNEL_ID", "").strip(),
    }


def write_env_file(values: Dict[str, str]) -> None:
    ordered = [
        "ROBLOSECURITY",
        "DISCORD_WEBHOOK_URL",
        "DISCORD_USER_ID",
        "CHECK_INTERVAL_SECONDS",
        "LOCAL_TIMEZONE",
        "ADD_UNVALUED_TO_TOTAL",
        "HIGH_VALUE_ALERT_THRESHOLD",
        "HIGH_VALUE_ALERT_REPEAT",
        "INITIAL_SCAN_NOTIFY",
        "SLACK_ENABLED",
        "SLACK_WEBHOOK_URL",
        "SLACK_UPLOAD_IMAGES",
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
    ]
    lines = []
    for key in ordered:
        lines.append(f"{key}={values.get(key, '')}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_env_values() -> Dict[str, str]:
    return {
        "ROBLOSECURITY": "",
        "DISCORD_WEBHOOK_URL": "",
        "DISCORD_USER_ID": "",
        "CHECK_INTERVAL_SECONDS": "60",
        "LOCAL_TIMEZONE": "America/Los_Angeles",
        "ADD_UNVALUED_TO_TOTAL": "true",
        "HIGH_VALUE_ALERT_THRESHOLD": "500",
        "HIGH_VALUE_ALERT_REPEAT": "3",
        "INITIAL_SCAN_NOTIFY": "true",
        "SLACK_ENABLED": "false",
        "SLACK_WEBHOOK_URL": "",
        "SLACK_UPLOAD_IMAGES": "false",
        "SLACK_BOT_TOKEN": "",
        "SLACK_CHANNEL_ID": "",
    }


def load_webhooks(env_values: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    env_values = env_values or read_env_file()

    valid_events = {"inbound", "declined", "all"}

    if WEBHOOKS_FILE.exists():
        try:
            data = json.loads(WEBHOOKS_FILE.read_text(encoding="utf-8"))
            hooks = data.get("webhooks", [])
            if isinstance(hooks, list):
                cleaned = []
                for hook in hooks:
                    if not isinstance(hook, dict):
                        continue
                    event = str(hook.get("event") or hook.get("type") or "inbound").lower().strip()
                    if event not in valid_events:
                        event = "inbound"
                    cleaned.append({
                        "name": str(hook.get("name") or "Webhook"),
                        "url": str(hook.get("url") or ""),
                        "active": bool(hook.get("active", True)),
                        "event": event,
                    })
                return cleaned
        except json.JSONDecodeError:
            pass

    # First-run migration from .env webhook into webhooks.json.
    url = env_values.get("DISCORD_WEBHOOK_URL", "")
    hooks = []
    if valid_discord_webhook_format(url):
        hooks = [{"name": "Main inbound", "url": url, "active": True, "event": "inbound"}]
        save_webhooks(hooks)
    return hooks


def save_webhooks(webhooks: List[Dict[str, Any]]) -> None:
    WEBHOOKS_FILE.write_text(
        json.dumps({"webhooks": webhooks}, indent=2),
        encoding="utf-8",
    )


def active_webhooks(webhooks: List[Dict[str, Any]], event: Optional[str] = None) -> List[Dict[str, Any]]:
    active = [
        w for w in webhooks
        if w.get("active") and valid_discord_webhook_format(str(w.get("url", "")))
    ]

    if event is None:
        return active

    event = event.lower().strip()
    return [
        w for w in active
        if str(w.get("event", "inbound")).lower().strip() in (event, "all")
    ]


def prompt_bool(message: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{message} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes", "true", "1")



def choose_provider_mode(default: str = "both") -> str:
    print()
    print(c("Notification provider", Term.BOLD + Term.BLUE))
    print("  1) Discord only")
    print("  2) Slack only")
    print("  3) Both Discord + Slack")
    raw = input(f"Choose provider [default {default}]: ").strip()

    if raw == "1":
        return "discord"
    if raw == "2":
        return "slack"
    return "both"


def provider_allows(settings: Dict[str, Any], provider: str) -> bool:
    mode = str(settings.get("provider_mode", "both")).lower()
    return mode == "both" or mode == provider



def red_alert_screen() -> None:
    diagnostic_lines = [
        "python runtime located",
        "checking local notifier directory",
        "reading requirements map",
        "probing .env presence",
        "env file missing",
        "webhook registry unavailable",
        "seen trade cache unavailable",
        "cookie validation blocked",
        "roblox session not initialized",
        "rolimons cache cold",
        "trade watcher paused",
        "setup wizard required",
        "local-only mode confirmed",
        "no external upload performed",
    ]

    size = shutil.get_terminal_size((100, 28))
    width = max(80, size.columns)
    height = max(24, size.lines)
    red_bg = "\033[41m"
    white = "\033[97m"
    bold = "\033[1m"
    reset = Term.RESET

    for frame in range(34):
        lines = []
        lines.append(("YOU'VE BEEN HACKED!" if frame % 2 == 0 else "LOCAL SECURITY EVENT").center(width))
        lines.append(("diagnostic stream: missing setup profile").center(width))
        lines.append("".center(width))
        for _ in range(height - 6):
            code = "".join(random.choice("0123456789abcdef") for _ in range(20))
            msg = random.choice(diagnostic_lines)
            pulse = random.choice(["TRACE", "SCAN", "WARN", "LOCAL", "SETUP"])
            line = f" {pulse:<5} [{code}] {msg}"
            lines.append(line[:width].ljust(width))
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.write(red_bg + white + bold + "\n".join(line.ljust(width) for line in lines[:height]) + reset)
        sys.stdout.flush()
        time.sleep(0.075)

    sys.stdout.write("\033[H\033[2J")
    final_lines = [
         "DONT TURN OFF THIS PC".center(width),
        "".center(width),
        "you're screwed, dont even try changing passwords".center(width),
        "if you try closing me, your bios wont even boot".center(width),
	"if you even try clicking ENTER your roblox account will be immediately deactivated.".center(width),
	"ever guessed why i needed admin permissions?".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
" ".center(width),
"try to ENTER any of your passwords now. its encrypted".center(width),
"better luck next time smart one".center(width),
    ]
    sys.stdout.write(red_bg + white + bold + "\n".join(line.ljust(width) for line in final_lines) + reset)
    sys.stdout.flush()
    input()
    sys.stdout.write(reset + "\033[H\033[2J")
    sys.stdout.flush()



def area_code_to_timezone(area_code: str) -> str:
    """
    Simple area-code-to-timezone helper for setup.
    It is intentionally conservative: unknown area codes fall back to Pacific.
    Users can still edit LOCAL_TIMEZONE later in .env if needed.
    """
    area = "".join(ch for ch in str(area_code) if ch.isdigit())

    pacific = {
        "209", "213", "279", "310", "323", "341", "350", "408", "415", "424", "442",
        "510", "530", "559", "562", "619", "626", "628", "650", "657", "661", "669",
        "707", "714", "747", "760", "805", "818", "831", "840", "858", "909", "916",
        "925", "949", "951", "253", "360", "425", "509", "564", "206", "503", "541",
        "971", "458", "702", "725", "775",
    }
    mountain = {
        "303", "719", "720", "970", "983", "480", "520", "602", "623", "928", "505",
        "575", "208", "986", "406", "307", "385", "435", "801",
    }
    central = {
        "205", "251", "256", "334", "659", "938", "217", "224", "309", "312", "331",
        "447", "464", "618", "630", "708", "730", "773", "779", "815", "847", "872",
        "219", "260", "317", "463", "574", "765", "812", "930", "319", "515", "563",
        "641", "712", "316", "620", "785", "913", "270", "364", "502", "606", "859",
        "225", "318", "337", "504", "985", "218", "320", "507", "612", "651", "763",
        "952", "228", "601", "662", "769", "314", "417", "557", "573", "636", "660",
        "816", "975", "308", "402", "531", "405", "539", "572", "580", "918", "210",
        "214", "254", "281", "325", "346", "361", "409", "430", "432", "469", "512",
        "682", "713", "726", "737", "806", "817", "830", "832", "903", "915", "936",
        "940", "945", "956", "972", "979", "262", "414", "534", "608", "715", "920",
    }

    if area in pacific:
        return "America/Los_Angeles"
    if area in mountain:
        return "America/Denver"
    if area in central:
        return "America/Chicago"
    return "America/New_York"


def log_background(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    BACKGROUND_LOGS.append(line)
    del BACKGROUND_LOGS[:-80]
    BACKGROUND_STATUS["last"] = line

def setup_progress_header(step: int, total: int = 4) -> None:
    width = 28
    filled = int(width * step / max(total, 1))
    bar = "█" * filled + "░" * (width - filled)
    pct = int((step / max(total, 1)) * 100)
    print(c(f"setup progress [{bar}] {pct}%", Term.CYAN))


def require_setup_phrase() -> None:
    # Kept intentionally neutral and non-weird for a public tool.
    phrase = "yes lomi, i have read your message. please create the env file for me"
    print()
    print(c("To continue, type this exactly:", Term.YELLOW))
    print(c(f"  {phrase}", Term.BOLD + Term.WHITE))
    while True:
        typed = input(c("\nType confirmation: ", Term.CYAN)).strip()
        if typed == phrase:
            return
        print(c("Not quite. Type the exact sentence so we know you actually read this.", Term.RED))


def setup_intro_screen() -> None:
    clear_screen()
    print_banner()
    setup_progress_header(0, 4)
    print()
    print(c("GOTCHA", Term.BOLD + Term.GREEN))
    print(c("Anyway, first-time setup detected.", Term.BOLD + Term.WHITE))
    print()
    print("  We see that you have not set up the needed information for this tool to work.")
    print("  We created a local .env file for you.")
    print("  You will paste the needed info here, and Bloxware will save it into .env")
    print("  so the notifier works next time.")
    print()
    print(c("  Keep .env private. This is like my-eyes-only except your Roblox account is on the line.", Term.RED))
    require_setup_phrase()


def cookie_tutorial() -> None:
    clear_screen()
    print_banner()
    setup_progress_header(1, 4)
    section("Step 1 of 4 — Roblox cookie", "only use this for your own account")

    print(c("First, we need your .ROBLOSECURITY cookie.", Term.BOLD + Term.WHITE))
    print()
    print("  How to find it:")
    print("  1) Log into Roblox in your browser.")
    print("  2) Open Developer Tools.")
    print("  3) Go to the Application tab.")
    print("  4) Under Storage, find Cookies.")
    print("  5) Click roblox.com.")
    print("  6) Under the Name column, find .ROBLOSECURITY.")
    print("  7) Copy the Value it holds and paste it into this panel.")
    print()
    print(c("  Warning: this cookie works like a login token. Never share it.", Term.RED))
    print()


def cookie_shape_ok(cookie: str) -> bool:
    return cookie.strip().startswith(ROBLOSECURITY_PREFIX)


def prompt_for_cookie_until_valid(values: Dict[str, str]) -> Dict[str, str]:
    while True:
        cookie_tutorial()
        cookie = input("Paste .ROBLOSECURITY value: ").strip()

        if cookie_shape_ok(cookie):
            print(c("\nCookie pasted!", Term.GREEN))
        else:
            print(c("\nThat is not what this panel is looking for.", Term.RED))
            print("  The value should start with:")
            print(c("  _|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.", Term.GRAY))
            print()
            retry = prompt_bool("Try pasting the cookie again?", True)
            if retry:
                continue
            return values

        print(c("Validating cookie with Roblox immediately...", Term.BLUE))
        try:
            test_session = make_roblox_session(cookie)
            me = fetch_authenticated_user(test_session)
            print(c(f"Cookie validated. Logged in as {me.get('displayName')} (@{me.get('name')}).", Term.GREEN))
            values["ROBLOSECURITY"] = cookie
            write_env_file(values)
            pause()
            return values
        except Exception as error:
            print(c(f"Cookie format looked right, but Roblox rejected it: {error}", Term.RED))
            print("  Try copying the full cookie value again.")
            retry = prompt_bool("Try again?", True)
            if not retry:
                return values


def prompt_for_basic_settings(values: Dict[str, str]) -> Dict[str, str]:
    clear_screen()
    print_banner()
    setup_progress_header(2, 4)
    section("Step 2 of 4 — Basic settings", "fast defaults, easy to change later")
    print("  These are safe defaults. Press Enter to keep them.")
    print()

    interval = input(f"Check interval seconds [{values.get('CHECK_INTERVAL_SECONDS', '60')}]: ").strip()
    if interval:
        try:
            values["CHECK_INTERVAL_SECONDS"] = str(max(15, int(interval)))
        except ValueError:
            print(c("Invalid interval, keeping old value.", Term.YELLOW))

    print()
    print("  Timezone setup is now easier:")
    print("  Type your phone area code, like 90210, 310, 212, etc.")
    print("  Bloxware maps it to a timezone for prettier trade timestamps.")
    area = input("Area code [90210]: ").strip() or "90210"
    values["LOCAL_TIMEZONE"] = area_code_to_timezone(area)
    print(c(f"Timezone set to {values['LOCAL_TIMEZONE']} from area code {area}.", Term.GREEN))

    initial = prompt_bool("Send current inbound trades on startup?", values.get("INITIAL_SCAN_NOTIFY", "true").lower() in ("true", "1", "yes", "y"))
    values["INITIAL_SCAN_NOTIFY"] = "true" if initial else "false"

    write_env_file(values)
    pause()
    return values


def prompt_for_notification_setup(values: Dict[str, str]) -> Dict[str, str]:
    clear_screen()
    print_banner()
    setup_progress_header(3, 4)
    section("Step 3 of 4 — Notifications", "Discord, Slack, or both")
    print("  You can skip these now and add them later in Settings.")
    print()

    hooks = load_webhooks(values)

    if prompt_bool("Add a Discord inbound webhook now?", True):
        while True:
            print()
            print("  Discord webhook guide:")
            print("  1) Open Discord channel settings.")
            print("  2) Go to Integrations → Webhooks.")
            print("  3) Create webhook and copy the URL.")
            print()
            url = input("Discord webhook URL: ").strip()
            if not url:
                break
            if not valid_discord_webhook_format(url):
                print(c("That does not look like a Discord webhook URL.", Term.RED))
                again = prompt_bool("Try again?", True)
                if again:
                    continue
                break
            hooks.append({"name": "Inbound Alerts", "url": url, "active": True, "event": "inbound"})
            save_webhooks(hooks)
            values["DISCORD_WEBHOOK_URL"] = url
            print(c("Discord webhook saved.", Term.GREEN))
            break

    if prompt_bool("Set up Slack text alerts now?", False):
        print()
        print("  Slack quick guide:")
        print("  1) Create or open any Slack workspace.")
        print("  2) Make a public channel like #trade-alerts.")
        print("  3) Go to https://api.slack.com/apps.")
        print("  4) Create an app From scratch.")
        print("  5) Enable Incoming Webhooks and copy the hooks.slack.com URL.")
        print()
        url = input("Slack Incoming Webhook URL: ").strip()
        if valid_slack_webhook_format(url):
            values["SLACK_ENABLED"] = "true"
            values["SLACK_WEBHOOK_URL"] = url
            print(c("Slack webhook saved.", Term.GREEN))
        elif url:
            print(c("That does not look like a Slack Incoming Webhook URL.", Term.RED))

    write_env_file(values)
    pause()
    return values


def first_run_setup_wizard(values: Dict[str, str]) -> Dict[str, str]:
    red_alert_screen()
    setup_intro_screen()
    values = prompt_for_cookie_until_valid(values)
    values = prompt_for_basic_settings(values)
    values = prompt_for_notification_setup(values)

    clear_screen()
    print_banner()
    setup_progress_header(4, 4)
    section("Setup complete", "you can change anything later in Settings")
    print(c("  Bloxware is ready to open.", Term.GREEN))
    pause()
    return values


def ensure_env_ready() -> None:
    section("Preflight checklist", "checking local setup before the menu")

    first_run = not ENV_FILE.exists()
    values = read_env_file() if ENV_FILE.exists() else default_env_values()

    if first_run:
        write_env_file(values)
        values = first_run_setup_wizard(values)

    cookie_ok = bool(values["ROBLOSECURITY"]) and values["ROBLOSECURITY"] != "put_your_roblox_cookie_here" and cookie_shape_ok(values["ROBLOSECURITY"])
    status_line(ENV_FILE.exists(), ".env exists", str(ENV_FILE.resolve()))
    status_line(cookie_ok, "Roblox cookie", "set" if cookie_ok else "missing / invalid format")

    if not cookie_ok:
        values = prompt_for_cookie_until_valid(values)
        cookie_ok = bool(values["ROBLOSECURITY"]) and cookie_shape_ok(values["ROBLOSECURITY"])

    hooks = load_webhooks(values)
    active_count = len(active_webhooks(hooks, "inbound"))
    status_line(active_count > 0, "inbound Discord webhooks", str(active_count))

    status_line(True, "check interval", f"{values['CHECK_INTERVAL_SECONDS']}s")
    status_line(True, "initial scan flood", values["INITIAL_SCAN_NOTIFY"])

    slack_enabled = values.get("SLACK_ENABLED", "false").strip().lower() in ("true", "1", "yes", "y")
    slack_ok = not slack_enabled or valid_slack_webhook_format(values.get("SLACK_WEBHOOK_URL", ""))
    status_line(slack_ok, "Slack provider", "enabled" if slack_enabled else "off")
    print()


def settings_from_env() -> Dict[str, Any]:
    values = read_env_file()
    hooks = load_webhooks(values)

    try:
        interval = max(15, int(values["CHECK_INTERVAL_SECONDS"]))
    except ValueError:
        interval = 60

    try:
        alert_threshold = max(0, int(values["HIGH_VALUE_ALERT_THRESHOLD"]))
    except ValueError:
        alert_threshold = 500

    try:
        alert_repeat = max(1, min(5, int(values["HIGH_VALUE_ALERT_REPEAT"])))
    except ValueError:
        alert_repeat = 3

    return {
        "cookie": values["ROBLOSECURITY"],
        "discord_user_id": values["DISCORD_USER_ID"],
        "interval": interval,
        "timezone_name": values["LOCAL_TIMEZONE"] or "America/Los_Angeles",
        "add_unvalued_to_total": values["ADD_UNVALUED_TO_TOTAL"].strip().lower() in ("true", "1", "yes", "y"),
        "high_value_alert_threshold": alert_threshold,
        "high_value_alert_repeat": alert_repeat,
        "initial_scan_notify": values["INITIAL_SCAN_NOTIFY"].strip().lower() in ("true", "1", "yes", "y"),
        "webhooks": hooks,
        "slack_enabled": values["SLACK_ENABLED"].strip().lower() in ("true", "1", "yes", "y"),
        "slack_webhook_url": values["SLACK_WEBHOOK_URL"].strip(),
        "slack_upload_images": values.get("SLACK_UPLOAD_IMAGES", "false").strip().lower() in ("true", "1", "yes", "y"),
        "slack_bot_token": values.get("SLACK_BOT_TOKEN", "").strip(),
        "slack_channel_id": values.get("SLACK_CHANNEL_ID", "").strip(),
        "provider_mode": "both",
    }


def choose_discord_event(default: str = "inbound") -> str:
    print()
    print(c("Webhook event type", Term.BOLD + Term.BLUE))
    print("  1) Inbound trades")
    print("  2) Declined/status-change trades")
    print("  3) All trade notifications")
    raw = input(f"Choose event type [default {default}]: ").strip()

    if raw == "2":
        return "declined"
    if raw == "3":
        return "all"
    return "inbound"


def event_label(event: str) -> str:
    event = str(event or "inbound").lower().strip()
    if event == "declined":
        return "DECLINED"
    if event == "all":
        return "ALL"
    return "INBOUND"


def show_webhook_manager() -> None:
    while True:
        clear_screen()
        print_banner()
        section("Discord webhook manager", "route different trade events into different Discord channels")
        hooks = load_webhooks()

        if not hooks:
            print(c("  No Discord webhooks saved yet.", Term.YELLOW))
        else:
            for idx, hook in enumerate(hooks, start=1):
                active = c("ACTIVE", Term.GREEN) if hook.get("active") else c("INACTIVE", Term.GRAY)
                event = c(event_label(hook.get("event", "inbound")), Term.BLUE)
                url = str(hook.get("url", ""))
                safe_url = url[:42] + "..." if len(url) > 45 else url
                print(f"  {idx}. {c(hook.get('name', 'Webhook'), Term.BOLD + Term.WHITE):<24} {event:<18} {active:<18} {c(safe_url, Term.GRAY)}")

        print()
        print("  1) Add Discord webhook")
        print("  2) Remove Discord webhook")
        print("  3) Toggle active/inactive")
        print("  4) Change webhook event type")
        print("  5) Send test to active Discord webhooks")
        print("  6) Back")
        choice = input(c("\nChoose: ", Term.CYAN)).strip()

        if choice == "1":
            name = input("Name, like Inbound Alerts or Declined Trades: ").strip() or "Webhook"
            event = choose_discord_event("inbound")
            url = input("Discord webhook URL: ").strip()

            if not valid_discord_webhook_format(url):
                print(c("Invalid Discord webhook format. It should start with https://discord.com/api/webhooks/", Term.RED))
                pause()
                continue

            hooks.append({"name": name, "url": url, "active": True, "event": event})
            save_webhooks(hooks)

            # Keep .env fallback updated with newest webhook.
            values = read_env_file()
            values["DISCORD_WEBHOOK_URL"] = url
            write_env_file(values)

            print(c(f"Discord webhook added for {event_label(event)} notifications.", Term.GREEN))
            pause()

        elif choice == "2":
            try:
                index = int(input("Remove number: ").strip()) - 1
                removed = hooks.pop(index)
                save_webhooks(hooks)
                print(c(f"Removed {removed.get('name', 'webhook')}.", Term.GREEN))
            except Exception:
                print(c("Invalid number.", Term.RED))
            pause()

        elif choice == "3":
            try:
                index = int(input("Toggle number: ").strip()) - 1
                hooks[index]["active"] = not bool(hooks[index].get("active"))
                save_webhooks(hooks)
                print(c("Toggled.", Term.GREEN))
            except Exception:
                print(c("Invalid number.", Term.RED))
            pause()

        elif choice == "4":
            try:
                index = int(input("Change event type for number: ").strip()) - 1
                hooks[index]["event"] = choose_discord_event(str(hooks[index].get("event", "inbound")))
                save_webhooks(hooks)
                print(c("Webhook event type updated.", Term.GREEN))
            except Exception:
                print(c("Invalid number.", Term.RED))
            pause()

        elif choice == "5":
            payload = {"content": "✅ Lomi's Notifier is active!"}
            count = 0
            for hook in active_webhooks(hooks):
                try:
                    send_discord_webhook_to_url(hook["url"], payload)
                    count += 1
                except Exception as error:
                    print(c(f"Failed {hook.get('name')}: {error}", Term.RED))
            print(c(f"Sent test to {count} active Discord webhook(s).", Term.GREEN))
            pause()

        elif choice == "6":
            return



def show_slack_tutorial() -> None:
    clear_screen()
    print_banner()
    section("Slack tutorial", "quick phone alerts, detailed text summaries, and when to use each device")

    print(c("What Slack is for", Term.BOLD + Term.MAGENTA))
    print("  • iPhone: fastest way to get a push notification when a trade arrives.")
    print("  • PC/browser: easiest place to create the Slack app and copy the webhook.")
    print("  • Notifier panel: where you paste the webhook and test it.")
    print()
    print(c("Important", Term.BOLD + Term.YELLOW))
    print("  • Make any Slack account if you do not already have one.")
    print("  • The workspace/group name does not matter.")
    print("  • Public channels are easiest for setup. Private channels can work, but may require extra app permissions.")
    print()

    phases = [
        ("A. Create Slack basics", [
            "Create or sign into a Slack account.",
            "Create/open any workspace. The workspace name does not matter.",
            "Create a public channel like #trade-alerts or #trade-notifier.",
        ]),
        ("B. Create the Slack app on PC/browser", [
            "Open https://api.slack.com/apps.",
            "Click Create an App.",
            "Choose From scratch. Do not choose manifest.",
            "App name: Bloxware Trade Notifier.",
            "Choose your workspace.",
            "Click Create App.",
        ]),
        ("C. Turn on Incoming Webhooks", [
            "On the app settings page, click Incoming Webhooks in the left sidebar.",
            "Turn Activate Incoming Webhooks ON.",
            "Scroll down and click Add New Webhook to Workspace.",
            "Choose your public alert channel.",
            "Click Allow.",
            "Copy the URL starting with https://hooks.slack.com/services/.",
        ]),
        ("D. Paste into Bloxware", [
            "Return to this notifier.",
            "Open Settings → Slack setup/notifications.",
            "Enable Slack.",
            "Paste the webhook URL.",
            "Send the test message.",
            "On iPhone, allow Slack notifications for that channel.",
        ]),
    ]

    for title, steps in phases:
        print(c(title, Term.BOLD + Term.BLUE))
        for step in steps:
            print(f"  {c('›', Term.GREEN)} {step}")
        print()

    print(c("Test message: ✅ Lomi's Notifier is active!", Term.GREEN))
    print(c("Slack gets detailed text summaries. Discord gets the full image panels.", Term.GRAY))
    pause()


def show_slack_notifications_setup() -> None:
    values = read_env_file()

    clear_screen()
    print_banner()
    section("Slack setup / notifications", "enable detailed Slack alerts without changing Discord")

    print("  Slack sends detailed text alerts with the trade link, values, items, and projection notes.")
    print("  Optional advanced mode can upload the same PNG panels to Slack with a Slack bot token + channel ID.")
    print()

    enabled = prompt_bool(
        "Enable Slack notifications?",
        values.get("SLACK_ENABLED", "false").strip().lower() in ("true", "1", "yes", "y"),
    )
    values["SLACK_ENABLED"] = "true" if enabled else "false"

    if enabled:
        current = values.get("SLACK_WEBHOOK_URL", "")
        print(c("\nPaste your Slack Incoming Webhook URL.", Term.YELLOW))
        print(c("It should start with https://hooks.slack.com/services/", Term.GRAY))
        print(c("Need help? Back out and open Settings → Slack tutorial.", Term.GRAY))
        prompt = f"Slack webhook URL [{current[:35] + '...' if current else ''}]: " if current else "Slack webhook URL: "
        url = input(prompt).strip()

        if url:
            if valid_slack_webhook_format(url):
                values["SLACK_WEBHOOK_URL"] = url
                print(c("Slack webhook saved.", Term.GREEN))
            else:
                print(c("That does not look like a Slack Incoming Webhook URL.", Term.RED))

        if values.get("SLACK_WEBHOOK_URL"):
            if prompt_bool("Send Slack test message now?", True):
                while True:
                    try:
                        send_slack_message(values["SLACK_WEBHOOK_URL"], "✅ Lomi's Notifier is active!")
                        print(c("Slack test sent.", Term.GREEN))
                        if prompt_bool("Did the Slack test message arrive?", True):
                            print(c("Slack webhook confirmed.", Term.GREEN))
                            break
                        print(c("Paste a different Slack webhook URL.", Term.YELLOW))
                        new_url = input("New Slack webhook URL: ").strip()
                        if valid_slack_webhook_format(new_url):
                            values["SLACK_WEBHOOK_URL"] = new_url
                            continue
                        print(c("That does not look like a Slack Incoming Webhook URL.", Term.RED))
                        break
                    except Exception as error:
                        print(c(f"Slack test failed: {error}", Term.RED))
                        if not prompt_bool("Try a different Slack webhook URL?", True):
                            break
                        new_url = input("New Slack webhook URL: ").strip()
                        if valid_slack_webhook_format(new_url):
                            values["SLACK_WEBHOOK_URL"] = new_url
                            continue
                        print(c("That does not look like a Slack Incoming Webhook URL.", Term.RED))
                        break

        print()
        print(c("Optional Slack image upload", Term.BOLD + Term.MAGENTA))
        print("  Webhooks alone send detailed text. To send the same PNG panels to Slack, enable image upload with a Slack bot token.")
        print("  Skip this unless you want Slack to receive the PNG panels too.")
        values["SLACK_UPLOAD_IMAGES"] = "true" if prompt_bool(
            "Enable Slack PNG image upload?",
            values.get("SLACK_UPLOAD_IMAGES", "false").strip().lower() in ("true", "1", "yes", "y")
        ) else "false"

        if values["SLACK_UPLOAD_IMAGES"] == "true":
            token = getpass.getpass("Slack bot token (xoxb-...): ").strip()
            if token:
                values["SLACK_BOT_TOKEN"] = token
            channel = input("Slack channel ID, starts with C...: ").strip()
            if channel:
                values["SLACK_CHANNEL_ID"] = channel
            print(c("For image upload, make sure requirements are installed: pip install -r requirements.txt", Term.GRAY))

    write_env_file(values)
    pause()


def show_timing_settings() -> None:
    values = read_env_file()

    clear_screen()
    print_banner()
    section("Timing settings", "separate timing from Discord and Slack setup")

    print(f"  Current check interval: {c(values['CHECK_INTERVAL_SECONDS'] + ' seconds', Term.YELLOW)}")
    print(f"  Initial scan flood:     {c(values['INITIAL_SCAN_NOTIFY'], Term.YELLOW)}")
    print()

    print("  1) Change check interval")
    print("  2) Toggle startup initial scan flood")
    print("  3) Back")
    choice = input(c("\nChoose: ", Term.CYAN)).strip()

    if choice == "1":
        new_interval = input("New interval in seconds, minimum 15: ").strip()
        try:
            values["CHECK_INTERVAL_SECONDS"] = str(max(15, int(new_interval)))
            write_env_file(values)
            print(c("Interval updated.", Term.GREEN))
        except ValueError:
            print(c("Invalid number.", Term.RED))
        pause()

    elif choice == "2":
        values["INITIAL_SCAN_NOTIFY"] = "false" if values["INITIAL_SCAN_NOTIFY"].strip().lower() in ("true", "1", "yes", "y") else "true"
        write_env_file(values)
        print(c(f"Initial scan notify is now {values['INITIAL_SCAN_NOTIFY']}.", Term.GREEN))
        pause()


def show_high_alert_settings() -> None:
    values = read_env_file()

    clear_screen()
    print_banner()
    section("High alert settings", "extra pings for clean good trades")

    print("  High alert is for trades that look clearly profitable.")
    print("  If the estimated value gain reaches your threshold and the incoming side")
    print("  has no projected items, Bloxware sends extra pings so you notice it fast.")
    print("  Example: threshold 500 means +500 value or better gets treated as a good trade.")
    print()
    print(f"  Current gain threshold: {c(values['HIGH_VALUE_ALERT_THRESHOLD'], Term.YELLOW)}")
    print(f"  Current repeat pings:   {c(values['HIGH_VALUE_ALERT_REPEAT'], Term.YELLOW)}")
    print()

    new_threshold = input("Set clean-gain threshold value, like 500 or 1000: ").strip()
    try:
        values["HIGH_VALUE_ALERT_THRESHOLD"] = str(max(0, int(new_threshold)))
    except ValueError:
        print(c("Invalid threshold. Keeping old value.", Term.RED))

    new_repeat = input("How many extra alert pings? 1-5: ").strip()
    if new_repeat:
        try:
            values["HIGH_VALUE_ALERT_REPEAT"] = str(max(1, min(5, int(new_repeat))))
        except ValueError:
            print(c("Invalid repeat count. Keeping old value.", Term.RED))

    write_env_file(values)
    print(c("High alert settings updated.", Term.GREEN))
    pause()


def show_settings_menu() -> None:
    while True:
        clear_screen()
        print_banner()
        section("Settings hub", "Discord and Slack are separated so setup is easier")
        values = read_env_file()
        hooks = load_webhooks(values)

        inbound_count = len(active_webhooks(hooks, "inbound"))
        declined_count = len(active_webhooks(hooks, "declined"))
        slack_on = values.get("SLACK_ENABLED", "false").strip().lower() in ("true", "1", "yes", "y")

        print(c("Discord", Term.BOLD + Term.BLUE))
        print(f"  1) Manage Discord webhooks   inbound: {c(str(inbound_count), Term.GREEN)} / declined: {c(str(declined_count), Term.YELLOW)}")
        print()
        print(c("Slack", Term.BOLD + Term.MAGENTA))
        print("  2) Slack tutorial            step-by-step api.slack.com guide")
        print(f"  3) Slack setup/notifications current: {c('on' if slack_on else 'off', Term.GREEN if slack_on else Term.GRAY)}")
        print()
        print(c("Timing + alerts", Term.BOLD + Term.CYAN))
        print(f"  4) Timing settings           interval: {c(values['CHECK_INTERVAL_SECONDS'] + 's', Term.YELLOW)} / initial scan: {c(values['INITIAL_SCAN_NOTIFY'], Term.YELLOW)}")
        print(f"  5) High alert settings       threshold: {c(values['HIGH_VALUE_ALERT_THRESHOLD'], Term.YELLOW)}")
        print()
        print("  6) Back")

        choice = input(c("\nChoose: ", Term.CYAN)).strip()

        if choice == "1":
            show_webhook_manager()
        elif choice == "2":
            show_slack_tutorial()
        elif choice == "3":
            show_slack_notifications_setup()
        elif choice == "4":
            show_timing_settings()
        elif choice == "5":
            show_high_alert_settings()
        elif choice == "6":
            return


# ---------- state ----------

def load_seen_trade_ids() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return set(str(x) for x in data.get("seen_trade_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_trade_ids(seen: set[str]) -> None:
    SEEN_FILE.write_text(
        json.dumps({"seen_trade_ids": sorted(seen)}, indent=2),
        encoding="utf-8",
    )


def load_active_inbound_ids() -> set[str]:
    if not ACTIVE_INBOUND_FILE.exists():
        return set()
    try:
        data = json.loads(ACTIVE_INBOUND_FILE.read_text(encoding="utf-8"))
        return set(str(x) for x in data.get("active_inbound_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_active_inbound_ids(active_ids: set[str]) -> None:
    ACTIVE_INBOUND_FILE.write_text(
        json.dumps({"active_inbound_ids": sorted(active_ids)}, indent=2),
        encoding="utf-8",
    )


def load_declined_history() -> List[Dict[str, Any]]:
    if not DECLINED_HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(DECLINED_HISTORY_FILE.read_text(encoding="utf-8"))
        trades = data.get("trades", [])
        return trades if isinstance(trades, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_declined_history(trades: List[Dict[str, Any]]) -> None:
    DECLINED_HISTORY_FILE.write_text(
        json.dumps({"trades": trades[-100:]}, indent=2),
        encoding="utf-8",
    )


def add_declined_history(trade_id: str, status: str, trader: Dict[str, Any]) -> None:
    trades = load_declined_history()
    entry = {
        "id": str(trade_id),
        "status": str(status or "Unknown"),
        "trader_display": trader.get("display_name", "Unknown"),
        "trader_username": trader.get("username", "Unknown"),
        "time": datetime.now(timezone.utc).isoformat(),
    }

    # Avoid duplicates.
    trades = [t for t in trades if str(t.get("id")) != str(trade_id)]
    trades.append(entry)
    save_declined_history(trades)


# ---------- fetchers ----------

def make_roblox_session(cookie: str) -> requests.Session:
    session = requests.Session()
    session.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
    session.headers.update({
        "User-Agent": "BloxwareTradeNotifierV17/1.0",
        "Accept": "application/json",
    })
    return session


def roblox_get(session: requests.Session, url: str) -> Dict[str, Any]:
    response = session.get(url, timeout=25)

    if response.status_code == 401:
        raise RuntimeError("Roblox rejected the cookie. Your cookie may be expired or invalid.")

    response.raise_for_status()
    return response.json()


def fetch_authenticated_user(session: requests.Session) -> Dict[str, Any]:
    return roblox_get(session, AUTHENTICATED_USER_URL)


def fetch_inbound_trades(session: requests.Session) -> List[Dict[str, Any]]:
    payload = roblox_get(session, INBOUND_TRADES_URL)
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def fetch_trade_details(session: requests.Session, trade_id: str) -> Dict[str, Any]:
    return roblox_get(session, TRADE_DETAILS_URL.format(trade_id=trade_id))


def fetch_trade_details_with_retry(session: requests.Session, trade_id: str, attempts: int = 3) -> Dict[str, Any]:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch_trade_details(session, trade_id)
        except HTTPError as error:
            last_error = error
            status = error.response.status_code if error.response is not None else "unknown"
            if attempt < attempts:
                print(c(f"  Trade {trade_id} returned {status}. Retry {attempt}/{attempts}...", Term.YELLOW))
                time.sleep(0.8 * attempt)
                continue
            raise
        except Exception as error:
            last_error = error
            if attempt < attempts:
                print(c(f"  Trade {trade_id} failed. Retry {attempt}/{attempts}...", Term.YELLOW))
                time.sleep(0.8 * attempt)
                continue
            raise last_error


def fetch_rolimons_items() -> Dict[str, Dict[str, Any]]:
    response = requests.get(ROLIMONS_ITEMDETAILS_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    raw_items = payload.get("items", {})

    parsed: Dict[str, Dict[str, Any]] = {}

    if not isinstance(raw_items, dict):
        return parsed

    for asset_id, data in raw_items.items():
        if not isinstance(data, list):
            continue

        rap = clean_number(data[2] if len(data) > 2 else None)
        value = clean_number(data[3] if len(data) > 3 else None)
        default_value = clean_number(data[4] if len(data) > 4 else None)
        demand = data[5] if len(data) > 5 else None
        trend = data[6] if len(data) > 6 else None

        parsed[str(asset_id)] = {
            "name": data[0] if len(data) > 0 else "Unknown",
            "acronym": data[1] if len(data) > 1 else "",
            "rap": rap,
            "value": value if value and value > 0 else None,
            "default_value": default_value if default_value and default_value > 0 else None,
            "demand": None if demand in (-1, "-1", None) else demand,
            "trend": None if trend in (-1, "-1", None) else trend,
            "projected": parse_bool_flag(data[7]) if len(data) > 7 else False,
            "hyped": parse_bool_flag(data[8]) if len(data) > 8 else False,
            "rare": parse_bool_flag(data[9]) if len(data) > 9 else False,
        }

    return parsed


def fetch_asset_thumbnails(asset_ids: List[str], size: str = "150x150") -> Dict[str, str]:
    if not asset_ids:
        return {}

    thumbnails: Dict[str, str] = {}

    for i in range(0, len(asset_ids), 50):
        chunk = asset_ids[i:i + 50]
        params = {
            "assetIds": ",".join(chunk),
            "size": size,
            "format": "Png",
            "isCircular": "false",
        }
        response = requests.get(ASSET_THUMBNAILS_URL, params=params, timeout=25)
        response.raise_for_status()

        for item in response.json().get("data", []):
            target_id = str(item.get("targetId"))
            image_url = item.get("imageUrl")
            if target_id and image_url:
                thumbnails[target_id] = image_url

    return thumbnails


def fetch_user_headshot(user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None

    params = {
        "userIds": str(user_id),
        "size": "150x150",
        "format": "Png",
        "isCircular": "true",
    }

    try:
        response = requests.get(USER_HEADSHOT_URL, params=params, timeout=25)
        response.raise_for_status()
        data = response.json().get("data", [])
        if data and data[0].get("imageUrl"):
            return data[0]["imageUrl"]
    except requests.RequestException:
        return None

    return None


def download_image(url: Optional[str], size: Tuple[int, int]) -> Image.Image:
    fallback = Image.new("RGBA", size, (48, 52, 60, 255))

    if not url:
        return fallback

    try:
        response = requests.get(url, timeout=25)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)

        canvas = Image.new("RGBA", size, (48, 52, 60, 255))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        canvas.alpha_composite(img, (x, y))
        return canvas
    except Exception:
        return fallback


# ---------- trade utilities ----------

def clean_number(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def fmt_number(value: Any) -> str:
    n = clean_number(value)
    if n is None:
        return "N/A"
    return f"{n:,}"


def fmt_signed(value: int) -> str:
    if value > 0:
        return f"+{value:,}"
    return f"{value:,}"


def fmt_roli_value(value: Optional[int]) -> str:
    if value is None or value <= 0:
        return "Not Assigned"
    return f"{value:,}"


def parse_bool_flag(value: Any) -> bool:
    # Never use bool(-1); Rolimons uses -1 as unset sometimes.
    return value is True or value == 1 or value == "1" or str(value).lower() == "true"


def format_created_date(raw_date: Any, timezone_name: str) -> str:
    if not raw_date:
        return "Unknown"

    try:
        clean = str(raw_date).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        local = dt.astimezone(ZoneInfo(timezone_name))
        hour = local.hour % 12 or 12
        minute = f"{local.minute:02d}"
        ampm = "AM" if local.hour < 12 else "PM"
        return f"{local.strftime('%b')} {local.day}, {local.year} at {hour}:{minute} {ampm}"
    except Exception:
        return str(raw_date)


def parse_trade_datetime(raw_date: Any) -> Optional[datetime]:
    if not raw_date:
        return None
    try:
        clean = str(raw_date).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def get_trade_id(trade: Dict[str, Any]) -> Optional[str]:
    trade_id = trade.get("id")
    return str(trade_id) if trade_id is not None else None


def extract_offer_user(offer: Dict[str, Any]) -> Dict[str, Any]:
    user = offer.get("user") or {}
    if not isinstance(user, dict):
        user = {}

    user_id = user.get("id") or user.get("userId")
    username = user.get("name") or user.get("username") or "Unknown"
    display_name = user.get("displayName") or username

    return {
        "id": str(user_id) if user_id is not None else None,
        "username": str(username),
        "display_name": str(display_name),
        "profile_url": ROBLOX_PROFILE_URL.format(user_id=user_id) if user_id is not None else "https://www.roblox.com",
    }


def extract_items_from_offer(offer: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = offer.get("userAssets") or []
    return items if isinstance(items, list) else []


def determine_sides(trade_details: Dict[str, Any], my_user_id: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    offers = trade_details.get("offers", [])
    if not isinstance(offers, list) or len(offers) < 2:
        return {}, {}

    give_offer = {}
    receive_offer = {}

    for offer in offers:
        user = extract_offer_user(offer)
        if user["id"] and int(user["id"]) == int(my_user_id):
            give_offer = offer
        else:
            receive_offer = offer

    if not give_offer or not receive_offer:
        give_offer, receive_offer = offers[0], offers[1]

    return give_offer, receive_offer


def enrich_item(
    item: Dict[str, Any],
    rolimons: Dict[str, Dict[str, Any]],
    thumbs: Dict[str, str],
    add_unvalued_to_total: bool,
) -> Dict[str, Any]:
    asset_id = item.get("assetId") or item.get("id")
    user_asset_id = item.get("userAssetId") or item.get("id")
    asset_id_str = str(asset_id) if asset_id is not None else ""

    roli = rolimons.get(asset_id_str, {})

    name = (
        item.get("name")
        or item.get("assetName")
        or roli.get("name")
        or f"Asset {asset_id_str}"
    )

    roblox_rap = clean_number(item.get("recentAveragePrice"), 0) or 0
    roli_rap = clean_number(roli.get("rap"), None)
    rap = roblox_rap or roli_rap or 0

    roli_value = clean_number(roli.get("value"), None)
    total_value = roli_value if roli_value and roli_value > 0 else (rap if add_unvalued_to_total else 0)

    return {
        "asset_id": asset_id_str,
        "user_asset_id": str(user_asset_id) if user_asset_id is not None else "N/A",
        "name": str(name),
        "serial": item.get("serialNumber") or item.get("serial") or None,
        "rap": rap,
        "roli_value": roli_value,
        "total_value": total_value,
        "demand": roli.get("demand"),
        "trend": roli.get("trend"),
        "projected": bool(roli.get("projected")),
        "hyped": bool(roli.get("hyped")),
        "rare": bool(roli.get("rare")),
        "thumbnail": thumbs.get(asset_id_str),
        "rolimons_url": f"https://www.rolimons.com/item/{asset_id_str}",
    }


def item_flags_list(item: Dict[str, Any]) -> List[str]:
    flags = []
    if item.get("projected"):
        flags.append("Projected")
    if item.get("hyped"):
        flags.append("Hyped")
    if item.get("rare"):
        flags.append("Rare")
    return flags


def item_flags(item: Dict[str, Any]) -> str:
    flags = item_flags_list(item)
    return ", ".join(flags) if flags else "None"


def summarize_side(items: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "count": len(items),
        "rap": sum(clean_number(i.get("rap"), 0) or 0 for i in items),
        "value": sum(clean_number(i.get("total_value"), 0) or 0 for i in items),
        "assigned_value": sum(clean_number(i.get("roli_value"), 0) or 0 for i in items),
    }


def side_meta(items: List[Dict[str, Any]]) -> str:
    projected = sum(1 for i in items if i.get("projected"))
    hyped = sum(1 for i in items if i.get("hyped"))
    rare = sum(1 for i in items if i.get("rare"))
    demands = sorted({str(i.get("demand")) for i in items if i.get("demand") is not None})
    trends = sorted({str(i.get("trend")) for i in items if i.get("trend") is not None})

    return "\n".join([
        f"Projected: `{projected}`",
        f"Hyped: `{hyped}`",
        f"Rare: `{rare}`",
        f"Demand: `{', '.join(demands) if demands else 'Not Assigned'}`",
        f"Trend: `{', '.join(trends) if trends else 'Not Assigned'}`",
        "Hoard: `Open Rolimons item page`",
    ])


def analyze_trade(give_items: List[Dict[str, Any]], receive_items: List[Dict[str, Any]], threshold: int) -> Dict[str, Any]:
    give = summarize_side(give_items)
    receive = summarize_side(receive_items)

    value_diff = receive["value"] - give["value"]
    rap_diff = receive["rap"] - give["rap"]

    receive_projected = any(i.get("projected") for i in receive_items)
    give_projected = any(i.get("projected") for i in give_items)

    if give["value"] > 0 and receive["value"] < int(give["value"] * 0.4) and not receive_projected:
        verdict = "🔴 TERRIBLE TRADE. It is not even projected and the incoming value is under 40% of your offer. Decline this trade."
    elif receive_projected and value_diff > 0:
        if value_diff >= threshold:
            verdict = "⚠️ Big win on paper, but the incoming side has projected item(s). Decline this trade unless you manually verify it first."
        else:
            verdict = "⚠️ Paper win, but the incoming side has projected item(s). Decline or manually verify before accepting."
    elif receive_projected:
        verdict = "🔴 Incoming side has projected item(s) and the value is not clearly better. Decline this trade."
    elif value_diff >= 1000:
        verdict = "✅ Strong clean win by estimated value."
    elif value_diff >= threshold:
        verdict = "🟢 Good clean win by estimated value."
    elif value_diff > 0:
        verdict = "🟢 Small clean win by estimated value."
    elif value_diff == 0:
        verdict = "🟡 Even by estimated value."
    elif value_diff > -1000:
        verdict = "🟠 Small loss by estimated value."
    else:
        verdict = "🔴 Loss by estimated value."

    if give_projected and not receive_projected:
        verdict += " You are giving projected item(s), so this may be better than raw value."

    return {
        "give": give,
        "receive": receive,
        "value_diff": value_diff,
        "rap_diff": rap_diff,
        "verdict": verdict,
        "receive_projected": receive_projected,
        "give_projected": give_projected,
        "high_value_clean_win": value_diff >= threshold and not receive_projected,
    }


def item_line(item: Dict[str, Any]) -> str:
    flags = item_flags(item)
    flag_text = f" | {flags}" if flags != "None" else ""
    serial = f" #{item['serial']}" if item.get("serial") else ""
    demand = item.get("demand") if item.get("demand") is not None else "N/A"
    trend = item.get("trend") if item.get("trend") is not None else "N/A"
    return (
        f"**[{item['name']}{serial}](https://www.roblox.com/catalog/{item['asset_id']})**\n"
        f"RAP `{fmt_number(item['rap'])}` | Value `{fmt_roli_value(item['roli_value'])}` | Demand `{demand}` | Trend `{trend}`{flag_text}"
    )


def side_text(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No items."
    lines = [item_line(item) for item in items]
    text = "\n".join(lines)
    if len(text) > 950:
        text = text[:930] + "\n...more items in image panel."
    return text


# ---------- image panel ----------

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_badge(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, fill, font: ImageFont.ImageFont) -> int:
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 24
    h = bbox[3] - bbox[1] + 14
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=fill)
    draw.text((x + 12, y + 4), text, font=font, fill=(255, 255, 255, 255))
    return x + w + 10


def draw_kv(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, value_fill, label_font, value_font) -> None:
    draw.text((x, y), label, font=label_font, fill=(185, 194, 210, 255))
    draw.text((x, y + 29), value, font=value_font, fill=value_fill)


def build_side_panel(title: str, user: Dict[str, Any], items: List[Dict[str, Any]], totals: Dict[str, int]) -> bytes:
    # Kept readable in Discord preview: not too wide, but tall enough for metadata.
    width = 1000
    header_h = 230
    row_h = 390
    padding = 30
    item_count = max(1, len(items))
    height = header_h + item_count * row_h + padding

    bg = (24, 27, 35, 255)
    card = (42, 47, 61, 255)
    card_2 = (35, 39, 50, 255)
    meta_box = (34, 38, 49, 255)
    muted = (185, 194, 210, 255)
    white = (248, 250, 255, 255)
    blue = (86, 166, 255, 255)
    green = (71, 215, 128, 255)
    orange = (255, 184, 77, 255)
    red = (239, 88, 88, 255)
    purple = (143, 105, 255, 255)
    slate = (79, 89, 110, 255)

    img = Image.new("RGBA", (width, height), bg)
    draw = ImageDraw.Draw(img)

    title_font = load_font(62, bold=True)
    user_font = load_font(36, bold=True)
    sub_font = load_font(30, bold=True)
    item_font = load_font(40, bold=True)
    small_font = load_font(25)
    stat_font = load_font(44, bold=True)
    total_font = load_font(42, bold=True)
    total_label_font = load_font(26, bold=True)
    badge_font = load_font(23, bold=True)
    meta_label_font = load_font(21, bold=True)
    meta_value_font = load_font(24, bold=True)

    draw.text((padding, 18), title, font=title_font, fill=blue)
    draw.text((padding, 92), f"Display: {user.get('display_name', 'Unknown')}", font=user_font, fill=white)
    draw.text((padding, 138), f"Username: @{user.get('username', 'Unknown')}", font=sub_font, fill=muted)

    # Top-right totals box with contained rows.
    box_x = width - 370
    box_y = 28
    box_w = 340
    box_h = 174
    draw.rounded_rectangle((box_x, box_y, box_x + box_w, box_y + box_h), radius=24, fill=card_2)
    draw.text((box_x + 24, box_y + 16), f"ITEMS {totals['count']}", font=total_label_font, fill=muted)

    draw.rounded_rectangle((box_x + 18, box_y + 52, box_x + box_w - 18, box_y + 104), radius=14, fill=(30, 45, 42, 255))
    draw.text((box_x + 34, box_y + 56), f"RAP {fmt_number(totals['rap'])}", font=total_font, fill=green)

    draw.rounded_rectangle((box_x + 18, box_y + 112, box_x + box_w - 18, box_y + 164), radius=14, fill=(48, 40, 30, 255))
    draw.text((box_x + 34, box_y + 116), f"VAL {fmt_number(totals['value'])}", font=total_font, fill=orange)

    y = header_h

    if not items:
        draw.text((padding, y + 30), "No items.", font=item_font, fill=white)
    else:
        for item in items:
            draw.rounded_rectangle((padding, y, width - padding, y + row_h - 22), radius=30, fill=card)

            thumb = download_image(item.get("thumbnail"), (190, 190))
            img.alpha_composite(thumb, (padding + 24, y + 46))

            text_x = padding + 240
            draw.text((text_x, y + 28), item["name"][:31], font=item_font, fill=white)

            serial = f"Serial #{item['serial']}" if item.get("serial") else "No serial / Original Owner"
            draw.text((text_x, y + 78), serial, font=small_font, fill=muted)

            draw.text((text_x, y + 116), f"RAP {fmt_number(item['rap'])}", font=stat_font, fill=green)
            draw.text((text_x, y + 168), f"VALUE {fmt_roli_value(item['roli_value'])}", font=stat_font, fill=orange)

            # Badge row: high enough that it never touches metadata.
            bx = text_x
            by = y + 222
            flags = item_flags_list(item)
            if item.get("projected"):
                bx = draw_badge(draw, (bx, by), "PROJECTED", red, badge_font)
            if item.get("hyped"):
                bx = draw_badge(draw, (bx, by), "HYPED", purple, badge_font)
            if item.get("rare"):
                bx = draw_badge(draw, (bx, by), "RARE", blue, badge_font)
            if not flags:
                draw_badge(draw, (bx, by), "NORMAL", slate, badge_font)

            # Bottom metadata has more padding and wider spacing, so Not Assigned cannot collide with NO.
            meta_y = y + 276
            meta_h = 78
            draw.rounded_rectangle((padding + 22, meta_y, width - padding - 22, meta_y + meta_h), radius=18, fill=meta_box)

            demand = item.get("demand") if item.get("demand") is not None else "Not Assigned"
            trend = item.get("trend") if item.get("trend") is not None else "Not Assigned"

            projected_yes = bool(item.get("projected"))
            hyped_yes = bool(item.get("hyped"))
            rare_yes = bool(item.get("rare"))

            draw_kv(draw, padding + 44, meta_y + 10, "DEMAND", str(demand), white, meta_label_font, meta_value_font)
            draw_kv(draw, padding + 250, meta_y + 10, "TREND", str(trend), white, meta_label_font, meta_value_font)
            draw_kv(draw, padding + 510, meta_y + 10, "PROJECTED", "YES" if projected_yes else "NO", green if projected_yes else red, meta_label_font, meta_value_font)
            draw_kv(draw, padding + 690, meta_y + 10, "HYPED", "YES" if hyped_yes else "NO", green if hyped_yes else red, meta_label_font, meta_value_font)
            draw_kv(draw, padding + 820, meta_y + 10, "RARE", "YES" if rare_yes else "NO", green if rare_yes else red, meta_label_font, meta_value_font)

            y += row_h

    watermark_font = load_font(18, bold=True)
    watermark = "Lomi's Bloxware Notifier"
    bbox = draw.textbbox((0, 0), watermark, font=watermark_font)
    wm_w = bbox[2] - bbox[0]
    wm_h = bbox[3] - bbox[1]
    draw.text(
        (width - wm_w - 26, height - wm_h - 18),
        watermark,
        font=watermark_font,
        fill=(130, 140, 160, 210),
    )

    output = io.BytesIO()
    img.save(output, "PNG")
    output.seek(0)
    return output.read()


# ---------- Discord ----------

def build_discord_payload_and_files(
    trade_id: str,
    trade_details: Dict[str, Any],
    my_user_id: int,
    rolimons: Dict[str, Dict[str, Any]],
    settings: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, bytes], bool, int]:
    give_offer, receive_offer = determine_sides(trade_details, my_user_id)

    give_user = extract_offer_user(give_offer)
    receive_user = extract_offer_user(receive_offer)

    give_raw = extract_items_from_offer(give_offer)
    receive_raw = extract_items_from_offer(receive_offer)

    asset_ids = []
    for raw in give_raw + receive_raw:
        asset_id = raw.get("assetId") or raw.get("id")
        if asset_id is not None:
            asset_ids.append(str(asset_id))

    thumbnails = fetch_asset_thumbnails(sorted(set(asset_ids)), size="150x150")

    give_items = [
        enrich_item(i, rolimons, thumbnails, settings["add_unvalued_to_total"])
        for i in give_raw
    ]
    receive_items = [
        enrich_item(i, rolimons, thumbnails, settings["add_unvalued_to_total"])
        for i in receive_raw
    ]

    analysis = analyze_trade(give_items, receive_items, settings["high_value_alert_threshold"])

    created_raw = trade_details.get("created") or trade_details.get("createdAt")
    created = format_created_date(created_raw, settings["timezone_name"])
    partner_headshot = fetch_user_headshot(receive_user.get("id"))

    ping = f"<@{settings['discord_user_id']}> " if settings["discord_user_id"] else ""
    trade_url = TRADE_PAGE_URL.format(trade_id=trade_id)

    value_diff = analysis["value_diff"]
    color = 0x2ECC71 if value_diff > 0 else 0xF1C40F if value_diff == 0 else 0xE74C3C

    summary_embed = {
        "title": "📬 New Roblox Trade Received",
        "url": trade_url,
        "description": f"*made by lomi*\n\n{analysis['verdict']}",
        "color": color,
        "fields": [
            {
                "name": "Trader",
                "value": (
                    f"Display: **{receive_user['display_name']}**\n"
                    f"Username: [@{receive_user['username']}]({receive_user['profile_url']})"
                ),
                "inline": True,
            },
            {
                "name": "Received",
                "value": created,
                "inline": True,
            },
            {
                "name": "Trade ID",
                "value": f"`{trade_id}`",
                "inline": True,
            },
            {
                "name": "Estimated Value Difference",
                "value": f"`{fmt_signed(analysis['value_diff'])}`",
                "inline": True,
            },
            {
                "name": "RAP Difference",
                "value": f"`{fmt_signed(analysis['rap_diff'])}`",
                "inline": True,
            },
            {
                "name": "Totals",
                "value": (
                    f"**You Give:** RAP `{fmt_number(analysis['give']['rap'])}` | Est. Value `{fmt_number(analysis['give']['value'])}`\n"
                    f"**You Receive:** RAP `{fmt_number(analysis['receive']['rap'])}` | Est. Value `{fmt_number(analysis['receive']['value'])}`"
                ),
                "inline": False,
            },
            {
                "name": "Incoming Side Notes",
                "value": side_meta(receive_items),
                "inline": True,
            },
            {
                "name": "Your Side Notes",
                "value": side_meta(give_items),
                "inline": True,
            },
        ],
    }

    if partner_headshot:
        summary_embed["thumbnail"] = {"url": partner_headshot}

    give_embed = {
        "title": "📤 You Give",
        "color": 0xE67E22,
        "description": side_text(give_items),
        "fields": [
            {
                "name": "Side Total",
                "value": (
                    f"Items `{analysis['give']['count']}` | "
                    f"RAP `{fmt_number(analysis['give']['rap'])}` | "
                    f"Est. Value `{fmt_number(analysis['give']['value'])}`"
                ),
                "inline": False,
            }
        ],
        "image": {"url": "attachment://you_give.png"},
    }

    receive_embed = {
        "title": "📥 You Receive",
        "color": 0x3498DB,
        "description": side_text(receive_items),
        "fields": [
            {
                "name": "Side Total",
                "value": (
                    f"Items `{analysis['receive']['count']}` | "
                    f"RAP `{fmt_number(analysis['receive']['rap'])}` | "
                    f"Est. Value `{fmt_number(analysis['receive']['value'])}`"
                ),
                "inline": False,
            }
        ],
        "image": {"url": "attachment://you_receive.png"},
    }

    files = {
        "you_give.png": build_side_panel("You Give", give_user, give_items, analysis["give"]),
        "you_receive.png": build_side_panel("You Receive", receive_user, receive_items, analysis["receive"]),
    }

    high_alert = analysis["high_value_clean_win"]

    if high_alert and settings["discord_user_id"]:
        content = (
            f"{ping} 🚨 **GOOD TRADE ALERT** 🚨 "
            f"`{fmt_signed(value_diff)}` estimated value gain and no incoming projected items."
        )
    else:
        content = f"{ping}New Roblox trade received."

    payload = {
        "content": content,
        "embeds": [summary_embed, give_embed, receive_embed],
    }

    return payload, files, high_alert, value_diff


def send_discord_webhook_to_url(webhook_url: str, payload: Dict[str, Any], image_files: Optional[Dict[str, bytes]] = None) -> None:
    image_files = image_files or {}

    if image_files:
        multipart_files = {}
        for index, (filename, data) in enumerate(image_files.items()):
            multipart_files[f"files[{index}]"] = (filename, data, "image/png")
        data = {"payload_json": json.dumps(payload)}
        response = requests.post(webhook_url, data=data, files=multipart_files, timeout=35)
    else:
        response = requests.post(webhook_url, json=payload, timeout=25)

    response.raise_for_status()


def send_slack_message(slack_webhook_url: str, text: str) -> None:
    if not valid_slack_webhook_format(slack_webhook_url):
        raise ValueError("Invalid Slack webhook URL.")
    response = requests.post(slack_webhook_url, json={"text": text}, timeout=25)
    response.raise_for_status()


def slack_item_line(item: Dict[str, Any]) -> str:
    serial = f"Serial #{item['serial']}" if item.get("serial") else "No serial / Original Owner"
    demand = item.get("demand") if item.get("demand") is not None else "Not Assigned"
    trend = item.get("trend") if item.get("trend") is not None else "Not Assigned"
    projected = "YES" if item.get("projected") else "NO"
    hyped = "YES" if item.get("hyped") else "NO"
    rare = "YES" if item.get("rare") else "NO"
    return (
        f"• {item['name']} — RAP {fmt_number(item['rap'])} | Value {fmt_roli_value(item['roli_value'])}\n"
        f"  {serial} | Demand: {demand} | Trend: {trend} | Projected: {projected} | Hyped: {hyped} | Rare: {rare}"
    )


def build_slack_trade_text(
    trade_id: str,
    trade_details: Dict[str, Any],
    my_user_id: int,
    rolimons: Dict[str, Dict[str, Any]],
    settings: Dict[str, Any],
    high_alert: bool,
    value_diff: int,
) -> str:
    give_offer, receive_offer = determine_sides(trade_details, my_user_id)
    receive_user = extract_offer_user(receive_offer)

    give_raw = extract_items_from_offer(give_offer)
    receive_raw = extract_items_from_offer(receive_offer)

    give_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in give_raw]
    receive_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in receive_raw]
    analysis = analyze_trade(give_items, receive_items, settings["high_value_alert_threshold"])

    trade_url = TRADE_PAGE_URL.format(trade_id=trade_id)
    title = "🚨 GOOD TRADE ALERT" if high_alert else "📬 New Roblox Trade"
    give_lines = "\n".join(slack_item_line(i) for i in give_items) or "No items."
    receive_lines = "\n".join(slack_item_line(i) for i in receive_items) or "No items."

    return (
        f"{title}\n"
        f"made by lomi\n\n"
        f"Trader: {receive_user['display_name']} (@{receive_user['username']})\n"
        f"Trade Link: {trade_url}\n\n"
        f"Summary: {analysis['verdict']}\n"
        f"Value Difference: {fmt_signed(value_diff)}\n"
        f"RAP Difference: {fmt_signed(analysis['rap_diff'])}\n\n"
        f"YOU GIVE — RAP {fmt_number(analysis['give']['rap'])} | Est. Value {fmt_number(analysis['give']['value'])}\n"
        f"{give_lines}\n\n"
        f"YOU RECEIVE — RAP {fmt_number(analysis['receive']['rap'])} | Est. Value {fmt_number(analysis['receive']['value'])}\n"
        f"{receive_lines}"
    )


def send_slack_images_with_sdk(settings: Dict[str, Any], text: str, image_files: Dict[str, bytes]) -> bool:
    token = settings.get("slack_bot_token", "")
    channel = settings.get("slack_channel_id", "")

    if not token or not channel or not image_files:
        return False

    try:
        from slack_sdk import WebClient
    except Exception:
        print(c("Slack image upload needs slack_sdk. Run: pip install slack_sdk", Term.YELLOW))
        return False

    try:
        client = WebClient(token=token)
        upload_items = []
        for filename, data in image_files.items():
            upload_items.append({
                "file": io.BytesIO(data),
                "filename": filename,
                "title": filename.replace("_", " ").replace(".png", "").title(),
            })
        client.files_upload_v2(
            channel=channel,
            initial_comment=text,
            file_uploads=upload_items,
        )
        return True
    except Exception as error:
        print(c(f"Slack image upload failed, sending text fallback: {error}", Term.YELLOW))
        return False


def send_slack_trade_alert(
    settings: Dict[str, Any],
    trade_id: str,
    trade_details: Dict[str, Any],
    my_user_id: int,
    rolimons: Dict[str, Dict[str, Any]],
    value_diff: int,
    high_alert: bool,
    image_files: Optional[Dict[str, bytes]] = None,
) -> bool:
    if not provider_allows(settings, "slack"):
        return False
    if not settings.get("slack_enabled"):
        return False

    text = build_slack_trade_text(
        trade_id=trade_id,
        trade_details=trade_details,
        my_user_id=my_user_id,
        rolimons=rolimons,
        settings=settings,
        high_alert=high_alert,
        value_diff=value_diff,
    )

    if settings.get("slack_upload_images") and settings.get("slack_bot_token") and settings.get("slack_channel_id"):
        if send_slack_images_with_sdk(settings, text, image_files or {}):
            return True

    url = settings.get("slack_webhook_url", "")
    if valid_slack_webhook_format(url):
        send_slack_message(url, text)
        return True
    return False


def send_to_active_webhooks(
    settings: Dict[str, Any],
    payload: Dict[str, Any],
    image_files: Optional[Dict[str, bytes]] = None,
    event: str = "inbound",
) -> int:
    if not provider_allows(settings, "discord"):
        return 0

    hooks = active_webhooks(settings["webhooks"], event)
    if not hooks:
        raise RuntimeError(f"No active Discord webhooks for {event}. Add one in Settings > Manage Discord webhooks.")

    sent = 0
    for hook in hooks:
        try:
            send_discord_webhook_to_url(hook["url"], payload, image_files)
            sent += 1
        except Exception as error:
            print(c(f"Failed webhook {hook.get('name', 'Webhook')}: {error}", Term.RED))
    return sent


def send_high_value_alert_spam(settings: Dict[str, Any], trade_id: str, value_diff: int) -> None:
    if not settings["discord_user_id"]:
        return

    repeat = settings["high_value_alert_repeat"]
    profile_ping = f"<@{settings['discord_user_id']}>"
    trade_url = TRADE_PAGE_URL.format(trade_id=trade_id)

    for _ in range(repeat):
        payload = {
            "content": (
                f"{profile_ping} 🚨 **OVER {settings['high_value_alert_threshold']} CLEAN DEAL** "
                f"({fmt_signed(value_diff)} value) — CHECK THIS NOW: {trade_url}"
            )
        }
        send_to_active_webhooks(settings, payload, event="inbound")
        time.sleep(0.35)



def send_declined_status_notification(
    trade_id: str,
    trade_details: Dict[str, Any],
    my_user_id: int,
    settings: Dict[str, Any],
) -> None:
    give_offer, receive_offer = determine_sides(trade_details, my_user_id)
    receive_user = extract_offer_user(receive_offer)
    status = str(trade_details.get("status") or "Unknown")
    trade_url = TRADE_PAGE_URL.format(trade_id=trade_id)

    payload = {
        "content": f"🚫 Trade status update: `{status}`",
        "embeds": [
            {
                "title": "🚫 Trade Status Update",
                "url": trade_url,
                "description": f"*made by lomi*\n\nTrade `{trade_id}` is now **{status}**.",
                "color": 0xE74C3C,
                "fields": [
                    {
                        "name": "Trader",
                        "value": (
                            f"Display: **{receive_user['display_name']}**\n"
                            f"Username: [@{receive_user['username']}]({receive_user['profile_url']})"
                        ),
                        "inline": True,
                    },
                    {"name": "Status", "value": f"`{status}`", "inline": True},
                    {"name": "Trade ID", "value": f"`{trade_id}`", "inline": True},
                ],
            }
        ],
    }

    add_declined_history(trade_id, status, receive_user)

    try:
        sent = send_to_active_webhooks(settings, payload, event="declined")
        print(c(f"Sent declined/status notification for {trade_id} to {sent} webhook(s).", Term.YELLOW))
    except Exception as error:
        print(c(f"Skipped declined/status notification: {error}", Term.GRAY))


def check_for_declined_or_removed_trades(
    previous_active_ids: set[str],
    current_active_ids: set[str],
    session: requests.Session,
    my_user_id: int,
    settings: Dict[str, Any],
) -> None:
    removed_ids = previous_active_ids - current_active_ids
    if not removed_ids:
        return

    for trade_id in sorted(removed_ids):
        try:
            details = fetch_trade_details_with_retry(session, trade_id)
            status = str(details.get("status") or "").lower()
            if "declin" in status:
                send_declined_status_notification(trade_id, details, my_user_id, settings)
        except Exception:
            # Some old/removed trades may no longer be readable. Ignore instead of crashing live mode.
            continue




def colored_profit(value_diff: int) -> str:
    if value_diff > 0:
        return c(fmt_signed(value_diff), Term.GREEN)
    if value_diff < 0:
        return c(fmt_signed(value_diff), Term.RED)
    return c(fmt_signed(value_diff), Term.YELLOW)


def print_trade_details_in_panel(index: int, trade: Dict[str, Any], session: requests.Session, my_user_id: int, rolimons: Dict[str, Dict[str, Any]], settings: Dict[str, Any]) -> None:
    trade_id = get_trade_id(trade)
    if not trade_id:
        return

    try:
        details = fetch_trade_details_with_retry(session, trade_id)
        give_offer, receive_offer = determine_sides(details, my_user_id)
        receive_user = extract_offer_user(receive_offer)

        give_raw = extract_items_from_offer(give_offer)
        receive_raw = extract_items_from_offer(receive_offer)

        give_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in give_raw]
        receive_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in receive_raw]
        analysis = analyze_trade(give_items, receive_items, settings["high_value_alert_threshold"])

        trade_url = TRADE_PAGE_URL.format(trade_id=trade_id)

        print(f"  {c(str(index) + ')', Term.GREEN)} {c(receive_user['display_name'], Term.BOLD + Term.WHITE)} {c('@' + receive_user['username'], Term.GRAY)}")
        print(f"     Link:      {c(trade_url, Term.BLUE)}")
        print(f"     Profit:    {colored_profit(analysis['value_diff'])} value | RAP {colored_profit(analysis['rap_diff'])}")
        print(f"     Summary:   {analysis['verdict']}")
        print(f"     Give:      RAP {fmt_number(analysis['give']['rap'])} | Est. Value {fmt_number(analysis['give']['value'])} | Items {analysis['give']['count']}")
        print(f"     Receive:   RAP {fmt_number(analysis['receive']['rap'])} | Est. Value {fmt_number(analysis['receive']['value'])} | Items {analysis['receive']['count']}")
        print(f"     Projected: incoming = {c('YES', Term.RED) if analysis['receive_projected'] else c('NO', Term.GREEN)} | your_side = {c('YES', Term.YELLOW) if analysis['give_projected'] else c('NO', Term.GREEN)}")
        print()
    except HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        print(f"  {c(str(index) + ')', Term.YELLOW)} Trade link: {c(TRADE_PAGE_URL.format(trade_id=trade_id), Term.BLUE)}")
        print(c(f"     Could not load full details. Roblox returned {status}.", Term.YELLOW))
        print()
    except Exception as error:
        print(c(f"  Could not load trade details: {error}", Term.RED))
        print()



def draw_ascii_bar(label: str, value: int, max_value: int, color: str) -> None:
    width = 32
    max_value = max(max_value, 1)
    filled = int(width * max(0, value) / max_value)
    bar = "█" * filled + "░" * (width - filled)
    print(f"     {label:<12} {color}{bar}{Term.RESET} {fmt_number(value)}")


def risk_score_for_items(items: List[Dict[str, Any]]) -> int:
    score = 0
    for item in items:
        if item.get("projected"):
            score += 45
        if item.get("hyped"):
            score += 20
        if item.get("rare"):
            score -= 5
        if item.get("demand") in (0, 1, "0", "1"):
            score += 10
    return max(0, min(100, score))



def fetch_public_history_points(asset_id: str) -> List[int]:
    """
    Best-effort public history fetch.
    If no public/parseable history is available, returns [] and the analysis falls back to current-value bars.
    """
    candidates = [
        f"https://www.rolimons.com/item/{asset_id}",
        f"https://www.rolimons.com/itemapi/itemdetails",
    ]

    for url in candidates:
        try:
            response = requests.get(url, timeout=18)
            if not response.ok:
                continue
            raw = response.text

            # Try to pull simple numeric arrays from embedded chart-like data.
            matches = re.findall(r'\\[(?:\\s*\\d+\\s*,?){8,}\\]', raw)
            for match in matches[:8]:
                nums = [int(x) for x in re.findall(r'\\d+', match)]
                # Filter obvious timestamps and keep value-like series.
                filtered = [n for n in nums if 0 < n < 100000000]
                if len(filtered) >= 8:
                    return filtered[-40:]
        except Exception:
            continue

    return []


def draw_history_sparkline(points: List[int], label: str) -> None:
    if not points:
        print(f"     {label}: no accessible public history graph data found.")
        return

    blocks = "▁▂▃▄▅▆▇█"
    low = min(points)
    high = max(points)
    spread = max(high - low, 1)
    spark = "".join(blocks[min(7, int((p - low) / spread * 7))] for p in points[-48:])
    print(f"     {label}: {spark}")
    print(f"       low {fmt_number(low)} | high {fmt_number(high)} | latest {fmt_number(points[-1])}")

def render_analysis_page(
    page: int,
    trade_id: str,
    receive_user: Dict[str, Any],
    analysis: Dict[str, Any],
    give_items: List[Dict[str, Any]],
    receive_items: List[Dict[str, Any]],
    incoming_risk: int,
    outgoing_risk: int,
) -> None:
    clear_screen()
    print_banner()

    if page == 1:
        section("Trade analysis — Page 1/3", f"{receive_user['display_name']} (@{receive_user['username']})")
        print(f"  Link: {c(TRADE_PAGE_URL.format(trade_id=trade_id), Term.BLUE)}")
        print(f"  Summary: {analysis['verdict']}")
        print(f"  Value diff: {colored_profit(analysis['value_diff'])}")
        print(f"  RAP diff:   {colored_profit(analysis['rap_diff'])}")
        print()

        max_value = max(analysis["give"]["value"], analysis["receive"]["value"], 1)
        print(c("  Value comparison", Term.BOLD + Term.WHITE))
        draw_ascii_bar("You give", analysis["give"]["value"], max_value, Term.YELLOW)
        draw_ascii_bar("You receive", analysis["receive"]["value"], max_value, Term.GREEN if analysis["value_diff"] >= 0 else Term.RED)
        print()

        print(c("  Risk score", Term.BOLD + Term.WHITE))
        draw_ascii_bar("Incoming", incoming_risk, 100, Term.RED if incoming_risk >= 40 else Term.GREEN)
        draw_ascii_bar("Your side", outgoing_risk, 100, Term.YELLOW)

    elif page == 2:
        section("Trade analysis — Page 2/3", "item breakdown")
        def print_item_report(title: str, items: List[Dict[str, Any]]) -> None:
            print(c(title, Term.BOLD + Term.BLUE))
            if not items:
                print("     No items.")
                return
            for item in items:
                demand = item.get("demand") if item.get("demand") is not None else "Not Assigned"
                trend = item.get("trend") if item.get("trend") is not None else "Not Assigned"
                projected = c("YES", Term.RED) if item.get("projected") else c("NO", Term.GREEN)
                hyped = c("YES", Term.YELLOW) if item.get("hyped") else c("NO", Term.GREEN)
                rare = c("YES", Term.BLUE) if item.get("rare") else c("NO", Term.GREEN)
                print(f"     • {item['name']}")
                print(f"       RAP {fmt_number(item['rap'])} | Value {fmt_roli_value(item['roli_value'])} | Demand {demand} | Trend {trend}")
                print(f"       Projected {projected} | Hyped {hyped} | Rare {rare}")
                print(f"       Rolimons: {item.get('rolimons_url', 'N/A')}")
            print()

        print_item_report("You give", give_items)
        print_item_report("You receive", receive_items)

    elif page == 3:
        section("Trade analysis — Page 3/3", "history, charts, and source links")
        print(c("  Current graph", Term.BOLD + Term.WHITE))
        max_value = max(analysis["give"]["value"], analysis["receive"]["value"], analysis["give"]["rap"], analysis["receive"]["rap"], 1)
        draw_ascii_bar("Give value", analysis["give"]["value"], max_value, Term.YELLOW)
        draw_ascii_bar("Take value", analysis["receive"]["value"], max_value, Term.GREEN if analysis["value_diff"] >= 0 else Term.RED)
        draw_ascii_bar("Give RAP", analysis["give"]["rap"], max_value, Term.YELLOW)
        draw_ascii_bar("Take RAP", analysis["receive"]["rap"], max_value, Term.GREEN)
        print()
        print(c("  Public history graph attempt", Term.BOLD + Term.WHITE))
        for item in give_items + receive_items:
            print(f"     • {item['name']}")
            draw_history_sparkline(fetch_public_history_points(item["asset_id"]), "history")
            print(f"       Rolimons: {item.get('rolimons_url', 'N/A')}")
        print()
        print(c("  History note", Term.BOLD + Term.WHITE))
        print("     If public chart data is accessible, Bloxware shows a sparkline above.")
        print("     If not, use the Rolimons links for the full interactive chart.")


def analyze_selected_trade(trade: Dict[str, Any], session: requests.Session, my_user_id: int, rolimons: Dict[str, Dict[str, Any]], settings: Dict[str, Any]) -> None:
    trade_id = get_trade_id(trade)
    if not trade_id:
        return

    clear_screen()
    print_banner()
    section("Trade analysis", "running API checks and math")

    progress_line("Loading trade details", 1, 6, color=Term.CYAN)
    try:
        details = fetch_trade_details_with_retry(session, trade_id)
    except Exception as error:
        print(c(f"Could not analyze trade: {error}", Term.RED))
        pause()
        return

    progress_line("Splitting trade sides", 2, 6, color=Term.CYAN)
    give_offer, receive_offer = determine_sides(details, my_user_id)
    receive_user = extract_offer_user(receive_offer)

    progress_line("Reading item data", 3, 6, color=Term.CYAN)
    give_raw = extract_items_from_offer(give_offer)
    receive_raw = extract_items_from_offer(receive_offer)

    give_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in give_raw]
    receive_items = [enrich_item(i, rolimons, {}, settings["add_unvalued_to_total"]) for i in receive_raw]

    progress_line("Calculating value", 4, 6, color=Term.CYAN)
    analysis = analyze_trade(give_items, receive_items, settings["high_value_alert_threshold"])

    progress_line("Scoring risk", 5, 6, color=Term.CYAN)
    incoming_risk = risk_score_for_items(receive_items)
    outgoing_risk = risk_score_for_items(give_items)

    progress_line("Building report", 6, 6, color=Term.GREEN)

    page = 1
    while True:
        render_analysis_page(page, trade_id, receive_user, analysis, give_items, receive_items, incoming_risk, outgoing_risk)
        print()
        print(c("Options", Term.BOLD + Term.CYAN))
        print("  1) Verdict/math")
        print("  2) Item breakdown")
        print("  3) Graphs/links")
        print("  B) Back to trade panel")
        choice = input(c("\nChoose: ", Term.CYAN)).strip().lower()

        if choice == "1":
            page = 1
        elif choice == "2":
            page = 2
        elif choice == "3":
            page = 3
        elif choice == "b":
            return
        else:
            print(c("Invalid choice.", Term.RED))
            time.sleep(0.5)



def show_inbound_trade_panel() -> None:
    while True:
        clear_screen()
        print_banner()
        section("Inbound trade panel", "current inbound trades with profit/value/projected details")

        settings = settings_from_env()
        try:
            session = make_roblox_session(settings["cookie"])
            me = fetch_authenticated_user(session)
            my_user_id = int(me["id"])
            rolimons = fetch_rolimons_items()
            trades = fetch_inbound_trades(session)
        except Exception as error:
            print(c(f"Could not load inbound trades: {error}", Term.RED))
            pause()
            return

        if not trades:
            print(c("  No current inbound trades.", Term.GRAY))
            pause()
            return

        for idx, trade in enumerate(trades, start=1):
            print_trade_details_in_panel(idx, trade, session, my_user_id, rolimons, settings)

        print(c("Analysis options", Term.BOLD + Term.CYAN))
        print("  Type a trade number to analyze the trade or select one of the following options below.")
        print("  R) Refresh panel")
        print("  B) Back")
        choice = input(c("\nChoose: ", Term.CYAN)).strip().lower()

        if choice == "b":
            return
        if choice == "r":
            continue
        try:
            index = int(choice) - 1
            if 0 <= index < len(trades):
                analyze_selected_trade(trades[index], session, my_user_id, rolimons, settings)
            else:
                print(c("Invalid trade number.", Term.RED))
                pause()
        except ValueError:
            print(c("Invalid choice.", Term.RED))
            pause()


def show_declined_trade_panel() -> None:
    clear_screen()
    print_banner()
    section("Declined/status panel", "local history from live scanner status changes")

    history = load_declined_history()
    if not history:
        print(c("  No declined/status updates saved yet.", Term.GRAY))
        print(c("  Keep live mode running so Bloxware can detect when inbound trades disappear/change status.", Term.GRAY))
        pause()
        return

    for idx, trade in enumerate(reversed(history[-25:]), start=1):
        print(f"  {c(str(idx) + ')', Term.YELLOW)} Status: {c(str(trade.get('status', 'Unknown')), Term.RED)}")
        print(f"     Display:  {trade.get('trader_display', 'Unknown')}")
        print(f"     Username: @{trade.get('trader_username', 'Unknown')}")
        print(f"     Saved:    {trade.get('time', 'Unknown')}")
        print()

    pause()


def show_trade_panel() -> None:
    while True:
        clear_screen()
        print_banner()
        section("Trade panel", "view trades without opening Discord or Slack")
        print("  1) View current inbound trades")
        print("  2) View declined/status history")
        print("  3) Back")
        choice = input(c("\nChoose: ", Term.CYAN)).strip()

        if choice == "1":
            show_inbound_trade_panel()
        elif choice == "2":
            show_declined_trade_panel()
        elif choice == "3":
            return



# ---------- processing ----------

def process_trade(
    trade_id: str,
    session: requests.Session,
    my_user_id: int,
    rolimons: Dict[str, Dict[str, Any]],
    settings: Dict[str, Any],
) -> bool:
    try:
        details = fetch_trade_details_with_retry(session, trade_id)
    except HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        print(c(f"Skipped trade {trade_id}: Roblox returned {status}. It may be inaccessible, expired, or already changed.", Term.YELLOW))
        return False
    except Exception as error:
        print(c(f"Skipped trade {trade_id}: {error}", Term.YELLOW))
        return False

    payload, files, high_alert, value_diff = build_discord_payload_and_files(
        trade_id=trade_id,
        trade_details=details,
        my_user_id=my_user_id,
        rolimons=rolimons,
        settings=settings,
    )

    sent = 0
    if provider_allows(settings, "discord"):
        sent = send_to_active_webhooks(settings, payload, files, event="inbound")

    slack_sent = send_slack_trade_alert(settings, trade_id, details, my_user_id, rolimons, value_diff, high_alert, files)

    if high_alert and provider_allows(settings, "discord"):
        send_high_value_alert_spam(settings, trade_id, value_diff)

    slack_text = "sent" if slack_sent else ("off" if not provider_allows(settings, "slack") or not settings.get("slack_enabled") else "failed/skipped")
    print(c(f"Processed trade {trade_id}. Discord sent: {sent} | Slack: {slack_text}.", Term.GREEN))
    return True


def rapid_initial_scan(
    session: requests.Session,
    my_user_id: int,
    rolimons: Dict[str, Dict[str, Any]],
    settings: Dict[str, Any],
    seen: set[str],
    boot_started_utc: datetime,
) -> int:
    inbound = fetch_inbound_trades(session)
    sent = 0

    section("Initial scan", "sending current inbound trades one-by-one")
    print(f"  Found {len(inbound)} inbound trade(s).")

    total = max(len(inbound), 1)
    scanned = 0

    for trade in reversed(inbound):
        scanned += 1
        progress_line("Scanning inbound", scanned, total, color=Term.YELLOW)

        trade_id = get_trade_id(trade)
        if not trade_id:
            continue

        created_dt = parse_trade_datetime(trade.get("created"))

        if not settings["initial_scan_notify"]:
            # Timestamp-aware ignore: anything already present before boot is marked as seen.
            if created_dt is None or created_dt <= boot_started_utc:
                print(c(f"  Ignoring old inbound trade {trade_id}.", Term.GRAY))
                seen.add(trade_id)
                continue

        if settings["initial_scan_notify"]:
            # Startup flood intentionally attempts every currently inbound trade, even if seen before.
            print(c(f"  Sending startup trade {trade_id}...", Term.BLUE))
            if process_trade(trade_id, session, my_user_id, rolimons, settings):
                sent += 1
            time.sleep(1.2)

        seen.add(trade_id)

    save_seen_trade_ids(seen)
    return sent


def boot_context(settings: Dict[str, Any]) -> Tuple[requests.Session, int, Dict[str, Dict[str, Any]], set[str]]:
    section("Boot checklist", "starting systems with breathing room")
    progress_line("Booting notifier", 1, 4, color=Term.CYAN)

    session = make_roblox_session(settings["cookie"])
    print(c("  Cookie loaded locally. It will not be printed.", Term.GREEN))
    print()

    progress_line("Authenticating", 2, 4, color=Term.CYAN)
    me = fetch_authenticated_user(session)
    my_user_id = int(me["id"])
    print(c(f"  Authenticated as {me.get('displayName')} (@{me.get('name')}).", Term.GREEN))
    print()

    progress_line("Loading Rolimons", 3, 4, color=Term.CYAN)
    try:
        rolimons = fetch_rolimons_items()
        print(c(f"  Loaded {len(rolimons):,} Rolimons item records.", Term.GREEN))
    except Exception as error:
        rolimons = {}
        print(c(f"  Warning: could not load Rolimons data: {error}", Term.YELLOW))
    print()

    seen = load_seen_trade_ids()
    progress_line("Ready", 4, 4, color=Term.GREEN)

    return session, my_user_id, rolimons, seen



def check_runtime_requirements() -> None:
    section("Requirement check", "verifying installed packages")
    packages = [
        ("requests", "requests"),
        ("python-dotenv", "dotenv"),
        ("Pillow", "PIL"),
        ("slack_sdk", "slack_sdk"),
    ]

    missing = []
    for idx, (display, module) in enumerate(packages, start=1):
        ok = importlib.util.find_spec(module) is not None
        progress_line(f"Checking {display}", idx, len(packages), color=Term.GREEN if ok else Term.YELLOW)
        if not ok:
            missing.append(display)

    if missing:
        print(c("\nMissing optional/required package(s): " + ", ".join(missing), Term.YELLOW))
        print(c("Run: pip install -r requirements.txt", Term.GRAY))
        print(c("slack_sdk is only required for Slack PNG image uploads.", Term.GRAY))
    print()


def background_monitor_loop(settings: Dict[str, Any], run_minutes: Optional[int]) -> None:
    try:
        boot_started_utc = datetime.now(timezone.utc)
        session, my_user_id, rolimons, seen = boot_context(settings)
        rapid_initial_scan(session, my_user_id, rolimons, settings, seen, boot_started_utc)

        end_at = None
        if run_minutes is not None:
            end_at = datetime.now(timezone.utc) + timedelta(minutes=run_minutes)

        checks = 0
        while True:
            if end_at and datetime.now(timezone.utc) >= end_at:
                log_background("Background scanner finished.")
                BACKGROUND_STATUS["active"] = False
                return

            inbound = fetch_inbound_trades(session)
            current_active_ids = {str(t["id"]) for t in inbound if t.get("id") is not None}
            previous_active_ids = load_active_inbound_ids()
            check_for_declined_or_removed_trades(previous_active_ids, current_active_ids, session, my_user_id, settings)
            save_active_inbound_ids(current_active_ids)

            new_count = 0
            for trade in reversed(inbound):
                trade_id = get_trade_id(trade)
                if not trade_id or trade_id in seen:
                    continue
                if process_trade(trade_id, session, my_user_id, rolimons, settings):
                    new_count += 1
                seen.add(trade_id)

            if new_count:
                save_seen_trade_ids(seen)
                log_background(f"Sent {new_count} new trade notification(s).")
                BACKGROUND_STATUS["sent"] += new_count

            checks += 1
            BACKGROUND_STATUS["checks"] = checks
            log_background(f"Check #{checks} complete. New trades: {new_count}.")
            time.sleep(settings["interval"])
    except Exception as error:
        log_background(f"Background scanner stopped: {error}")
        BACKGROUND_STATUS["active"] = False


def start_background_notifier(settings: Dict[str, Any], run_minutes: Optional[int]) -> None:
    BACKGROUND_STATUS["active"] = True
    BACKGROUND_STATUS["mode"] = "timed task" if run_minutes is not None else "normal boot"
    BACKGROUND_STATUS["providers"] = settings.get("provider_mode", "both")
    BACKGROUND_STATUS["checks"] = 0
    BACKGROUND_STATUS["sent"] = 0
    log_background("Background scanner starting...")

    thread = threading.Thread(
        target=background_monitor_loop,
        args=(settings, run_minutes),
        daemon=True,
    )
    thread.start()
    BACKGROUND_THREADS.append(thread)
    print(c("Background scanner started. Returning to home menu.", Term.GREEN))
    print(c("Keep this terminal open; closing it stops the background scanner.", Term.GRAY))
    pause()


def run_notifier(run_minutes: Optional[int] = None, provider_mode: str = "both") -> None:
    clear_screen()
    print_banner()
    print_features()

    settings = settings_from_env()
    settings["provider_mode"] = provider_mode

    if provider_allows(settings, "discord") and not active_webhooks(settings["webhooks"], "inbound"):
        print(c("\nNo active inbound Discord webhooks. Open Settings > Manage Discord webhooks first, or run Slack-only.", Term.RED))
        pause()
        return

    if provider_allows(settings, "slack") and not settings.get("slack_enabled"):
        print(c("\nSlack is not enabled. Open Settings > Slack setup/notifications, or run Discord-only.", Term.RED))
        pause()
        return

    print()
    print(c("Run style", Term.BOLD + Term.BLUE))
    print("  1) Foreground live mode")
    print("  2) Keep running in background and go home")
    style = input(c("Choose [1]: ", Term.CYAN)).strip()
    if style == "2":
        start_background_notifier(settings, run_minutes)
        return

    boot_started_utc = datetime.now(timezone.utc)
    session, my_user_id, rolimons, seen = boot_context(settings)

    sent = rapid_initial_scan(session, my_user_id, rolimons, settings, seen, boot_started_utc)
    print(c(f"\nInitial scan complete. Sent {sent} notification(s).", Term.GREEN))

    end_at = None
    if run_minutes is not None:
        end_at = datetime.now(timezone.utc) + timedelta(minutes=run_minutes)
        print(c(f"Timed task active for {run_minutes} minute(s).", Term.YELLOW))

    section("Live mode", f"checking every {settings['interval']} seconds")
    print(c("Press Ctrl+C to stop.", Term.GRAY))

    checks_ran = 0

    while True:
        try:
            if end_at and datetime.now(timezone.utc) >= end_at:
                sys.stdout.write("\n")
                print(c("Timed task finished.", Term.GREEN))
                break

            inbound = fetch_inbound_trades(session)
            current_active_ids = {str(t["id"]) for t in inbound if t.get("id") is not None}
            previous_active_ids = load_active_inbound_ids()
            check_for_declined_or_removed_trades(previous_active_ids, current_active_ids, session, my_user_id, settings)
            save_active_inbound_ids(current_active_ids)
            new_count = 0

            for trade in reversed(inbound):
                trade_id = get_trade_id(trade)
                if not trade_id or trade_id in seen:
                    continue

                process_trade(trade_id, session, my_user_id, rolimons, settings)
                seen.add(trade_id)
                new_count += 1

            checks_ran += 1

            if new_count:
                save_seen_trade_ids(seen)
                sys.stdout.write("\n")
                print(c(f"Sent {new_count} new trade notification(s).", Term.GREEN))
            else:
                sys.stdout.write(f"\r{c('No new trades.', Term.GRAY)} Live check #{checks_ran} complete.\033[K")
                sys.stdout.flush()

            countdown_bar(settings["interval"], checks_ran)

        except KeyboardInterrupt:
            print(c("\nStopped.", Term.YELLOW))
            break
        except Exception as error:
            print(c(f"Error: {error}", Term.RED))
            countdown_bar(settings["interval"], checks_ran)



def show_discord_setup_guide() -> None:
    clear_screen()
    print_banner()
    section("Discord setup guide", "best for PC + full trade cards/images")

    steps = [
        ("1", "Open Discord on desktop or web."),
        ("2", "Go to your server, then pick the channel for trade alerts."),
        ("3", "Click the channel gear → Integrations → Webhooks."),
        ("4", "Create a webhook, name it something like Bloxware Trades."),
        ("5", "Copy the webhook URL."),
        ("6", "Come back here → Settings → Manage Discord webhooks → Add Discord webhook."),
        ("7", "Paste the URL and send a test message."),
    ]

    print(c("  Discord is the main full-detail view.", Term.BLUE))
    print(c("  It gets the embeds, item panels, photos, and trade summary.\n", Term.GRAY))

    for num, body in steps:
        print(f"  {c(num + ')', Term.GREEN)} {body}")

    print(c("\nTip: use a dedicated channel like #trade-alerts so trade notifications do not get buried.", Term.YELLOW))
    pause()


def show_slack_setup_guide() -> None:
    show_slack_tutorial()



def show_background_tracker() -> None:
    while True:
        clear_screen()
        print_banner()
        section("Background tracker", "scanner status while you use the menu")

        active = BACKGROUND_STATUS.get("active", False)
        print(f"  Active:    {c('YES', Term.GREEN) if active else c('NO', Term.GRAY)}")
        print(f"  Mode:      {BACKGROUND_STATUS.get('mode', '')}")
        print(f"  Providers: {BACKGROUND_STATUS.get('providers', '')}")
        print(f"  Checks:    {BACKGROUND_STATUS.get('checks', 0)}")
        print(f"  Sent:      {BACKGROUND_STATUS.get('sent', 0)}")
        print(f"  Last:      {BACKGROUND_STATUS.get('last', 'none')}")
        print()
        print(c("Recent logs", Term.BOLD + Term.BLUE))
        for line in BACKGROUND_LOGS[-18:]:
            print(f"  {line}")
        print()
        print("  R) Refresh")
        print("  B) Back")
        choice = input(c("\nChoose: ", Term.CYAN)).strip().lower()
        if choice == "b":
            return



def main_menu() -> None:
    while True:
        clear_screen()
        print_banner()
        print_features()
        settings = settings_from_env()
        hooks = active_webhooks(settings["webhooks"], "inbound")
        declined_hooks = active_webhooks(settings["webhooks"], "declined")
        slack_on = settings.get("slack_enabled") and valid_slack_webhook_format(settings.get("slack_webhook_url", ""))

        if BACKGROUND_STATUS.get("active"):
            section("Active scanner", "background scanner is running")
            print(f"  Providers: {c(str(BACKGROUND_STATUS.get('providers', '')), Term.GREEN)}")
            print(f"  Checks:    {BACKGROUND_STATUS.get('checks', 0)}")
            print(f"  Sent:      {BACKGROUND_STATUS.get('sent', 0)}")
            print(f"  Last:      {BACKGROUND_STATUS.get('last', 'starting...')}")

        section("Main menu", "choose how you want to run it")
        print(f"  1) Normal boot          {c('rapid scan + live mode', Term.GREEN)}")
        print(f"  2) Timed task           {c('run for a set number of minutes', Term.YELLOW)}")
        print(f"  3) Trade panel          {c('view, analyze, and compare trades', Term.CYAN)}")
        print(f"  4) Background tracker   {c('view active scanner updates', Term.GREEN if BACKGROUND_STATUS.get('active') else Term.GRAY)}")
        print(f"  5) Settings             {c(f'{len(hooks)} inbound / {len(declined_hooks)} declined webhook(s)', Term.BLUE)} / Slack: {c('on' if slack_on else 'off', Term.GREEN if slack_on else Term.GRAY)}")
        print(f"  6) Discord setup guide  {c('PC + full embeds/images', Term.CYAN)}")
        print(f"  7) Slack setup guide    {c('iPhone + detailed text alerts', Term.MAGENTA)}")
        print(f"  8) Contact              {c(CONTACT_URL, Term.MAGENTA)}")
        print("  9) Exit")

        choice = input(c("\nChoose: ", Term.CYAN)).strip()

        if choice == "1":
            mode = choose_provider_mode("both")
            run_notifier(provider_mode=mode)
            pause()

        elif choice == "2":
            raw = input("How many minutes should it run? ").strip()
            try:
                minutes = max(1, int(raw))
            except ValueError:
                print(c("Invalid minutes.", Term.RED))
                pause()
                continue
            mode = choose_provider_mode("both")
            run_notifier(run_minutes=minutes, provider_mode=mode)
            pause()

        elif choice == "3":
            show_trade_panel()

        elif choice == "4":
            show_background_tracker()

        elif choice == "5":
            show_settings_menu()

        elif choice == "6":
            show_discord_setup_guide()

        elif choice == "7":
            show_slack_setup_guide()

        elif choice == "8":
            print(c(f"Opening: {CONTACT_URL}", Term.MAGENTA))
            try:
                webbrowser.open(CONTACT_URL)
            except Exception:
                pass
            pause()

        elif choice == "9":
            print(c("happy trading!", Term.MAGENTA))
            return


def main() -> None:
    require_admin()
    enable_ansi()
    clear_screen()
    print_banner()
    check_runtime_requirements()
    ensure_env_ready()
    main_menu()


if __name__ == "__main__":
    main()
