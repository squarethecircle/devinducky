"""Find the Devin API key: environment first, then the user's login shell.

launchd doesn't source shell profiles, so under launchd the key is read once
from `$SHELL -lic` and kept only in memory.
"""

import os
import subprocess


class NoApiKey(Exception):
    pass


def api_key():
    key = os.environ.get("DEVIN_API_KEY", "").strip()
    if key:
        return key
    shell = os.environ.get("SHELL", "/bin/zsh")
    try:
        out = subprocess.run([shell, "-lic", "printenv DEVIN_API_KEY"],
                             capture_output=True, text=True, timeout=15,
                             stdin=subprocess.DEVNULL)
        key = out.stdout.strip().splitlines()[-1].strip() if out.stdout.strip() else ""
    except (OSError, subprocess.TimeoutExpired):
        key = ""
    if not key:
        raise NoApiKey("DEVIN_API_KEY is not set in the environment or your login shell")
    return key
