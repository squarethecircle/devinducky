import struct

import pytest

from devinducky import browser, hid, keys, state
from devinducky.bindings import Bindings
from devinducky.config import DEFAULTS
from devinducky.input import HoldClassifier, decode


# ---------- state ----------

@pytest.mark.parametrize("status,detail,expected", [
    ("new", None, "starting"), ("claimed", None, "starting"), ("resuming", None, "starting"),
    ("running", "working", "working"), ("running", None, "working"),
    ("running", "waiting_for_user", "waiting"), ("running", "waiting_for_approval", "approval"),
    ("running", "finished", "finished"),
    ("suspended", "inactivity", "idle"), ("suspended", "user_request", "idle"),
    ("suspended", "out_of_credits", "error"), ("suspended", "usage_limit_exceeded", "error"),
    ("suspended", "error", "error"), ("error", None, "error"), ("exit", None, "ended"),
    ("running", "something_new", "working"), ("brand_new_status", None, "working"),
])
def test_display_state(status, detail, expected):
    assert state.display_state({"status": status, "status_detail": detail}) == expected


def test_archived_is_ended_and_none_is_unbound():
    assert state.display_state({"status": "running", "status_detail": "working", "is_archived": True}) == "ended"
    assert state.display_state(None) == "unbound"


def test_transitions_only_notable_changes():
    prev = {"a": "working", "b": "working", "c": "waiting", "d": "working"}
    cur = {"a": "waiting", "b": "working", "c": "waiting", "d": "idle", "e": "finished"}
    assert state.transitions(prev, cur) == [("a", "working", "waiting")]


def test_summary_gvs():
    g = state.summary_gvs(["working", "waiting", "finished", "approval"], 2, "finished", 0)
    assert g == {20: state.CODE["approval"], 21: 2, 22: 1, 23: 1, 24: 3, 25: state.CODE["finished"], 26: 0, 27: 4}
    assert state.summary_gvs([], None, None, 1)[20] == 0


def test_parse_ts():
    assert state.parse_ts("1970-01-01T00:01:00Z") == 60
    assert state.parse_ts(5) == 5.0 and state.parse_ts("junk") is None


# ---------- bindings ----------

def test_bind_move_unbind_roundtrip(tmp_path):
    b = Bindings(str(tmp_path / "b.json"), 12)
    assert b.bind(0, "s1") is None
    assert b.bind(3, "s2") is None
    assert b.bind(5, "s1") == 0                   # moves from slot 0
    assert b.get(0) is None and b.get(5) == "s1"
    assert b.bind(3, "s3") is None                # rebind replaces s2
    assert b.slot_of("s2") is None
    b.save()
    b2 = Bindings(str(tmp_path / "b.json"), 12).load()
    assert b2.slots == {3: "s3", 5: "s1"}
    assert b2.unbind(3) == "s3" and b2.first_free() == 0


def test_bindings_ignore_bad_file(tmp_path):
    p = tmp_path / "b.json"
    p.write_text('{"0": "a", "40": "out-of-range", "1": ""}')
    assert Bindings(str(p), 12).load().slots == {0: "a"}
    p.write_text("not json")
    assert Bindings(str(p), 12).load().slots == {}


# ---------- browser URL parsing ----------

@pytest.mark.parametrize("url,expected", [
    ("https://app.devin.ai/sessions/7f29616947aa4d3fa98317c42e008493", "7f29616947aa4d3fa98317c42e008493"),
    ("https://app.devin.ai/sessions/7f29616947aa4d3fa98317c42e008493?tab=shell#x", "7f29616947aa4d3fa98317c42e008493"),
    ("https://app.devin.ai/sessions/devin-abc123", "abc123"),
    ("https://app.devin.ai/sessions", None),
    ("https://github.com/foo", None), ("", None), (None, None),
])
def test_session_id_from_url(url, expected):
    assert browser.session_id_from_url(url, DEFAULTS["session_url_regex"]) == expected


# ---------- HID packets ----------

def test_set_led_packet():
    p = hid.build_set_led(7, (300, 128, -5))
    assert len(p) == 64 and p[:7] == bytes([0x05, 0, 0x04, 7, 255, 128, 0]) and not any(p[7:])
    with pytest.raises(ValueError):
        hid.build_set_led(20, (0, 0, 0))


