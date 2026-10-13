# devinducky

Watch and drive [Devin](https://docs.devin.ai/api-reference/overview) sessions from a [duckyPad Pro](https://github.com/duckyPad/duckyPad-Pro).
Bind keys to sessions, see each one's state on its LED, jump to a session with one tap, and launch new ones from presets.
Inspired by [claude-pad](https://github.com/URL42/claude-pad).

macOS only, because it uses AppleScript to read and focus browser tabs.

## Layout

```
 ┌──────┬──────┬──────┬──────┐
 │ S1   │ S2   │ S3   │ S4   │  session slots, all empty until you bind them
 ├──────┼──────┼──────┼──────┤    hold (~0.7 s) = bind to the Devin session in your active browser tab
 │ S5   │ S6   │ S7   │ S8   │                    (hold on a non-Devin tab = unbind)
 ├──────┼──────┼──────┼──────┤    tap           = go to that session
 │ S9   │ S10  │ S11  │ S12  │    LED           = session state
 ├──────┼──────┼──────┼──────┤
 │ L1   │ L2   │ L3   │ L4   │  launch presets: tap to arm (blinks), tap again within 3 s to launch
 ├──────┼──────┼──────┼──────┤
 │ NEW  │ DASH │ REFR │ INFO │  new-session page · sessions list · refresh now · OLED summary
 └──────┴──────┴──────┴──────┘
 upper encoder: rotate = step through bound sessions (the browser follows when you stop), push = open
 lower encoder: rotate = system volume, push = refresh
```

"Go to that session" first looks for a tab that already has the session open (Chrome, Arc, Brave, Edge, Chromium, Safari) and brings it to the front. It opens a new tab only if there isn't one.

A newly launched session opens in your browser. Hold an empty slot to bind it.

INFO shows a summary on the OLED for 5 seconds, or until you press another key. The summary includes the API status, how many sessions are waiting on you or working, and how many keys are bound.

| LED | Meaning |
|---|---|
| amber, pulsing | waiting for you |
| orange, fast pulse | waiting for approval |
| blue | working |
| cyan | starting / resuming |
| green (dims after 30 min) | finished |
| red | error, or suspended for limits / credits |
| dim white | suspended (inactivity / you paused it) |
| very dim | exited or archived |
| off | unbound |

Bindings live in `~/.devinducky/bindings.json` and survive restarts. A session that ends stays bound, showing very dim, until you rebind or unbind its key.

## How it works

The duckyPad can't report key presses over HID. Each key's on-press and on-release scripts therefore type a unique hotkey, such as `Ctrl+Alt+F13`. The daemon listens for these with `pynput` and times the gap between press and release to tell a tap from a hold.

In the other direction, the daemon drives the pad over HID. It sets each key's LED and writes global variables (`_GV20`–`_GV27`) that the INFO key's script reads. It polls the Devin v3 API only for the sessions that are bound. With nothing bound it makes no polling calls.

`gen-profile` builds the pad profile from the same key table the daemon uses, so the two can't drift apart.

## Setup

1. Put a Devin **Personal Access Token** in your shell profile: `export DEVIN_API_KEY=…`.
   - The daemon reads it from the environment. Under launchd it reads it from your login shell instead.
   - The key is never written to disk.
2. `uv sync`
3. `uv run devinducky gen-profile` writes `profile/duckyPad_Profile_devinducky.zip`. In the [duckyPad configurator](https://github.com/duckyPad/duckyPad-Configurator):
   1. **Import** the zip.
   2. **Save** to the pad.
   3. **Close the configurator.** It holds the device while it's open.
   - When you re-import, delete the old profile first, because Import adds a new copy.
   - Re-run `gen-profile` after renaming launch presets.
4. Grant **Accessibility** to your terminal in System Settings › Privacy & Security. Without it, no key presses are seen.
5. `uv run devinducky test-pad` cycles the LEDs and prints key down/up events with timings.
6. `uv run devinducky which-tab` prints the active tab's session ID. The first run triggers macOS's **Automation** prompt.
7. `uv run devinducky run -v` runs the daemon in the foreground.

### Running in the background

```sh
uv run devinducky install      # launchd agent com.devinducky.daemon, starts at login, restarts if it dies
tail -f ~/.devinducky/daemon.log
launchctl kickstart -k gui/$(id -u)/com.devinducky.daemon   # restart after code/config changes
uv run devinducky uninstall
```

Under launchd, the process that needs Accessibility is the venv's real Python binary, not your terminal. `install` prints its path. Add that path in System Settings.

## Config: `~/.devinducky/config.toml`

Every key is optional. The defaults are in [`src/devinducky/config.py`](src/devinducky/config.py).

```toml
poll_s = 10
hold_ms = 700
browsers = ["Google Chrome", "Arc", "Safari"]   # search / focus order
pad_profile = 0                     # only paint when this pad profile number is active (0 = any)
new_session_url = "https://app.devin.ai/"   # what the NEW key opens
notify = { waiting = true, finished = true, error = true }   # macOS banners
ntfy_url = ""                       # optionally also POST notifications here

[colors]
working = [0, 60, 255]

[[launch]]                          # L1..L4, in order
name   = "Fix CI"                   # first 5 chars become the key label
prompt = "Look at the latest failing CI run on main in org/repo and open a PR fixing it."
repos  = ["org/repo"]
color  = [120, 0, 255]
# also: playbook_id, title, devin_mode, max_acu_limit, tags
```

`uv run devinducky playbooks` lists your org's playbook IDs. Launched sessions are tagged `devinducky`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Keys do nothing | Is the daemon running? Does the right process have Accessibility? Is the pad on the devinducky profile? Check with `test-pad`. |
| LEDs never change | Close the duckyPad configurator. |
| Hold flashes red | The active tab isn't a Devin session, or Automation permission for the browser was denied. Check with `which-tab`. |
| INFO says API KEY ERROR | `DEVIN_API_KEY` is missing or invalid. Under launchd, make sure your login shell exports it. |

## Development

`uv run pytest`. The tests need no pad, network, or browser.

Hardware details are in [`hid.py`](src/devinducky/hid.py): VID `0x0483`, PID `0xD11D`, and the protocol from the [duckyPad HID docs](https://github.com/duckyPad/duckyPad-Profile-Autoswitcher/blob/master/HID_details.md). On macOS the device is opened non-exclusively, so other tools can share it.

## License

[MIT](LICENSE)
