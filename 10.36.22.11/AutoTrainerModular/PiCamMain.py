#!/usr/bin/python3

import os  # OS module (path, ...)
import io  # input/output module
import sys  # System utility module
from picamera2 import Picamera2  # Pi Camera module (Pi 5 compatible)
from picamera2.encoders import H264Encoder, MJPEGEncoder, Quality
from picamera2.outputs import FileOutput, Output
from libcamera import controls as libcamera_controls
import time  # Time module
import collections  # deque for the frame ring buffer
import json  # events.json for the stream page
import socket  # .dat lines from MainCode.py, for the event panel
import datetime  # Datetime utility
import logging  # Debugging tool
import gpiod  # GPIO utility (Pi 5 compatible)
from gpiod.line_settings import LineSettings, Direction, Edge, Bias
import numpy  # Numpy array toolbox
import threading  # threading utility
import csv  # CVS file reader
import netifaces  # Network interface to get IP
import argparse  # Input argument parser
import queue as queue  # Queue data stracture
import socketserver as socketserver  # Socket module - webcam
from http import server as server  # Http server
import glob  # File pattern search
import signal  # Exit signal detection
import re  # Regular expression module
from urllib.parse import urlparse  # URL helper
import StorageMonitor  # Background disk usage monitor

# Global gpiod resources for cleanup
_gpio_chip = None
_gpio_lines = None

state_lock = threading.Lock()
controller_status = {"camera_running": False}
schedule_cache = {"start_sec": [], "stop_sec": [], "start": [], "stop": []}
piCamWebOutput = None
piCamStreamServer = None
streamingThread = None


# MainCode.py forwards every .dat line here; see eventFeedLoop()
EVENT_UDP_ADDR = ("127.0.0.1", 9101)


def getTimeFormat(withTime=False, dash=False):
    """
    Get the current time format in YYYY-MM-DD HH-MM-SS.
    """

    now = datetime.datetime.now()
    if withTime:
        if dash:
            timeFormat = now.strftime("%Y-%m-%d-%H-%M-%S")
        else:
            timeFormat = now.strftime("%Y%m%d%H%M%S")
    else:
        if dash:
            timeFormat = now.strftime("%Y-%m-%d")
        else:
            timeFormat = now.strftime("%Y%m%d")

    return timeFormat


def readStateMachineNames(fileName="SetStateMachineTP.h"):
    """State machine names in the order of their numbers in the .dat (the
    FOREACH_STATEMACHINE list in the firmware)."""

    with open(fileName) as fh:
        text = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S))
    macro = re.search(r"#define\s+FOREACH_STATEMACHINE\(SM\)((?:[^\n]*\\\n)*[^\n]*)", text)
    return re.findall(r"SM\((\w+)\)", macro.group(1)) if macro else []


class EventFeed(object):
    """Last events and the current session's counts, for the stream page's panel
    (served as events.json). A session is one run of the state machine that
    reports trials; it starts over when that machine changes or restarts."""

    KEEP = 10

    def __init__(self):
        self.lock = threading.Lock()
        try:
            self.smNames = readStateMachineNames()
        except (OSError, re.error):
            self.smNames = []
        self.events = collections.deque(maxlen=self.KEEP)
        self.seq = 0
        self.sessionSm, self.sessionSince, self.lastSmTime = None, None, None
        self.trial, self.licksInTrial = None, 0
        self.counts = dict(trials=0, rewarded=0, pokesL=0, pokesR=0, pulses=0)

    def _add(self, label, kind, note=""):
        self.seq += 1
        self.events.appendleft(dict(
            time=datetime.datetime.now().strftime("%H:%M:%S.%f")[:12],
            label=label, kind=kind, note=note))

    def _newSession(self, sm):
        self.sessionSm, self.sessionSince = sm, datetime.datetime.now().strftime("%H:%M")
        self.counts = dict.fromkeys(self.counts, 0)
        self.trial, self.licksInTrial = None, 0

    def add(self, event, value, sm, smTime, label):
        """One .dat line; label is the video text it got (NOSEPOKE L/R, LICK) or None."""

        with self.lock:
            if sm == self.sessionSm and event != 83:  # 83's time field is a probability
                if self.lastSmTime is not None and smTime < self.lastSmTime - 1000:
                    self._newSession(sm)  # same machine started again
                self.lastSmTime = smTime
            if event == 81:
                if sm != self.sessionSm:
                    self._newSession(sm)
                    self.lastSmTime = smTime
                self.counts["trials"] += 1
                self.trial, self.licksInTrial = self.counts["trials"], 0
                self._add("TRIAL %d" % self.trial, "trial", "port " + {1: "L", 2: "R"}.get(value, str(value)))
            elif label == "LICK" and sm == self.sessionSm and self.trial:
                self.licksInTrial += 1
                self._add(label, "lick", "lick %d of trial %d" % (self.licksInTrial, self.trial))
            elif label == "LICK":
                self._add(label, "lick", self.smName(sm))
            elif label:
                self.counts["pokesL" if label.endswith("L") else "pokesR"] += 1
                self._add(label, "poke")
            elif event == 51 and sm == self.sessionSm:
                self.counts["rewarded"] += 1
                self.counts["pulses"] += value
                self._add("REWARD %d pulse%s" % (value, "" if value == 1 else "s"), "reward")
            elif event == 51:
                self._add("WATER %d pulse%s" % (value, "" if value == 1 else "s"), "reward",
                          self.smName(sm))
            elif event == -51:
                self._add("no reward", "none", "trial %d" % self.trial if self.trial else "")

    def smName(self, sm):
        return self.smNames[sm] if 0 <= sm < len(self.smNames) else "state machine %d" % sm

    def snapshot(self):
        with self.lock:
            return dict(
                seq=self.seq,
                events=list(self.events),
                counts=dict(self.counts),
                session=(dict(name=self.smName(self.sessionSm), since=self.sessionSince)
                         if self.sessionSm is not None else None),
            )


eventFeed = EventFeed()


SENSOR_KEYS = ("L", "R", "Lick")
SENSOR_DAY_MIN = 1440  # the panel's long strip: last 24 h in 1-min bins
SENSOR_RAW_MS = 600000  # the panel's raw trace: last 10 min of edges
SENSOR_RAW_CAP = 3000  # most edges sent per row (a chattering lick line makes ~50k)
SENSOR_FAST_MS = 20  # rising edges closer than this count as chatter
SENSOR_CACHE_DIR = os.path.expanduser("~/.cache/opcon_sensors")  # outside ExpData: never transferred
SENSOR_CACHE_EVERY_S = 300  # how often the panel's state is saved
SENSOR_CACHE_MAX_AGE_MS = (SENSOR_DAY_MIN + 60) * 60000  # an older cache is ignored


def localNowMs():
    """Local wall clock in ms, in the Teensy's convention (local time stored as UTC)."""

    return int((time.time() - time.timezone) * 1000)


def readSensorPins(fileName="SetHardwareConfig.h"):
    """{hardware name: Teensy pin} for every CreateHDW_DI/DO in the firmware config."""

    with open(fileName) as fh:
        text = re.sub(r"//.*", "", fh.read())
    return dict(
        (name, int(pin))
        for name, pin in re.findall(r'CreateHDW_D[IO]\((\w+),\s*"[^"]*",\s*(\d+)', text)
    )


