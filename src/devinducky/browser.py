"""Read the active browser tab's URL with AppleScript and pull out a Devin session ID."""

import logging
import re
import subprocess

log = logging.getLogger(__name__)

# AppleScript for the active tab's URL, per browser family.
_CHROMIUM = 'tell application "{app}" to get URL of active tab of front window'
_SAFARI = 'tell application "{app}" to get URL of front document'
SCRIPTS = {
    "Google Chrome": _CHROMIUM, "Arc": _CHROMIUM, "Brave Browser": _CHROMIUM,
    "Microsoft Edge": _CHROMIUM, "Chromium": _CHROMIUM,
    "Safari": _SAFARI,
}


class BrowserError(Exception):
    pass


def _osascript(script, timeout=5):
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise BrowserError(out.stderr.strip() or "osascript failed")
    return out.stdout.strip()


def frontmost_app():
    return _osascript('tell application "System Events" to get name of first application process '
                      'whose frontmost is true')


def running(app):
    return _osascript(f'application "{app}" is running') == "true"


def active_tab_url(browsers):
    """URL of the active tab in the frontmost supported browser, else the first running one."""
    try:
        front = frontmost_app()
    except BrowserError:
        front = None
    order = ([front] if front in browsers else []) + [b for b in browsers if b != front]
    errors = []
    for app in order:
        script = SCRIPTS.get(app)
        if not script:
            continue
        try:
            if app != front and not running(app):
                continue
            return app, _osascript(script.format(app=app))
        except (BrowserError, subprocess.TimeoutExpired) as e:
            errors.append(f"{app}: {e}")
    raise BrowserError("; ".join(errors) or "no supported browser is running")


# One Apple Event fetches every tab URL; the loops below run locally in AppleScript,
# which is ~5x faster than asking the browser tab by tab.
_LIST_TABS = '''
tell application "{app}" to set u to URL of tabs of windows
set out to ""
repeat with wi from 1 to count u
    set wl to item wi of u
    repeat with ti from 1 to count wl
        set out to out & wi & tab & ti & tab & (item ti of wl) & linefeed
    end repeat
end repeat
return out
'''
_FOCUS = {
    "chromium": 'tell application "{app}"\nset active tab index of window {w} to {t}\n'
                'set index of window {w} to 1\nactivate\nend tell',
    "Arc": 'tell application "Arc"\ntell tab {t} of window {w} to select\nactivate\nend tell',
    "Safari": 'tell application "Safari"\nset current tab of window {w} to tab {t} of window {w}\n'
              'set index of window {w} to 1\nactivate\nend tell',
}


def parse_tab_list(out):
    """'w<TAB>t<TAB>url' lines -> [(window, tab, url)]."""
    tabs = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            tabs.append((int(parts[0]), int(parts[1]), parts[2]))
    return tabs


def focus_tab(browsers, needle):
    """Bring an already-open tab whose URL contains `needle` to the front.

    Only browsers that are already running are searched (so nothing gets launched).
    Returns the browser name if a tab was focused, else None.
    """
    for app in browsers:
        if app not in SCRIPTS:
            continue
        try:
            if not running(app):
                continue
            tabs = parse_tab_list(_osascript(_LIST_TABS.replace("{app}", app)))
            hit = next(((w, t) for w, t, url in tabs if needle in url), None)
            if not hit:
                continue
            tpl = _FOCUS.get(app, _FOCUS["chromium"])
            _osascript(tpl.replace("{app}", app).replace("{w}", str(hit[0])).replace("{t}", str(hit[1])))
            return app
        except (BrowserError, subprocess.TimeoutExpired) as e:
            log.warning("focus_tab %s: %s", app, e)
            continue
    return None


def session_id_from_url(url, pattern):
    """Extract the session ID in the bare form the API returns as `session_id`.

    The API accepts both `devin-<hex>` and `<hex>` in paths but reports the bare
    one, so we store that to keep bindings and poll results comparable.
    """
    m = re.search(pattern, url or "")
    if not m:
        return None
    return m.group(1).removeprefix("devin-")
