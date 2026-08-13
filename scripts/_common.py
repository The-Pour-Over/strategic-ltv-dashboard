"""Shared plumbing for the action-center producer scripts: credential loading
from standard locations (never hardcoded, never committed) and data-dir
resolution so every script can write into either this repo's
action-center/data/ or the dashboard repo's client/public/data/.
"""
import os, sys


def load_env_file(path):
    env = {}
    p = os.path.expanduser(path)
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def meta_creds():
    """Meta Graph API token + version: env vars first, ~/.secrets/meta-ads.env fallback."""
    env = load_env_file("~/.secrets/meta-ads.env")
    env.update({k: v for k, v in os.environ.items() if k.startswith("META_")})
    token = env.get("META_ADS_TOKEN") or env.get("META_ADS_ACCESS_TOKEN")
    if not token:
        sys.exit("No Meta token: set META_ADS_TOKEN (or META_ADS_ACCESS_TOKEN) or put it in ~/.secrets/meta-ads.env")
    return token, env.get("META_GRAPH_VERSION", "v23.0")


def beehiiv_key():
    """Beehiiv API key: BEEHIIV_API_KEY env, then ~/.config/po-secrets/beehiiv.env, then ~/.secrets/beehiiv.env."""
    key = os.environ.get("BEEHIIV_API_KEY")
    if key:
        return key
    for p in ("~/.config/po-secrets/beehiiv.env", "~/.secrets/beehiiv.env"):
        key = load_env_file(p).get("BEEHIIV_API_KEY")
        if key and key != "PASTE_KEY_HERE":
            return key
    sys.exit("No beehiiv key: set BEEHIIV_API_KEY or put it in ~/.config/po-secrets/beehiiv.env")


def resolve_data_dir(explicit=None):
    """--data wins; otherwise the first existing of action-center/data, client/public/data, data (cwd-relative)."""
    if explicit:
        return explicit
    for cand in ("action-center/data", "client/public/data", "data"):
        if os.path.isdir(cand):
            return cand
    sys.exit("No data dir found — pass --data <dir> (looked for action-center/data, client/public/data, data)")