class SensorTrace(object):
    """Nosepoke and lick lines for the stream page's sensor panel (served as
    sensors.json): per-minute bins over the last 24 h (fraction of the minute
    the sensor read in/contact, rising edges, edges < SENSOR_FAST_MS apart),
    the hourly level checks (code 98), each sensor's current state and since
    when, and the raw edges of the 10 min before the last sensor edge.
    Built by following the subject's .dat files. The state and the read
    position are saved every few minutes to a small cache outside ExpData, so
    a restart resumes where it was even after the day's .dat has moved to the
    NAS; without a cache it rebuilds from the .dat files still on the box."""

    SAVED = ("state", "since", "lastEdge", "rawInit", "changed", "approx", "lastEdgeMs",
             "lastPokeSm", "lastMs", "firstMs", "gaps")

    def __init__(self):
        self.lock = threading.Lock()
        self.codes = {}  # .dat event code (= Teensy pin) -> key
        self.levelPins = {}  # pin in code-98 rows -> (key, level meaning in/contact)
        self.bins = {}  # epoch minute -> {key: [inFraction, edges, fastEdges]}
        self.state = dict((k, 0) for k in SENSOR_KEYS)
        self.since = dict((k, None) for k in SENSOR_KEYS)  # ms the state was last settled
        self.lastEdge = dict((k, None) for k in SENSOR_KEYS)  # smTime of last rising edge
        self.levels = collections.deque()  # (ms, key, in)
        self.raw = collections.deque()  # (ms, key, state after the edge)
        self.rawInit = dict((k, 0) for k in SENSOR_KEYS)
        self.changed = dict((k, None) for k in SENSOR_KEYS)  # ms the current state began
        self.approx = dict((k, True) for k in SENSOR_KEYS)  # True: began at or before 'changed'
        self.lastEdgeMs = None  # ms of the last sensor edge (anchors the 10 min trace)
        self.lastPokeSm = None
        self.lastMs = None
        self.firstMs = None  # oldest data read (start of the oldest .dat still on the box)
        self.gaps = []  # [fromMs, toMs]: data lost while the camera was down and the .dat moved
        self.gapFrom = None
        self.ready = False

    def configure(self, pins):
        """Nosepoke edges are logged under their pin; licks show up as the camera
        line (GPIOOutDO), which also pulses with each nosepoke edge."""

        self.codes = {pins["Nosepoke1DI"]: "L", pins["Nosepoke2DI"]: "R", pins["GPIOOutDO"]: "Lick"}
        self.levelPins = {pins["Nosepoke1DI"]: ("L", 0), pins["Nosepoke2DI"]: ("R", 0)}  # LOW = nose in
        if "LickDI" in pins:
            self.levelPins[pins["LickDI"]] = ("Lick", 1)  # HIGH = contact

    def _bin(self, minute):
        b = self.bins.get(minute)
        if b is None:
            b = self.bins[minute] = dict((k, [0.0, 0, 0]) for k in SENSOR_KEYS)
        return b

    def _settle(self, key, ms):
        """Credit the time since the last change to the minutes it covered."""

        t0 = self.since[key]
        if self.state[key] and t0 is not None and ms > t0:
            t0 = max(t0, ms - (SENSOR_DAY_MIN + 60) * 60000)
            while t0 < ms:
                m = t0 // 60000
                t = min(ms, (m + 1) * 60000)
                self._bin(m)[key][0] += (t - t0) / 60000.0
                t0 = t
        self.since[key] = ms

    def add(self, code, value, smTime, epoch):
        ms = epoch * 1000 + smTime % 1000
        if self.lastMs is None or ms > self.lastMs:
            self.lastMs = ms
        if self.firstMs is None or ms < self.firstMs:
            self.firstMs = ms
        if self.gapFrom is not None:
            if ms - self.gapFrom > 60000:
                self.gaps.append([self.gapFrom, ms])
            self.gapFrom = None
        if code == 98:  # hourly level check: value = pin*10 + level
            pin, level = divmod(value, 10)
            if pin in self.levelPins:
                key, inLevel = self.levelPins[pin]
                self._settle(key, ms)
                self._setState(key, 1 if level == inLevel else 0, ms)
                self.levels.append((ms, key, self.state[key]))
                self.raw.append((ms, key, self.state[key]))  # so the trace starts at the right level
            return
        key = self.codes.get(code)
        if key is None:
            return
        if key != "Lick":
            self.lastPokeSm = smTime
        elif value == 1 and smTime == self.lastPokeSm:
            return  # camera-line pulse of a nosepoke edge, not a lick
        self._settle(key, ms)
        if value == 1:
            b = self._bin(ms // 60000)[key]
            b[1] += 1
            last = self.lastEdge[key]
            if last is not None and 0 <= smTime - last < SENSOR_FAST_MS:
                b[2] += 1
            self.lastEdge[key] = smTime
        self._setState(key, 1 if value == 1 else 0, ms, edge=True)
        self.raw.append((ms, key, self.state[key]))
        if self.lastEdgeMs is None or ms > self.lastEdgeMs:
            self.lastEdgeMs = ms

    def _setState(self, key, new, ms, edge=False):
        """Track when the current state began. A state first seen in an hourly
        check began at or before it (approx); an edge dates it exactly."""

        if self.changed[key] is None or new != self.state[key]:
            self.changed[key] = ms
            self.approx[key] = not edge
        self.state[key] = new

    def _prune(self):
        if self.lastMs is None:
            return
        oldest = self.lastMs // 60000 - SENSOR_DAY_MIN - 60
        for m in [m for m in self.bins if m < oldest]:
            del self.bins[m]
        while self.levels and self.levels[0][0] < oldest * 60000:
            self.levels.popleft()
        self.gaps = [g for g in self.gaps if g[1] >= oldest * 60000]
        anchor = self.lastEdgeMs if self.lastEdgeMs is not None else self.lastMs
        while self.raw and self.raw[0][0] < anchor - SENSOR_RAW_MS:
            ms, key, s = self.raw.popleft()
            self.rawInit[key] = s

    def _line(self, line):
        p = line.split(b",")
        if len(p) < 6:
            return
        try:
            code, value, smTime, epoch = int(p[0]), int(p[1]), int(p[4]), int(p[5])
        except ValueError:
            return
        self.add(code, value, smTime, epoch)

    def _save(self, path, current, pos, part):
        """Write the state and read position atomically (temp file + rename)."""

        with self.lock:
            d = dict((name, getattr(self, name)) for name in self.SAVED)
            d.update(
                version=1,
                file=os.path.basename(current),
                pos=pos,
                part=part.decode("latin-1"),
                bins=[[m, [b[k] for k in SENSOR_KEYS]] for m, b in self.bins.items()],
                levels=list(self.levels),
                raw=list(self.raw),
            )
            text = json.dumps(d, separators=(",", ":"))
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)

    def _load(self, path):
        """Restore a saved state; returns (file name, pos, partial line) or None."""

        try:
            with open(path) as fh:
                d = json.load(fh)
        except (IOError, OSError, ValueError):
            return None
        if d.get("version") != 1 or d.get("lastMs") is None:
            return None
        if localNowMs() - d["lastMs"] > SENSOR_CACHE_MAX_AGE_MS:
            return None  # too old to help: rebuild from the .dat files
        for name in self.SAVED:
            setattr(self, name, d[name])
        self.lastEdge = dict(d["lastEdge"])
        self.bins = dict((m, dict(zip(SENSOR_KEYS, vals))) for m, vals in d["bins"])
        self.levels = collections.deque(tuple(x) for x in d["levels"])
        self.raw = collections.deque(tuple(x) for x in d["raw"])
        return d["file"], d["pos"], d["part"].encode("latin-1")

    def follow(self, dataDir, subject):
        """Resume from the cache if there is one; otherwise read the subject's
        .dat files from the day before onward. Then keep following the newest;
        MainCode starts a new one every day."""

        pattern = os.path.join(dataDir, subject + "-*.dat")
        current, pos, part = None, 0, b""
        cachePath = None
        try:
            if not os.path.isdir(SENSOR_CACHE_DIR):
                os.makedirs(SENSOR_CACHE_DIR)
            cachePath = os.path.join(SENSOR_CACHE_DIR, re.sub(r"[^\w.-]", "_", subject) + ".json")
        except OSError as e:
            logging.debug("Sensor cache off: %r" % e)
        saved = self._load(cachePath) if cachePath else None
        resumeAfter = None
        if saved:
            name, savedPos, savedPart = saved
            path = os.path.join(dataDir, name)
            if os.path.exists(path) and os.path.getsize(path) >= savedPos:
                current, pos, part = path, savedPos, savedPart
            else:  # moved to the NAS while the camera was down: go on with newer files
                resumeAfter = path
                self.gapFrom = self.lastMs
        lastSave, savedAt = time.time(), (current, pos)
        while True:
            files = sorted(glob.glob(pattern))
            if current is None:
                if resumeAfter is not None:
                    files = [f for f in files if f > resumeAfter]
                if not files:
                    self.ready = True
                    time.sleep(5)
                    continue
                if resumeAfter is not None:
                    current = files[0]
                else:
                    current = files[-2] if len(files) > 1 else files[-1]
            try:
                with open(current, "rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read(4 * 1024 * 1024)
                    pos = fh.tell()
            except (IOError, OSError):  # moved to the NAS by the transfer
                chunk = b""
            if chunk:
                lines = (part + chunk).split(b"\n")
                part = lines.pop()
                with self.lock:
                    for line in lines:
                        self._line(line)
                    self._prune()
                continue
            newer = [f for f in files if f > current]
            if newer:
                current, pos, part = newer[0], 0, b""
                continue
            self.ready = True
            if cachePath and time.time() - lastSave >= SENSOR_CACHE_EVERY_S and (current, pos) != savedAt:
                lastSave, savedAt = time.time(), (current, pos)  # nothing new read: no write
                try:
                    self._save(cachePath, current, pos, part)
                except (IOError, OSError) as e:
                    logging.debug("Sensor cache not saved: %r" % e)
            time.sleep(2)

    def snapshot(self):
        nowMs = localNowMs()
        end = nowMs // 60000 + 1
        start = end - SENSOR_DAY_MIN
        with self.lock:
            dataEnd = self.lastMs
            rows = {}
            for k in SENSOR_KEYS:
                occ, n, fast = [], [], []
                openFrom = self.since[k] if self.state[k] else None
                for m in range(start, end):
                    b = self.bins.get(m)
                    o, e, f = b[k] if b else (0.0, 0, 0)
                    if openFrom is not None and dataEnd is not None:  # still in: up to the last data
                        lo, hi = max(openFrom, m * 60000), min(dataEnd, (m + 1) * 60000)
                        if hi > lo:
                            o += (hi - lo) / 60000.0
                    occ.append(round(min(o, 1.0), 2))
                    n.append(e)
                    fast.append(f)
                rows[k] = dict(occ=occ, n=n, fast=fast)
            levels = [
                [round(ms / 60000.0 - start, 1), k, s] for ms, k, s in self.levels if ms >= start * 60000
            ]
            cur = {}
            for k in SENSOR_KEYS:
                ch = self.changed[k]
                cur[k] = dict(
                    on=self.state[k],
                    forMin=None if ch is None or dataEnd is None else int((dataEnd - ch) // 60000),
                    approx=self.approx[k],
                )
            raw, w1 = None, self.lastEdgeMs
            if w1 is not None:
                w0 = w1 - SENSOR_RAW_MS
                ev, init, cut = {}, dict(self.rawInit), False
                for k in SENSOR_KEYS:
                    lst = [(ms, s) for ms, kk, s in self.raw if kk == k and w0 <= ms <= w1]
                    if len(lst) > SENSOR_RAW_CAP:
                        init[k], lst, cut = lst[-SENSOR_RAW_CAP - 1][1], lst[-SENSOR_RAW_CAP:], True
                    ev[k] = [[ms - w0, s] for ms, s in lst]
                raw = dict(start=w0, init=init, ev=ev, capped=cut, ageMin=int((nowMs - w1) // 60000))
            return dict(
                ready=self.ready,
                start=start * 60,
                endMin=None if dataEnd is None else min(SENSOR_DAY_MIN, dataEnd // 60000 - start + 1),
                beginMin=0 if self.firstMs is None else max(0, self.firstMs // 60000 - start),
                gaps=[
                    [max(0, a // 60000 - start), min(SENSOR_DAY_MIN, b // 60000 - start + 1)]
                    for a, b in self.gaps
                    if b // 60000 >= start
                ],
                lagMin=None if dataEnd is None else int((nowMs - dataEnd) // 60000),
                rows=rows,
                levels=levels,
                cur=cur,
                raw=raw,
            )


sensorTrace = SensorTrace()


def readEventPins(fileName="SetHardwareConfig.h"):
    """Teensy pins of the nosepoke inputs and the camera trigger line, from the
    firmware's hardware config: ({nosepoke pin: label}, trigger pin)."""

    labels = {"Nosepoke1DI": "NOSEPOKE L", "Nosepoke2DI": "NOSEPOKE R"}
    with open(fileName) as fh:
        text = re.sub(r"//.*", "", fh.read())
    pins = dict(
        (name, int(pin))
        for name, pin in re.findall(r'CreateHDW_D[IO]\((\w+),\s*"[^"]*",\s*(\d+)', text)
    )
    return dict((pins[n], label) for n, label in labels.items() if n in pins), pins.get("GPIOOutDO")


def eventFeedLoop():
    """Feed each .dat line MainCode.py forwards to the stream page's panel. A
    camera-line high written in the same ms as a nosepoke edge belongs to that
    nosepoke; any other one is a lick."""

    try:
        pokeLabels, linePin = readEventPins()
    except (OSError, re.error) as e:
        logging.debug("Event panel off, no hardware config: %s" % e)
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(EVENT_UDP_ADDR)
    except OSError:
        logging.debug("Event panel off, port %d busy" % EVENT_UDP_ADDR[1])
        return
    lastPoke = None
    while True:
        try:
            words = sock.recv(256).decode().split(",")
            event, value, sm, smTime = int(words[0]), int(words[1]), int(words[2]), int(words[4])
        except (ValueError, IndexError, UnicodeDecodeError):
            continue
        label = None
        if event in pokeLabels and value == 1:
            label, lastPoke = pokeLabels[event], smTime
        elif event == linePin and value == 1 and smTime != lastPoke:
            label = "LICK"
        try:
            eventFeed.add(event, value, sm, smTime, label)
        except Exception as e:  # the panel must never stop the camera
            logging.debug("Event panel: %r" % e)


def getUserConfig(fileName, splitterChar):
    """Function to read the user configuration file as a dictionary."""

    userConfig = {}
    with open(fileName) as configFile:
        for eachLine in configFile:
            if "=" in eachLine:
                settingName, settingValue = eachLine.split(splitterChar)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                userConfig[settingName] = settingValue
    return userConfig


def set_camera_running(state):
    """Track camera running status."""

    with state_lock:
        controller_status["camera_running"] = bool(state)


def is_camera_running():
    """Return camera running status."""

    with state_lock:
        return controller_status.get("camera_running", False)


def load_schedule(camera_config, alarm_file):
    """Return record start/stop lists and seconds since midnight."""

    rec_opt = str(camera_config.get("Record_Schedule", "")).lower()
    record_start = []
    record_stop = []

    if rec_opt == "u":
        try:
            record_start = list(eval(camera_config.get("Record_Start", "[]")))
            record_stop = list(eval(camera_config.get("Record_Stop", "[]")))
        except Exception:
            logging.debug("Failed to parse user schedule; defaulting to empty.")
            record_start, record_stop = [], []
    elif rec_opt == "t":
        try:
            F = open(alarm_file, "r").readlines()
        except IOError:
            logging.debug("* Alarm schedule file not found for schedule load.")
            return record_start, record_stop, [], []

        st, sp = (list(), list())
        for i, L in enumerate(F):
            if (
                ("Training" in L)
                and ("SetDailyAlarms" in L)
                and (L.strip()[0:2] != "//")
                and (L.strip()[0:1] != "/")
            ):
                st.append(L)
                sp.append(F[i + 1])

        for i in range(len(st)):
            t1 = tuple(
                map(int, (st[i][st[i].find("(") + 1 : st[i].find(")")]).split(",")[:2])
            )
            t2 = tuple(
                map(int, (sp[i][sp[i].find("(") + 1 : sp[i].find(")")]).split(",")[:2])
            )
            record_start.append(t1)
            record_stop.append(t2)

    start_sec = [i[0] * 3600 + i[1] * 60 for i in record_start]
    stop_sec = [i[0] * 3600 + i[1] * 60 for i in record_stop]
    return record_start, record_stop, start_sec, stop_sec


def is_time_in_schedule(now, start_sec, stop_sec, lead=0, lag=0):
    """Return True if now (seconds) is within schedule ± margins."""

    if not start_sec or not stop_sec:
        return False

    now = now % 86400
    for start, stop in zip(start_sec, stop_sec):
        if stop == start:
            continue
        diff = stop - start
        sig = int((1 - diff / abs(diff)) / 2)
        adj_now = now
        if sig and adj_now < start and adj_now < stop:
            adj_now = adj_now + 24 * 3600
        start_adj = start - lead
        stop_adj = stop + lag + 24 * 3600 * sig
        if adj_now >= start_adj and adj_now < stop_adj:
            return True
    return False


def in_record_window(now=None):
    """Return True if local time is inside a recording window (clips are saved)."""

    if now is None:
        now = time.time() - time.timezone  # schedule is in local time
    return is_time_in_schedule(
        now, schedule_cache["start_sec"], schedule_cache["stop_sec"]
    )


def resolve_subject_output_dir(user_config):
    """Return Output_Dir/<Subject_Name> with fallbacks."""

    base_raw = str(user_config.get("Output_Dir", "")).strip()
    if not base_raw or base_raw.lower() == "default":
        base_dir = os.path.abspath(".")
    else:
        base_dir = os.path.expandvars(os.path.expanduser(base_raw))

    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        base_dir = os.path.abspath(".")
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            pass

    subject = user_config.get("Subject_Name", "Subject")
    if not isinstance(subject, str):
        subject = str(subject)
    subject = subject.strip() or "Subject"
    safe_subject = subject.replace(os.sep, "_").replace("/", "_")

    target = os.path.join(base_dir, safe_subject)
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        return base_dir
    return target


def removeFDir(path, backup=False, empty=False):
    """Remove files/directories with additional option
    empty: True (remove only when dir is empty)
    backup: True (backup file/dir with epoch time added to its name) ##
    """

    if os.path.exists(path):
        if os.path.isfile(path):
            os.remove(path)
        if os.path.isdir(path):
            if empty:
                if not os.listdir(path):
                    os.rmdir(path)
            else:
                os.rmdir(path)


class safeExit:
    """
    Class to exit the program safely.
    """

    exitStatus = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exitNow)
        signal.signal(signal.SIGTERM, self.exitNow)

    def exitNow(self, signum, frame):
        """
        Function to exit the program.
        """

        self.exitStatus = True


def getIP():
    """Return RPi IP address."""

    return netifaces.ifaddresses("eth0")[netifaces.AF_INET][0]["addr"]


def generateHTML(resolution, ip):
    """Generate an HTML page."""

    storage_path = "/"
    storage_display = "N/A"
    try:
        cam_cfg = globals().get("cameraConfig")
        usr_cfg = globals().get("userConfig")
        candidate = None
        if isinstance(cam_cfg, dict):
            candidate = cam_cfg.get("RPi_Video_Dir") or candidate
        if not candidate and isinstance(usr_cfg, dict):
            candidate = usr_cfg.get("Storage_Check_Path")
        if candidate:
            storage_path = candidate
    except Exception:
        pass
    storage_path = storage_path or "/"
    if not os.path.exists(storage_path):
        storage_path = "/"
    try:
        usage_pct = StorageMonitor.get_usage_percent(storage_path)
        storage_display = "{:.1f}%".format(usage_pct)
    except Exception:
        storage_display = "N/A"

    camera_state = "ON" if is_camera_running() else "OFF"
    schedule_state = "YES" if in_record_window() else "NO"

    PAGE = """\
    <html>
    <head>
    <title>OpCon PiCamera %s</title>
    </head>
    <body>
    <table width="100%%" align="left">
      <tr>
        <th>RPi IP Address</th>
        <th>Image Resolution</th>
        <th>User Name</th>
        <th>Box Name</th>
        <th>Subject Name</th>
        <th>Storage Used</th>
      </tr>
      <tr>
        <td align="center"><font color="000FF">%s</font></td>
        <td align="center"><font color="000FF">%sx%s</font></td>
        <td align="center"><font color="000FF">%s</font></td>
        <td align="center"><font color="000FF">%s</font></td>
        <td align="center"><font color="000FF">%s</font></td>
                <td align="center"><font color="000FF">%s</font></td>
      </tr>
    </table>
    <p>Camera Status: <b>%s</b> | Saving clips (recording window): <b>%s</b></p>
    <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap">
    <img src="stream.mjpg" width="%d" height="%d" />
    %s
    </div>
    %s
    </body>
    </html>
    """ % (
        ip,
        ip,
        resolution[0],
        resolution[1],
        userConfig["Name"],
        userConfig["Box_Name"],
        userConfig["Subject_Name"],
        storage_display,
        camera_state,
        schedule_state,
        resolution[1],
        resolution[0],
        EVENT_PANEL,
        SENSOR_PANEL,
    )
    return PAGE


# Live events beside the stream; polls events.json (EventFeed) a few times a second
EVENT_PANEL = """
<section style="width:372px;box-sizing:border-box;border:1px solid #d0d4da;border-radius:6px;
  padding:14px 16px;font:13px system-ui,-apple-system,'Segoe UI',sans-serif;color:#1b1b1b">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <b style="font-size:15px">Live events</b>
    <span id="ev-session" style="font-size:12px;color:#4a5361"></span>
  </div>
  <div style="display:flex;align-items:center;gap:12px;padding:10px 12px;margin:12px 0;
    background:#fff4e5;border-radius:4px;min-height:30px">
    <span id="ev-latest" style="font-size:22px;font-weight:700;color:#8a4b00"></span>
    <span id="ev-latest-note" style="color:#4a5361"></span>
  </div>
  <div id="ev-counts" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;text-align:center"></div>
  <div id="ev-list" style="margin-top:12px;font:12.5px ui-monospace,Consolas,monospace"></div>
</section>
<script>
(function () {
  var colors = {poke: '#0b6b3a', lick: '#8a4b00', reward: '#1f5fbf', none: '#4a5361', trial: '#1b1b1b'};
  var seen = -1;
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]; }); }
  function tile(n, label) {
    return '<div style="padding:6px 0;background:#f3f5f8;border-radius:4px"><div style="font-size:18px;font-weight:600">' +
      n + '</div><div style="font-size:11px;color:#4a5361">' + label + '</div></div>';
  }
  function show(d) {
    var c = d.counts;
    document.getElementById('ev-session').textContent = d.session ? d.session.name + ' · since ' + d.session.since : 'no trials yet';
    document.getElementById('ev-counts').innerHTML = tile(c.trials, 'trials') + tile(c.rewarded, 'rewarded') +
      tile(c.pokesL + ' / ' + c.pokesR, 'pokes L / R') + tile(c.pulses, 'water pulses');
    var e = d.events[0];
    document.getElementById('ev-latest').textContent = e ? e.label : '';
    document.getElementById('ev-latest').style.color = e ? colors[e.kind] : '';
    document.getElementById('ev-latest-note').textContent = e ? e.time + (e.note ? ' · ' + e.note : '') : 'waiting for events';
    document.getElementById('ev-list').innerHTML = d.events.map(function (e) {
      return '<div style="display:flex;gap:12px;padding:4px 0;border-bottom:1px solid #eceef1">' +
        '<span style="color:#4a5361">' + esc(e.time) + '</span><span style="font-weight:600;color:' + colors[e.kind] + '">' +
        esc(e.label) + '</span><span style="color:#4a5361">' + esc(e.note) + '</span></div>';
    }).join('');
  }
  function poll() {
    fetch('events.json', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (d) {
      if (d.seq !== seen) { seen = d.seq; show(d); }
    }).catch(function () {}).then(function () { setTimeout(poll, 250); });
  }
  poll();
})();
</script>
"""


# Sensor health below the stream and events panel; polls sensors.json (SensorTrace)
SENSOR_PANEL = """
<section style="width:100%;max-width:1032px;box-sizing:border-box;margin-top:20px;border:1px solid #d0d4da;
  border-radius:6px;padding:14px 16px;font:13px system-ui,-apple-system,'Segoe UI',sans-serif;color:#1b1b1b">
  <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 14px">
    <b style="font-size:15px">Sensors</b>
    <span id="sn-chips" style="display:flex;flex-wrap:wrap;gap:6px"></span>
  </div>
  <div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#4a5361;margin:12px 0 4px">
    Last 24 h <span id="sn-day-when" style="text-transform:none;letter-spacing:0"></span></div>
  <canvas id="sn-day" style="width:100%;display:block"></canvas>
  <div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#4a5361;margin:12px 0 4px">
    10 min before the last event <span id="sn-raw-when" style="text-transform:none;letter-spacing:0"></span></div>
  <canvas id="sn-raw" style="width:100%;display:block"></canvas>
  <div style="display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:10px;font-size:11.5px;color:#4a5361">
    <span><i style="display:inline-block;width:12px;height:9px;background:#1f5fbf;border-radius:2px"></i> events per minute</span>
    <span><i style="display:inline-block;width:12px;height:9px;background:#b42318;border-radius:2px"></i> reads in for the whole minute</span>
    <span><i style="display:inline-block;width:12px;height:9px;background:#c77700;border-radius:2px"></i> chatter (most events &lt;20 ms apart)</span>
    <span><i style="display:inline-block;width:12px;height:9px;background:repeating-linear-gradient(45deg,#c9ced6 0 3px,transparent 3px 6px)"></i> no data: not received from the Teensy yet, or older than the oldest file on the box</span>
    <span>&#9679; / &#9675; hourly level check: in / out</span>
  </div>
</section>
<script>
(function () {
  var KEYS = ['L', 'R', 'Lick'], LABEL = {L: 'L poke', R: 'R poke', Lick: 'Lick'};
  var C = {trace: '#1f5fbf', ok: '#0b6b3a', okbg: '#e6f4ec', warn: '#8a4b00', warnfill: '#c77700', warnbg: '#fff4e5',
           bad: '#b42318', badbg: '#fde8e6', muted: '#4a5361', line: '#eceef1', hatch: '#c9ced6', fg: '#1b1b1b'};
  var LW = 58, RH = 24, GAP = 8, AX = 18, last = null;
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function hm(sec) { var d = new Date(sec * 1000); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); }
  function hms(sec) { var d = new Date(sec * 1000); return hm(sec) + ':' + pad(d.getUTCSeconds()); }
  function sum(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s; }
  function dur(m) { return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min'; }
  function ago(m) { return m < 1 ? 'just now' : dur(m) + ' ago'; }
  function flags(d) {
    // Stuck = in right now for 60 min or more; earlier stuck stretches stay visible in the 24 h strip only.
    var f = {};
    KEYS.forEach(function (k) {
      var r = d.rows[k], c = d.cur[k], n = sum(r.n), fast = sum(r.fast);
      var other = k === 'L' ? sum(d.rows.R.n) : k === 'R' ? sum(d.rows.L.n) : 0;
      var inFor = c.on && c.forMin !== null ? (c.approx ? '\\u2265 ' : '') + dur(c.forMin) : '';
      var now = c.on ? (k === 'Lick' ? 'contact ' : 'IN ') + inFor : (k === 'Lick' ? 'no contact' : 'out');
      if (c.on && c.forMin !== null && c.forMin >= 60) f[k] = {cls: 'bad', text: LABEL[k] + ' stuck IN \\u00b7 ' + inFor};
      else if (n > 1000 && fast / n > 0.3) f[k] = {cls: 'warn', text: LABEL[k] + ' chatter \\u00b7 ' + Math.round(100 * fast / n) + '% of events <20 ms apart'};
      else if (k !== 'Lick' && n === 0 && other >= 100) f[k] = {cls: 'warn', text: LABEL[k] + ' silent \\u00b7 ' + now};
      else f[k] = {cls: 'ok', text: LABEL[k] + ' \\u00b7 ' + now};
    });
    return f;
  }
  function setup(cv, h) {
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + 'px';
    var ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); return [ctx, w];
  }
  function labels(ctx, fl) {
    ctx.font = '600 11px ui-monospace,Consolas,monospace'; ctx.textBaseline = 'middle';
    KEYS.forEach(function (k, i) { ctx.fillStyle = C[fl[k].cls]; ctx.fillText(LABEL[k], 0, i * (RH + GAP) + RH / 2); });
  }
  function drawDay(d, fl) {
    var H = KEYS.length * (RH + GAP) + AX, s = setup(document.getElementById('sn-day'), H), ctx = s[0], w = s[1];
    var x = function (m) { return LW + (w - LW - 4) * m / 1440; }, cw = Math.max(1, (w - LW - 4) / 1440);
    var end = d.endMin === null ? 0 : d.endMin;
    labels(ctx, fl);
    KEYS.forEach(function (k, i) {
      var y0 = i * (RH + GAP), r = d.rows[k], scale = k === 'Lick' ? 300 : 30;
      ctx.fillStyle = C.line; ctx.fillRect(LW, y0 + RH, w - LW - 4, 1);
      for (var m = 0; m < end; m++) {
        var n = r.n[m], f = r.fast[m];
        if (r.occ[m] >= 0.95) { ctx.fillStyle = C.bad; ctx.fillRect(x(m), y0, cw + 0.5, RH); continue; }
        if (!n) continue;
        var h = Math.max(2, RH * Math.min(1, Math.sqrt(n / scale)));
        ctx.fillStyle = (n >= 20 && f / n > 0.5) ? C.warnfill : C.trace;
        ctx.fillRect(x(m), y0 + RH - h, cw + 0.5, h);
      }
      var hatch = function (a, b) {  // minutes with no data
        if (b <= a) return;
        ctx.save(); ctx.beginPath(); ctx.rect(x(a), y0, x(b) - x(a), RH); ctx.clip();
        ctx.strokeStyle = C.hatch; ctx.lineWidth = 1.5;
        for (var sx = x(a) - RH; sx < x(b); sx += 6) { ctx.beginPath(); ctx.moveTo(sx, y0 + RH); ctx.lineTo(sx + RH, y0); ctx.stroke(); }
        ctx.restore();
      };
      hatch(0, Math.min(d.beginMin || 0, end));
      hatch(end, 1440);
      (d.gaps || []).forEach(function (g) { hatch(g[0], g[1]); });
      d.levels.forEach(function (l) {
        if (l[1] !== k) return;
        ctx.beginPath(); ctx.arc(x(l[0]), y0 + RH + 4, 2.4, 0, 7);
        if (l[2]) { ctx.fillStyle = C.fg; ctx.fill(); } else { ctx.strokeStyle = C.muted; ctx.lineWidth = 1; ctx.stroke(); }
      });
    });
    ctx.fillStyle = C.muted; ctx.font = '10.5px ui-monospace,Consolas,monospace';
    var y = KEYS.length * (RH + GAP) + AX / 2 + 2, first = (180 - (d.start / 60) % 180) % 180;
    for (var m = first; m <= 1440; m += 180) {
      ctx.textAlign = m < 20 ? 'left' : m > 1420 ? 'right' : 'center';
      ctx.fillText(hm(d.start + m * 60), x(m), y);
    }
    ctx.textAlign = 'left';
    document.getElementById('sn-day-when').textContent = '\\u00b7 ' + hm(d.start) + ' \\u2192 ' + hm(d.start + 1440 * 60);
  }
  function drawRaw(d, fl) {
    var H = KEYS.length * (RH + GAP) + AX, s = setup(document.getElementById('sn-raw'), H), ctx = s[0], w = s[1];
    var x = function (ms) { return LW + (w - LW - 4) * ms / 600000; };
    labels(ctx, fl);
    if (!d.raw) { document.getElementById('sn-raw-when').textContent = '\\u00b7 no sensor events since ' + hm(d.start + (d.beginMin || 0) * 60); return; }
    var stale = d.raw.ageMin > 60;  // greyed out: history, not what the sensors do now
    KEYS.forEach(function (k, i) {
      var y0 = i * (RH + GAP), hi = y0 + 3, lo = y0 + RH - 1, ev = d.raw.ev[k], st = d.raw.init[k];
      ctx.strokeStyle = stale ? C.hatch : fl[k].cls === 'ok' ? C.trace : fl[k].cls === 'warn' ? C.warnfill : C.bad; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x(0), st ? hi : lo);
      for (var j = 0; j < ev.length; j++) { ctx.lineTo(x(ev[j][0]), st ? hi : lo); st = ev[j][1]; ctx.lineTo(x(ev[j][0]), st ? hi : lo); }
      ctx.lineTo(x(600000), st ? hi : lo); ctx.stroke();
    });
    ctx.fillStyle = C.muted; ctx.font = '10.5px ui-monospace,Consolas,monospace';
    var y = KEYS.length * (RH + GAP) + AX / 2 + 2;
    [0, 2, 4, 6, 8, 10].forEach(function (m) {
      ctx.textAlign = m === 0 ? 'left' : m === 10 ? 'right' : 'center';
      ctx.fillText(m === 10 ? 'last event' : '-' + (10 - m) + ' min', x(m * 60000), y);
    });
    ctx.textAlign = 'left';
    document.getElementById('sn-raw-when').textContent = '\\u00b7 ends ' + hms((d.raw.start + 600000) / 1000) +
      ' (' + ago(d.raw.ageMin) + ')' + (stale ? ' \\u00b7 old, greyed out' : '') +
      (d.raw.capped ? ' \\u00b7 last ' + 3000 + ' edges per row shown' : '');
  }
  function chip(cls, text) {
    return '<span style="font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap;color:' +
      C[cls] + ';background:' + C[cls + 'bg'] + '">' + text + '</span>';
  }
  function show(d) {
    var el = document.getElementById('sn-chips');
    if (!d.ready && d.endMin === null) { el.innerHTML = chip('warn', 'reading data\\u2026'); return; }
    var fl = flags(d), html = KEYS.map(function (k) { return chip(fl[k].cls, fl[k].text); }).join('');
    if (d.lagMin !== null && d.lagMin > 120) html += chip('warn', 'data ' + Math.floor(d.lagMin / 60) + ' h ' + (d.lagMin % 60) + ' min behind');
    if (!d.ready) html += chip('warn', 'still reading data\\u2026');
    el.innerHTML = html;
    drawDay(d, fl); drawRaw(d, fl);
  }
  function poll() {
    fetch('sensors.json', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (d) {
      last = d; show(d);
    }).catch(function () {}).then(function () { setTimeout(poll, 5000); });
  }
  window.addEventListener('resize', function () { if (last) show(last); });
  poll();
})();
</script>
"""



class StreamingOutput(io.BufferedIOBase):
    """Streaming web output object compatible with picamera2."""

    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = threading.Condition()

    def write(self, buf):
        if buf.startswith(b"\xff\xd8"):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class StreamingHandler(server.BaseHTTPRequestHandler):
    """Streaming handler object."""

    def get_frame(self):
        if piCamWebOutput is None or not is_camera_running():
            raise RuntimeError("Camera not streaming")
        with piCamWebOutput.condition:
            piCamWebOutput.condition.wait()
            frame = piCamWebOutput.frame
        return frame

    def get_page(self):
        return generateHTML([360, 640], getIP())

    PATH_SUFFIXES = (
        "/status",
        "/events.json",
        "/sensors.json",
        "/stream.mjpg",
        "/index.html",
    )

    def _build_index_redirect(self, base):
        if base and not base.endswith("/"):
            return base + "/index.html"
        return "/index.html"

    def _split_base_suffix(self):
        parsed_url = urlparse(self.path)
        normalized_path = parsed_url.path or "/"
        if normalized_path != "/" and normalized_path.endswith("/"):
            normalized_path = normalized_path.rstrip("/")
        base = ""
        prefix = "/camera"
        core_path = normalized_path
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            base = prefix
            core_path = normalized_path[len(prefix) :]
            if not core_path:
                core_path = "/"
        if not core_path:
            core_path = "/"
        if core_path != "/" and not core_path.startswith("/"):
            core_path = "/" + core_path

        if core_path == "/":
            return base, "/"

        for suffix in self.PATH_SUFFIXES:
            if core_path == suffix:
                return base, suffix
        return normalized_path, None

    def do_GET(self):
        base, suffix = self._split_base_suffix()
        if suffix is None:
            # Quietly handle favicon to avoid noisy 404s in the log
            if self.path.endswith("/favicon.ico"):
                self.send_response(204)
                self.end_headers()
                return
            # If we're under /camera but hit an unknown child, send the user back home
            if base == "/camera":
                self.send_response(302)
                self.send_header("Location", self._build_index_redirect(base))
                self.end_headers()
                return
            self.send_error(404)
            self.end_headers()
            return

        if suffix == "/":
            self.send_response(301)
            self.send_header("Location", self._build_index_redirect(base))
            self.end_headers()
            return

        if suffix == "/index.html":
            PAGE = self.get_page()
            content = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
            return

        if suffix == "/status":
            status = {
                "camera_running": is_camera_running(),
                "record_window": in_record_window(),
            }
            payload = str(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)
            return

        if suffix == "/events.json":
            payload = json.dumps(eventFeed.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)
            return

        if suffix == "/sensors.json":
            payload = json.dumps(sensorTrace.snapshot(), separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)
            return

        if suffix == "/stream.mjpg":
            if piCamWebOutput is None or not is_camera_running():
                self.send_error(503, "Camera not streaming")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Age", 0)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=FRAME"
            )
            self.end_headers()
            try:
                while True:
                    frame = self.get_frame()
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception as e:
                logging.warning(
                    "Removed streaming client %s: %s", self.client_address, str(e)
                )
            return

        self.send_error(404)
        self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    """Streaming server object"""

    allow_reuse_address = True
    daemon_threads = True


class PiCamBuffer(Output):
    """Ring buffer of encoded H.264 frames, cut into clips by time.

    Plays the role of picamera's PiCameraCircularIO on the Pi3B: keeps the last
    'seconds' of frames with wall-clock timestamps (us, the clock of the GPIO
    edge times), and copy_to saves startTime..stopTime from the last key frame
    at or before startTime.
    """

    def __init__(self, encoder, seconds):
        super().__init__()
        self.encoder = encoder
        self.seconds = seconds
        self.frames = collections.deque()  # (wall_us, keyframe, bytes)
        self.lock = threading.Lock()

    def outputframe(self, frame, keyframe=True, timestamp=None, packet=None, audio=False):
        if audio or timestamp is None or self.encoder.firsttimestamp is None:
            return
        # timestamp is the sensor time (us, boot clock = CLOCK_MONOTONIC on a Pi that
        # never suspends) minus the first frame's
        offset_us = (time.time() - time.clock_gettime(time.CLOCK_MONOTONIC)) * 1e6
        wall_us = timestamp + self.encoder.firsttimestamp + offset_us
        with self.lock:
            self.frames.append((wall_us, keyframe, bytes(frame)))
            while wall_us - self.frames[0][0] > self.seconds * 1e6:
                self.frames.popleft()

    def copy_to(self, output, tfilename, startTime, stopTime=None):
        """Save frames from startTime to stopTime (us) and their times to tfilename."""

        with self.lock:
            frames = list(self.frames)
        first = None
        for i, (t, key, _) in enumerate(frames):
            if t > startTime:
                break
            if key:
                first = i
        if first is None:
            logging.debug("Clip start no longer in the buffer; not saved.")
            return
        clip = [f for f in frames[first:] if stopTime is None or f[0] <= stopTime]

        with open(output, "wb") as out_file:
            for _, _, b in clip:
                out_file.write(b)
        tstart = clip[0][0]
        with open(tfilename, "w") as tfile:
            tfile.write("%d\n" % tstart)
            tfile.write("\n".join(str(int(t - tstart)) for t, _, _ in clip))


class PtsOutput(object):
    """Write H264 data to a video file and record frame timestamps.

    Compatible with picamera2 (no longer relies on picamera frame attributes).
    Timestamps are written using wall-clock time.
    """

    def __init__(self, video_filename, pts_filename):
        self.video_output = io.open(video_filename, "wb")
        self.pts_output = io.open(pts_filename, "w")
        self.start_time = None

    def write(self, buf):
        self.video_output.write(buf)
        now_us = int(time.time() * 1e6)
        if self.start_time is None:
            self.start_time = now_us
            self.pts_output.write("%d\n" % self.start_time)
        self.pts_output.write("%d\n" % (now_us - self.start_time))

    def flush(self):
        self.video_output.flush()
        self.pts_output.flush()

    def close(self):
        self.video_output.close()
        self.pts_output.close()


class PiCameraObject(object):
    """PiCamera class definition (picamera2 / Pi 5 compatible).
    Attributes:
        camType      : type of the PiCamera object [Master | Slave]
        resolution   : resolution of video [default is 640*360]
        framerate    : frame per second [default is 60 frames per second]
        rotation     : camera rotation angle [default is 0 degree]
        bitrate      : camera bit rate [default is 3 Mbps]
        camPin       : GPIO pin number on RPi to receive events from Teensy
        splitter_port: (unused with picamera2, kept for API compat)
        format       : Video file format (h264, mjpeg)
    """

    def __init__(
        self,
        camType,
        resolution=(640, 360),
        framerate=90,
        rotation=0,
        bitrate=2000000,
        camPin=26,
        splitter_port=1,
        format="h264",
    ):
        """Returns a PiCamera object whose name is *name*."""

        self.camType = camType
        self.resolution = resolution
        self.framerate = framerate
        self.rotation = rotation
        self.bitrate = bitrate
        self.camPin = camPin
        self.splitter_port = splitter_port
        self.format = format
        self.gainTime = 0
        self.gainThreadRunning = False
        self.stopRequested = False
        self._recording = False
        self._streaming = False
        self.bufferOutput = None
        self._encoder = None
        self._stream_encoder = None
        signal.signal(signal.SIGHUP, self.signalReceived)

        self.recordStart = None
        self.recordStop = None

        self.camera = Picamera2()
        self.configureSensor()

        self.setupGPIO()

        self.GPIO_Old = None

    def configureSensor(self):
        """Configure picamera2 sensor and create video configuration."""

        # Build transform for rotation
        from libcamera import Transform

        transform = Transform()
        if self.rotation == 180:
            transform = Transform(hflip=True, vflip=True)
        elif self.rotation == 90:
            transform = Transform(hflip=True, transpose=True)
        elif self.rotation == 270:
            transform = Transform(vflip=True, transpose=True)

        self._video_config = self.camera.create_video_configuration(
            main={"size": self.resolution, "format": "YUV420"},
            lores={"size": (640, 360), "format": "YUV420"},
            transform=transform,
            controls={
                "FrameDurationLimits": (
                    int(1e6 // self.framerate),
                    int(1e6 // self.framerate),
                )
            },
        )
        self.camera.configure(self._video_config)

    def interruptGPIO(self, channel):
        """Activates when GPIO value is changed."""

        event = self._gpio_line.read_edge_events()
        if not event:
            return
        for ev in event:
            PinStatus = 1 if ev.event_type == ev.Type.RISING_EDGE else 0
            # Denoising
            if PinStatus != self.GPIO_Old:
                self.GPIO_Old = PinStatus
            else:
                continue
            # Stamp with the edge's own hardware timestamp rather than a
            # delayed time.time() call, to avoid scheduling jitter.
            wallSec = self._edgeTimestampToWall(ev.timestamp_ns)
            camTime = int(wallSec * 1e6)  # microseconds (wall clock)
            piTime = wallSec + self.getTimeDiffUTC()
            mono = ev.timestamp_ns / 1e9  # CLOCK_MONOTONIC, same clock as .pitime
            self.GPIOqueue.put((PinStatus, camTime, piTime, mono))

    def _gpio_event_loop(self):
        """Background thread that polls gpiod for edge events."""
        while not self.stopRequested:
            if self._gpio_line.wait_edge_events(
                timeout=datetime.timedelta(milliseconds=100)
            ):
                for ev in self._gpio_line.read_edge_events():
                    PinStatus = 1 if ev.event_type == ev.Type.RISING_EDGE else 0
                    if PinStatus != self.GPIO_Old:
                        self.GPIO_Old = PinStatus
                        # Stamp with the edge's own hardware timestamp
                        # rather than a delayed time.time() call, to avoid
                        # poll/scheduling jitter (up to the 100ms timeout).
                        wallSec = self._edgeTimestampToWall(ev.timestamp_ns)
                        camTime = int(wallSec * 1e6)
                        piTime = wallSec + self.getTimeDiffUTC()
                        mono = ev.timestamp_ns / 1e9  # CLOCK_MONOTONIC
                        self.GPIOqueue.put((PinStatus, camTime, piTime, mono))

    def setupGPIO(self):
        """Setup GPIO to communicate with Teensy board using gpiod (Pi 5 compatible)."""
        global _gpio_chip, _gpio_lines

        self.GPIOqueue = queue.Queue()
        _gpio_chip = gpiod.request_lines(
            "/dev/gpiochip4",
            consumer="picam-gpio",
            config={
                self.camPin: LineSettings(
                    direction=Direction.INPUT,
                    bias=Bias.PULL_DOWN,
                    edge_detection=Edge.BOTH,
                ),
            },
        )
        self._gpio_line = _gpio_chip
        _gpio_lines = _gpio_chip

        # Start background GPIO event polling thread
        self._gpio_thread = threading.Thread(
            name="GPIOEventLoop", target=self._gpio_event_loop, daemon=True
        )
        self._gpio_thread.start()

    def setBuffer(
        self,
        preEventSaveTime=2,
        initialWaitTime=10,
        inactivityTime=5,
        postEventSaveTime=2,
        circularBufferSize=60,
        maxClipTime=50,
    ):
        """Sets camera buffer parameters.

        Parameters:
            preEventSaveTime   : Video kept before the first event, in sec
            initialWaitTime    : Close the clip if the line stays high this long, in sec
            inactivityTime     : Close the clip after this long with no event, in sec
                                 (long enough to keep a poke and its licks in one clip)
            postEventSaveTime  : Video kept after the last event, in sec
            circularBufferSize : Total ring buffer size in sec
            maxClipTime        : Save a clip once it is this long, in sec, before its
                                 start leaves the ring buffer
        """

        self.vidBuffer = preEventSaveTime
        self.T1 = initialWaitTime
        self.T2 = inactivityTime
        self.postBuffer = postEventSaveTime
        self.bufferLen = circularBufferSize
        self.maxClip = maxClipTime

    def clipName(self, startTime):
        """'<subject>_<YYYY-MM-DD>_<HH-MM-SS>' for a clip starting at startTime
        (local-time epoch seconds, as from getTime)."""

        stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.gmtime(startTime))
        return "%s_%s" % (self.subject, stamp)

    def setStorage(self, dirPath=None, subject="Subject"):
        """Set storage path for video files.

        Parameters:
            dirPath : Directory path to save video files
            subject : Animal name, used in the clip file names
        """

        self.subject = subject

        self.root = os.path.realpath("")
        self.gainPath = os.path.join(self.root, "GainSettings")

        if dirPath is None:
            self.storagePath = os.path.join(self.root, "Video")
        else:
            self.storagePath = dirPath

        if not os.path.exists(self.storagePath):
            os.makedirs(self.storagePath)

    def setRecordSched(self, dic, file):
        """Set record schedule."""

        self.recOpt = dic["Record_Schedule"].lower()

        if self.recOpt == "u":
            self.recordStart = eval(dic["Record_Start"])
            self.recordStop = eval(dic["Record_Stop"])
        elif self.recOpt == "t":
            self.recordStart = list()
            self.recordStop = list()

            try:
                F = open(file, "r").readlines()
            except IOError:
                logging.debug("* EXCEPTION HAPPENED.")
                logging.debug("* Alarm schedule find not found.")
                return

            st, sp = (list(), list())
            for i, L in enumerate(F):
                if (
                    ("Training" in L)
                    and ("SetDailyAlarms" in L)
                    and (L.strip()[0:2] != "//")
                    and (L.strip()[0:1] != "/")
                ):
                    st.append(L)
                    sp.append(F[i + 1])

            for i in range(len(st)):
                t1 = tuple(
                    map(
                        int,
                        (st[i][st[i].find("(") + 1 : st[i].find(")")]).split(",")[:2],
                    )
                )
                t2 = tuple(
                    map(
                        int,
                        (sp[i][sp[i].find("(") + 1 : sp[i].find(")")]).split(",")[:2],
                    )
                )
                self.recordStart.append(t1)
                self.recordStop.append(t2)

        logging.debug("".join(["The record start times are: ", str(self.recordStart)]))
        logging.debug("".join(["The record stop  times are: ", str(self.recordStop)]))

    def getDSTInfo(self, fileName):
        """
        Function to read DST data as a dictionary.
        """

        dic = {}
        with open(fileName) as File:
            for L in File:
                L = L.strip()
                S = L.split(",")
                Year, Days = [S[0].strip(), [S[1].strip(), S[2].strip()]]
                dic[Year] = Days
        return dic

    def dstStatus(self, dt):
        """
        Function to check Daylight Saving status.
        """

        Y = str(dt.year)
        d1 = int(self.DSTInfo[Y][0])
        d2 = int(self.DSTInfo[Y][1])
        dst_start = datetime.datetime(dt.year, 3, d1, 2, 0)
        dst_start += datetime.timedelta(6 - dst_start.weekday())
        dst_end = datetime.datetime(dt.year, 11, d2, 2, 0)
        dst_end += datetime.timedelta(6 - dst_end.weekday())
        return dst_start <= dt < dst_end

    def getTimeDiffUTC(self):
        """Return local time difference with UTC considering daylight saving"""

        TimeDiffUTC = -time.timezone
        # if self.dstStatus(datetime.datetime.now()):
        #    TimeDiffUTC += 3600

        return TimeDiffUTC

    def getTime(self):
        """Return epoch time in local time zone considering daylight saving"""

        return time.time() + self.getTimeDiffUTC()

    def _edgeTimestampToWall(self, timestamp_ns):
        """Convert a gpiod edge event's hardware timestamp (nanoseconds,
        CLOCK_MONOTONIC by default) to wall-clock epoch seconds.

        gpiod captures edge timestamps in kernel/interrupt context at the
        moment of the electrical transition. Stamping events this way
        avoids the scheduling/poll-wakeup jitter incurred by calling
        time.time() after the fact in userspace.
        """

        anchor_monotonic_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        anchor_wall = time.time()
        return anchor_wall + (timestamp_ns - anchor_monotonic_ns) / 1e9

    def getGains(self):
        """Get camera gains via picamera2 metadata."""

        metadata = self.camera.capture_metadata()
        params = numpy.empty([6, 1])
        params[0] = metadata.get("ExposureTime", 0)
        # picamera2 does not expose ISO directly; approximate from AnalogueGain
        params[1] = int(metadata.get("AnalogueGain", 1) * 100)
        colour_gains = metadata.get("ColourGains", (1.0, 1.0))
        params[2] = colour_gains[0]
        params[3] = colour_gains[1]
        params[4] = metadata.get("AnalogueGain", 1.0)
        params[5] = metadata.get("DigitalGain", 1.0)
        return params

    def resetGains(self):
        """Reset camera to auto mode."""

        logging.debug("Resetting camera to auto mode ...")
        self.camera.set_controls(
            {
                "AeEnable": True,
                "AwbEnable": True,
                "ExposureTime": 0,
                "AnalogueGain": 0,
            }
        )

    def loadGains(self, params=""):
        """Loads camera gains from a .params file or parameter list."""

        if not params:
            logging.debug("Finding most recent parameter file ...")
            mintime = 0
            for file in os.listdir(self.root):
                fileName = os.path.join(self.root, file)
                newtime = os.path.getmtime(fileName)
                if file.endswith(".params") and newtime > mintime:
                    mintime = newtime
                    params = file
                    logging.debug("File: %s" % os.path.join(self.root, params))

        if isinstance(params, str):
            try:
                if not params.endswith(".params"):
                    params = params + ".params"
                filename = os.path.join(self.root, params)
                file = open(filename)
            except Exception:
                logging.debug("File not found")
                return
            reader = csv.reader(file)
            for row in reader:
                True
            params = [float(i) for i in row]
            file.close()

        if len(params) == 6:
            logging.debug(
                "Rotation/framerate/bitrate not stored. Consider re-saving parameter file."
            )
        elif len(params) == 9:
            self.rotation = int(params[6])
            self.framerate = int(params[7])
            if self._recording:
                logging.debug("Cannot load rotation/framerate/bitrate while recording!")
            else:
                self.configureSensor()
                self.bitrate = int(int(params[8]) * 1e6)
        else:
            logging.debug("Wrong number of parameters!")
            return None

        self._apply_gain_params(params)

        if len(params) == 9:
            logging.debug(
                "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
            )
        else:
            logging.debug("Loaded: %d %d %1.3f %1.3f %1.3f %1.3f" % tuple(params))
        meta = self.camera.capture_metadata()
        logging.debug("Actual exposure time: %d" % meta.get("ExposureTime", 0))
        logging.debug("Actual digital gain: %1.3f" % meta.get("DigitalGain", 1.0))

        if len(params) == 9:
            if int(params[8]) is not None:
                self.bitrate = int(int(params[8]) * 1e6)
        else:
            return None

    def _apply_gain_params(self, params):
        """Apply gain parameters to the camera using picamera2 controls."""
        self.resetGains()
        logging.debug("Setting camera to loaded gain values ...")
        time.sleep(1)
        controls = {
            "AeEnable": False,
            "AwbEnable": False,
            "ExposureTime": int(params[0]),
            "AnalogueGain": float(params[4]) if params[4] > 0 else 1.0,
            "ColourGains": (float(params[2]), float(params[3])),
        }
        self.camera.set_controls(controls)
        time.sleep(1)

    def setGainsParam(self, ShSp, ISO, WG1, WG2, AnG, DiG, Rot, FPS, BRate):
        """Loads camera gains from explicit parameters."""

        params = [ShSp, ISO, WG1, WG2, AnG, DiG, Rot, FPS, BRate]

        # Set rotation, fps, and bitrate
        self.rotation = int(params[6])
        self.framerate = int(params[7])
        if self._recording:
            logging.debug("Cannot load rotation/framerate/bitrate while recording!")
        else:
            self.configureSensor()
            self.bitrate = int(int(params[8]) * 1e6)

        self._apply_gain_params(params)

        logging.debug(
            "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
        )

        meta = self.camera.capture_metadata()
        logging.debug("Actual exposure time: %d" % meta.get("ExposureTime", 0))
        logging.debug("Actual digital gain: %1.3f" % meta.get("DigitalGain", 1.0))

    def loadGainsFile(self):
        """Loads camera gains from most recent file inside /GainSettings folder."""

        # Get the most recent gain file
        try:
            gFiles = [
                F
                for F in os.listdir(self.gainPath)
                if os.path.isfile(os.path.join(self.gainPath, F)) and "gain-" in F
            ]
        except IOError:
            logging.debug("No gain folder detected. Skipping load gain.")
            return

        if not gFiles:
            return
        gFiles = sorted(gFiles)
        gFile = gFiles[-1:][0]

        gFileT = int(re.findall("[0-9]+", gFile)[0])

        if gFileT > self.gainTime:
            logging.debug("New gain setting file spotted: %s" % gFile)
            time.sleep(0.01)
            self.gainTime = gFileT
            gFilePath = os.path.join(self.gainPath, gFile)
            gFileRef = open(gFilePath)
            reader = csv.reader(gFileRef)
            for row in reader:
                True
            params = [float(i.strip()) for i in row]
        else:
            return

        # Delete old gain files [keep three most recent ones]
        for i in range(len(gFiles) - 3):
            os.remove(os.path.join(self.gainPath, gFiles[i]))

        # Set rotation, fps, and bitrate
        self.rotation = int(params[6])
        self.framerate = int(params[7])
        if self._recording:
            logging.debug("Cannot load rotation/framerate/bitrate while recording!")
        else:
            self.configureSensor()
            self.bitrate = int(int(params[8]) * 1e6)

        self._apply_gain_params(params)

        logging.debug(
            "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
        )

        meta = self.camera.capture_metadata()
        logging.debug("Actual exposure time: %d" % meta.get("ExposureTime", 0))
        logging.debug("Actual digital gain: %1.3f" % meta.get("DigitalGain", 1.0))

    def signalReceived(self, sigID, stack):
        """Receives signal from other processors or even from itself."""
        logging.debug("A signal received with ID: " + str(sigID))

    def checkNewGain(self, event):
        """Checks for new gain settings"""

        while True:
            if event.isSet():
                self.loadGainsFile()
                time.sleep(0.1)

    def setGainThread(self):
        """Sets camera gain thread event."""

        self.gainThreadRunning = True

        logging.debug("Setting camera gain thread.")

        self.gainEvent = threading.Event()

        self.gainThread = threading.Thread(
            name="CameraGain", target=self.checkNewGain, args=(self.gainEvent,)
        )
        self.gainThread.daemon = True
        self.gainThread.start()

        self.gainEvent.set()

    def request_stop(self):
        """Request cooperative stop of camera loops."""

        self.stopRequested = True

    def initiateCamera(self):
        """Initiates camera for recording in circular buffer mode."""

        # a key frame (with repeated headers) every second, so a clip can start
        # within a second of its pre-event time and plays on its own
        self._encoder = H264Encoder(bitrate=self.bitrate, iperiod=self.framerate)
        self.bufferOutput = PiCamBuffer(self._encoder, self.bufferLen)
        self.camera.start()
        self.camera.start_encoder(self._encoder, self.bufferOutput)
        self._recording = True
        logging.debug("Recording initial video buffer ...")
        time.sleep(self.vidBuffer)

    def previewLoop(self, event):
        """Camera preview loop"""

        while True:
            if event.isSet():
                piCamStreamServer.serve_forever()
            else:
                time.sleep(0.5)

    def startWebPreview(self):
        """Starting Pi Camera web preview using picamera2 MJPEG encoder."""

        if not hasattr(self, "previewEvent"):
            self.previewEvent = threading.Event()
        self._stream_encoder = MJPEGEncoder()
        self._stream_encoder.output = FileOutput(piCamWebOutput)
        self.camera.start_encoder(self._stream_encoder, name="lores")
        self._streaming = True
        self.previewEvent.set()

    def stopWebPreview(self):
        """Stop pi camera web preview."""

        if hasattr(self, "previewEvent"):
            self.previewEvent.clear()
        try:
            if self._stream_encoder:
                self.camera.stop_encoder(self._stream_encoder)
                self._stream_encoder = None
                self._streaming = False
        except Exception:
            pass

    def setWebCamThread(self):
        """Set web preview thread
        It calls previewLoop function to stream pi camera to web.
        """

        self.previewEvent = threading.Event()

        self.previewThread = threading.Thread(
            name="CameraWebP", target=self.previewLoop, args=(self.previewEvent,)
        )
        self.previewThread.daemon = True
        self.previewThread.start()

    def exitSafely(self):
        """Function to exit pi camera code safely."""

        global _gpio_chip, _gpio_lines

        if hasattr(self, "previewEvent") and self.previewEvent.isSet():
            self.stopWebPreview()
        if self.gainThreadRunning:
            self.gainEvent.clear()
        try:
            if self._encoder:
                self.camera.stop_encoder(self._encoder)
        except Exception:
            pass
        try:
            if self._stream_encoder:
                self.camera.stop_encoder(self._stream_encoder)
        except Exception:
            pass
        try:
            self.camera.stop()
        except Exception:
            pass
        self.camera.close()
        self._recording = False

        # Cleanup gpiod resources
        if _gpio_chip is not None:
            try:
                _gpio_chip.release()
            except Exception:
                pass
            _gpio_chip = None
            _gpio_lines = None

        logging.debug("Program ended with exit signal = " + str(exitInst.exitStatus))
        logging.debug("Camera code is stopped successfully.")

    def recordCircular(self):
        """Start camera recording in circular mode.
        This recording mode extracts frames in circular buffer for each trial.
        """

        # initiate camera
        self.initiateCamera()

        try:
            recordFlag = 0
            lastGPIOtime = 0
            eventLog = ""
            startTime = None
            logging.debug("Waiting for trigger ...")

            while True:

                if self.stopRequested:
                    raise Exception("StopRequested")

                # wait until queue is populated
                while self.GPIOqueue.empty():

                    if self.stopRequested:
                        raise Exception("StopRequested")

                    # close the clip: line held high for T1, no event for T2, or
                    # clip as long as maxClip (save before its start leaves the buffer)
                    now = self.getTime()
                    vidStopTime = None
                    if recordFlag == 1 and now - lastGPIOtime > self.T1:
                        vidStopTime = lastGPIO[1] + self.T1 * 1e6
                    elif recordFlag == 2 and now - lastGPIOtime > self.T2:
                        vidStopTime = lastGPIO[1] + self.postBuffer * 1e6
                    elif recordFlag and now - startTime > self.maxClip:
                        vidStopTime = time.time() * 1e6

                    if vidStopTime is not None:

                        with open(self.timeFileName, "a") as timeFile:
                            timeFile.write(eventLog)
                        vidStartTime = camStartTime - self.vidBuffer * 1e6

                        duration = round((vidStopTime - vidStartTime) / 1e6)

                        self.bufferOutput.copy_to(
                            self.videoFileName,
                            self.framesFileName,
                            vidStartTime,
                            vidStopTime,
                        )
                        logging.debug(
                            "%s: Saved %s (%d seconds)\n"
                            % (
                                datetime.datetime.now().strftime("%H:%M:%S"),
                                fname,
                                duration,
                            )
                        )

                        recordFlag = 0
                        eventLog = ""

                    time.sleep(5e-4)
                    # Check exit signal
                    if exitInst.exitStatus:
                        raise Exception("An exit signal received by OS.")

                lastGPIO = self.GPIOqueue.get()

                # camera runs all day for the stream; save clips only in recording windows
                if recordFlag == 0 and not self.checkTime():
                    continue

                # start recording
                if recordFlag == 0 and lastGPIO[0] % 2 == 1:
                    camStartTime, startTime = lastGPIO[1:3]
                    lastGPIOtime = lastGPIO[2]

                    fname = self.clipName(startTime)
                    dname = getTimeFormat()
                    pname = os.path.join(self.storagePath, dname)
                    if not os.path.exists(pname):
                        os.makedirs(pname)
                    self.timeFileName = os.path.join(pname, "".join([fname, ".events"]))
                    self.videoFileName = os.path.join(
                        pname, "".join([fname, ".", self.format])
                    )
                    self.framesFileName = os.path.join(
                        pname, "".join([fname, ".frames"])
                    )

                    with open(self.timeFileName, "w") as timeFile:
                        params = tuple(self.getGains())
                        params = params + (
                            self.rotation,
                            self.framerate,
                            int(self.bitrate / 1e6),
                        )
                        timeFile.write(
                            "%d, %d, %1.3f, %1.3f, %1.3f, %1.3f, %d, %d, %1.1f\n"
                            % params
                        )
                    logging.debug(
                        "%s: Begin %s"
                        % (datetime.datetime.now().strftime("%H:%M:%S"), fname)
                    )
                    recordFlag = 1

                # wait for release
                elif recordFlag == 1 and lastGPIO[0] % 2 == 0:
                    lastGPIOtime = lastGPIO[2]
                    recordFlag = 2

                # subsequent presses (ON or OFF)
                else:  # elif lastGPIO[0] % 2 == 1:
                    lastGPIOtime = lastGPIO[2]

                eventLog += "%d, %d, %s, %.6f\n" % lastGPIO

        except KeyboardInterrupt:
            logging.debug("User interrupted the program.")

        except Exception as e:
            logging.debug("EXCEPTION HAPPENED.")
            logging.debug("Error : %s: %s \n" % ((e.__class__, e)))

        finally:
            self.exitSafely()

    def recordSchedule(self):
        """Sets recording schedule."""

        self.contPeriod = 10  # new video every X seconds

        self.startSec = [i[0] * 3600 + i[1] * 60 for i in self.recordStart]
        self.stopSec = [i[0] * 3600 + i[1] * 60 for i in self.recordStop]

    def checkTime(self):
        now = self.getTime() % 86400
        for start, stop in zip(self.startSec, self.stopSec):

            # Before and after midnight fix
            diff = stop - start
            sig = int((1 - diff / abs(diff)) / 2)
            if sig and now < start and now < stop:
                now = now + 24 * 3600
            stop = stop + 24 * 3600 * sig

            if now >= start and now < stop:
                return True
        return False

    def recordContinuous(self):
        """Start camera recording in continuous mode."""

        self.recordSchedule()
        self.recordingStatus = False
        self._cont_encoder = None
        self._cont_output = None

        # Start the camera (picamera2 needs the camera running to encode)
        self.camera.start()

        try:
            eventLog = ""
            startTime = None
            checkDelete = (
                None  # after video is saved, wait 2 seconds to see if no events
            )
            deleteName = None
            lastEvent = None

            if not self.checkTime():
                logging.debug("Waiting for alarm ...")
            while True:

                if self.stopRequested:
                    raise Exception("StopRequested")

                # Wait until queue is populated
                while self.GPIOqueue.empty():

                    if self.stopRequested:
                        raise Exception("StopRequested")

                    startFlag = not self.recordingStatus and self.checkTime()
                    stopFlag = self.recordingStatus and not self.checkTime()

                    # Split every X sec (minimum 2 sec long file), X=contPeriod
                    splitFlag = (
                        self.recordingStatus
                        and self.checkTime()
                        and self.getTime() % self.contPeriod < 0.5
                        and self.getTime() - startTime > 2
                    )

                    # delete previous video if no events within 2 seconds after video
                    if checkDelete is not None and self.getTime() - checkDelete > 2.1:
                        if eventLog == "":
                            for f in glob.glob(deleteName + "*"):
                                logging.debug("removed " + f)
                                os.remove(f)
                        checkDelete = None
                        deleteName = None

                    # stop previous recording
                    if stopFlag or splitFlag:
                        with open(timeFileName, "a") as timeFile:
                            timeFile.write(eventLog)
                        # possibly delete if no events within 2 seconds before video
                        if lastEvent is None or lastEvent < startTime - 2.1:
                            checkDelete = self.getTime()
                            deleteName = fPathNoExt

                        eventLog = ""
                        logging.debug(
                            "%s: Saved %s (%d seconds)\n"
                            % (
                                datetime.datetime.now().strftime("%H:%M:%S"),
                                fname,
                                self.getTime() - startTime,
                            )
                        )
                        if stopFlag:
                            if self._cont_encoder:
                                self.camera.stop_encoder(self._cont_encoder)
                                self._cont_encoder = None
                            if self._cont_output:
                                self._cont_output.close()
                                self._cont_output = None
                            self.recordingStatus = False
                            self._recording = False
                            logging.debug("Stopped recording.")
                            logging.debug("Waiting for alarm ...")

                    # start/split new recording
                    if startFlag or splitFlag:
                        startTime = self.getTime()
                        fname = self.clipName(startTime)
                        dname = getTimeFormat()
                        pname = os.path.join(self.storagePath, dname)
                        fPathNoExt = os.path.join(pname, fname)
                        if not os.path.exists(pname):
                            os.makedirs(pname)
                        timeFileName = os.path.join(pname, "".join([fname, ".events"]))
                        videoFileName = os.path.join(
                            pname, "".join([fname, ".", self.format])
                        )
                        framesFileName = os.path.join(
                            pname, "".join([fname, ".frames"])
                        )
                        eventLog = ""  # clear events

                        # Stop previous encoder if splitting
                        if splitFlag and self._cont_encoder:
                            self.camera.stop_encoder(self._cont_encoder)
                            if self._cont_output:
                                self._cont_output.close()

                        # setup output
                        self._cont_output = PtsOutput(videoFileName, framesFileName)
                        self._cont_encoder = H264Encoder(bitrate=self.bitrate)
                        self.camera.start_encoder(
                            self._cont_encoder,
                            FileOutput(self._cont_output),
                        )
                        if not splitFlag:
                            logging.debug("Started recording.")
                        self.recordingStatus = True
                        self._recording = True

                        logging.debug(
                            "%s: Begin %s"
                            % (datetime.datetime.now().strftime("%H:%M:%S"), fname)
                        )

                        # start events file
                        with open(timeFileName, "w") as timeFile:
                            params = tuple(self.getGains())
                            params = params + (
                                self.rotation,
                                self.framerate,
                                float(self.bitrate) / 1e6,
                            )
                            timeFile.write(
                                "%d, %d, %1.3f, %1.3f, %1.3f, %1.3f, %d, %d, %1.1f\n"
                                % params
                            )

                    if self.recordingStatus:
                        time.sleep(5e-4)
                    else:
                        time.sleep(1)

                    # Check exit signal
                    if exitInst.exitStatus:
                        raise Exception("An exit signal received by OS.")

                lastGPIO = self.GPIOqueue.get()
                lastEvent = lastGPIO[2]
                eventLog += "%d, %d, %s, %.6f\n" % lastGPIO

        except KeyboardInterrupt:
            logging.debug("User interrupted the program.")

        except Exception as e:
            logging.debug("EXCEPTION HAPPENED.")
            logging.debug("Error : %s: %s \n" % ((e.__class__, e)))

        finally:
            self.exitSafely()


if __name__ == "__main__":

    # Parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", help="Name of camera setting file", type=str)
    parser.add_argument(
        "-d",
        "--debug",
        help="Logging debug output option [1: Log File, 0:Screen]",
        default=1,
        type=int,
    )
    parser.add_argument(
        "-v", "--verbose", help="Verbose state [0 | 1]", default=1, type=int
    )
    args = parser.parse_args()

    # Setup exit signal
    global exitInst
    exitInst = safeExit()

    removeFDir("/home/pi/picamera.log")

    if args.debug:
        logging.basicConfig(
            filename="/home/pi/picamera.log",
            level=logging.DEBUG,
            format="(%(threadName)-9s) %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format="(%(threadName)-9s) %(message)s",
        )  # [.DEBUG or .INFO]

    # Read user and camera configuration
    userConfig = getUserConfig("userInfo.in", "=")
    cameraConfig = getUserConfig(args.file, "=")

    # Build schedule cache once
    rec_start, rec_stop, start_sec, stop_sec = load_schedule(
        cameraConfig, "SetInitialAlarms.h"
    )
    schedule_cache.update(
        {
            "start": rec_start,
            "stop": rec_stop,
            "start_sec": start_sec,
            "stop_sec": stop_sec,
        }
    )

    logging.debug(
        "Picamera code started on ["
        + cameraConfig["Camera_Type"]
        + "]"
        + "["
        + cameraConfig["RPi_IP"]
        + "]: "
        + getTimeFormat(withTime=True, dash=True)
    )

    # Set video local storage path in config
    subject_output_dir = resolve_subject_output_dir(userConfig)
    video_dir = os.path.join(subject_output_dir, "Video")
    cameraConfig["RPi_Video_Dir"] = video_dir

    # Sensor panel on the stream page: follows the subject's .dat files
    try:
        sensorTrace.configure(readSensorPins())
        sensorThread = threading.Thread(
            name="SensorTrace",
            target=sensorTrace.follow,
            args=(subject_output_dir, str(userConfig.get("Subject_Name", "Subject")).strip()),
        )
        sensorThread.daemon = True
        sensorThread.start()
    except Exception as e:  # the panel must never stop the camera
        logging.debug("Sensor panel off: %r" % e)

    # Start streaming server (available even when camera is off)
    if cameraConfig["WebCam_Preview"].lower() == "true":
        logging.debug(
            "Picamera web preview server starting on: "
            + cameraConfig["RPi_IP"]
            + ":"
            + cameraConfig["Stream_Port"]
        )
        if piCamWebOutput is None:
            piCamWebOutput = StreamingOutput()
        streamingPort = ("", int(cameraConfig["Stream_Port"]))
        piCamStreamServer = StreamingServer(streamingPort, StreamingHandler)
        streamingThread = threading.Thread(
            name="CameraWebServer",
            target=piCamStreamServer.serve_forever,
        )
        streamingThread.daemon = True
        streamingThread.start()

        # Its own thread, not the camera object's: that one is rebuilt each session
        threading.Thread(name="EventFeed", target=eventFeedLoop, daemon=True).start()

    # Start background storage monitor (prefer checking video dir if available)
    try:
        check_path = cameraConfig.get("RPi_Video_Dir", "/")
        threshold_pct = float(userConfig.get("Storage_Fill_Threshold", 85))
        interval_sec = int(userConfig.get("Storage_Check_Interval_Sec", 600))
        cooldown_sec = int(userConfig.get("Storage_Notify_Cooldown_Sec", 86400))
        StorageMonitor.start_storage_monitor(
            user_config=userConfig,
            check_path=check_path,
            threshold_pct=threshold_pct,
            interval_sec=interval_sec,
            cooldown_sec=cooldown_sec,
            state_file="/tmp/atmod_storage_alert_cam.json",
        )
        logging.debug(
            "Storage monitor started (path=%s, threshold=%.1f%%, interval=%ds)",
            check_path,
            threshold_pct,
            interval_sec,
        )
    except Exception as _e:
        logging.debug("Storage monitor failed to start: %s", _e)

    cam1 = None
    camThread = None

    def start_camera():
        """Start camera session if not already running."""

        global cam1, camThread
        if camThread is not None:
            return

        cam1 = PiCameraObject(
            camType=cameraConfig["Camera_Type"],
            resolution=eval(cameraConfig["Camera_Resolution"]),
            framerate=int(cameraConfig["Camera_FPS"]),
            rotation=int(cameraConfig["Camera_Rotation"]),
            bitrate=int(cameraConfig["Camera_Bitrate"]),
            camPin=int(cameraConfig["Camera_Pin"]),
            splitter_port=1,
            format=cameraConfig["Camera_Format"],
        )

        cam1.setRecordSched(cameraConfig, "SetInitialAlarms.h")
        if cameraConfig["Recording_Mode"].lower() == "b":
            cam1.setBuffer(
                preEventSaveTime=2,
                initialWaitTime=10,
                inactivityTime=5,
                postEventSaveTime=2,
                circularBufferSize=60,
                maxClipTime=50,
            )
        cam1.recordSchedule()
        cam1.setStorage(video_dir, userConfig["Subject_Name"])
        cam1.loadGainsFile()

        if cameraConfig["WebCam_Preview"].lower() == "true":
            cam1.startWebPreview()

        cam1.setGainThread()

        if cameraConfig["Recording_Mode"].lower() == "b":
            logging.debug("Recording in circular buffer mode.")
            target = cam1.recordCircular
        else:
            logging.debug("Recording in continuous mode.")
            target = cam1.recordContinuous

        camThread = threading.Thread(name="CameraRecord", target=target)
        camThread.daemon = True
        camThread.start()
        set_camera_running(True)

    def stop_camera():
        """Stop camera session if running."""

        global cam1, camThread
        if cam1:
            cam1.request_stop()
        if camThread:
            camThread.join(timeout=15)
        cam1 = None
        camThread = None
        set_camera_running(False)

    try:
        while not exitInst.exitStatus:
            if camThread is None:
                start_camera()
            elif not camThread.is_alive():
                cam1 = None
                camThread = None
                set_camera_running(False)
            time.sleep(1)
    except KeyboardInterrupt:
        logging.debug("Program ended.")
    finally:
        stop_camera()
        try:
            if piCamStreamServer:
                piCamStreamServer.shutdown()
        except Exception:
            pass