def test_write_gv_packets_split():
    pkts = hid.build_write_gv({i: i * 1000 for i in range(14)})
    assert len(pkts) == 2
    p = pkts[0]
    assert p[2] == 0x19 and p[3] == 0x80 and struct.unpack_from("<I", p, 4)[0] == 0
    assert p[8] == 0x81 and struct.unpack_from("<I", p, 9)[0] == 1000
    assert pkts[1][3] == 0x80 | 12


def test_parse_info():
    r = bytearray(64)
    r[3:7] = bytes([2, 1, 0, 24])
    r[7:11] = struct.pack("<I", 1234)
    r[11] = 3
    info = hid.parse_info(r)
    assert (info.firmware, info.hw_rev, info.serial, info.profile, info.sleeping) == ("2.1.0", 24, 1234, 3, False)


# ---------- hotkeys ----------

def test_hotkey_table_unique_and_roundtrips():
    assert len(set(keys.HOTKEY_FOR.values())) == len(keys.EVENTS)
    for ev, hk in keys.HOTKEY_FOR.items():
        assert decode(set(hk.mods), hk.fkey) == ev
    assert decode({"ctrl"}, "f13") is None


def test_every_slot_has_down_and_up():
    for k in keys.SLOT_KEYS:
        assert keys.Event("down", k) in keys.HOTKEY_FOR and keys.Event("up", k) in keys.HOTKEY_FOR


# ---------- tap vs hold ----------

def test_tap_vs_hold():
    c = HoldClassifier(700)
    c.down(1, 0.0)
    assert c.due(0.5) == [] and c.up(1, 0.6) == "tap"
    c.down(2, 1.0)
    assert c.due(1.69) == [] and c.due(1.71) == [2] and c.due(2.0) == []
    assert c.up(2, 2.5) is None                   # hold already fired; release is ignored
    assert c.up(9, 3.0) is None                   # stray release


# ---------- pad profile ----------

def test_build_profile(tmp_path):
    from devinducky.cli import build_profile
    cfg = dict(DEFAULTS, launch=[{"name": "Fix CI", "prompt": "x"}])
    pdir = build_profile(cfg, str(tmp_path))
    files = set(__import__("os").listdir(pdir))
    assert {"config.txt", "key1.txt", "key1-release.txt", "key13.txt", "key20.txt", "key23.txt"} <= files
    assert "key13-release.txt" not in files
    conf = open(f"{pdir}/config.txt").read().splitlines()
    assert "z1 S1" in conf and "dr 1" in conf and "z13 Fix C" in conf and "dr 20" in conf
    assert all(f"z{k} " in "\n".join(conf) for k in range(1, 27))
    assert open(f"{pdir}/key1.txt").read() == keys.HOTKEY_FOR[keys.Event("down", 1)].ducky() + "\n"


def test_parse_tab_list():
    out = "1\t1\thttps://a.com/x,y\n1\t2\thttps://app.devin.ai/sessions/abc\n2\t1\t\njunk\n"
    assert browser.parse_tab_list(out) == [
        (1, 1, "https://a.com/x,y"), (1, 2, "https://app.devin.ai/sessions/abc"), (2, 1, "")]


def test_top_wheel_switches_to_session_after_settling(tmp_path, monkeypatch):
    from devinducky import daemon
    from devinducky.render import Frame
    d = daemon.Daemon.__new__(daemon.Daemon)
    d.bindings = Bindings(str(tmp_path / "b.json"), keys.NUM_SLOTS)
    d.bindings.bind(0, "aaa")
    d.bindings.bind(3, "ddd")
    d.cursor, d.goto_due, d.sessions, d.frame = None, None, {}, Frame()
    opened = []
    monkeypatch.setattr(d, "open_slot", opened.append, raising=False)
    d.handle("press", keys.ENC1_CW)
    d.handle("press", keys.ENC1_CW)
    assert d.cursor == 3 and opened == []           # nothing until the wheel stops
    assert d.goto_due is not None
    d.handle("press", keys.ENC1_CCW)
    assert d.cursor == 0


def test_mods_from_event_flags():
    from devinducky.input import mods_from_flags
    assert mods_from_flags(0x40000 | 0x80000 | 0x800000) == {"ctrl", "alt"}   # Fn flag ignored
    assert decode(mods_from_flags(0x40000 | 0x80000 | 0x20000 | 0x100000), "f13") is None
