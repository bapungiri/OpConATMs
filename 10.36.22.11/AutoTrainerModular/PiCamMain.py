#!/usr/bin/python3

import os  # OS module (path, ...)
import io  # input/output module
import sys  # System utility module
from picamera2 import Picamera2  # Pi Camera module (Pi 5 compatible)
from picamera2.encoders import H264Encoder, MJPEGEncoder, Quality
from picamera2.outputs import FileOutput, CircularOutput
from libcamera import controls as libcamera_controls
import time  # Time module
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

SCHEDULE_LEAD_SEC = 600  # seconds before schedule to power on camera
SCHEDULE_LAG_SEC = 600  # seconds after schedule to keep camera on

manual_override = False
state_lock = threading.Lock()
controller_status = {"camera_running": False}
schedule_cache = {"start_sec": [], "stop_sec": [], "start": [], "stop": []}
piCamWebOutput = None
piCamStreamServer = None
streamingThread = None


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


def set_manual_override(state):
    """Set manual camera override flag."""

    global manual_override
    with state_lock:
        manual_override = bool(state)


def get_manual_override():
    """Return manual override flag."""

    with state_lock:
        return manual_override


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


def schedule_active_with_margin(now=None):
    """Helper to check schedule status with configured margins."""

    if now is None:
        now = time.time()
    return is_time_in_schedule(
        now,
        schedule_cache["start_sec"],
        schedule_cache["stop_sec"],
        SCHEDULE_LEAD_SEC,
        SCHEDULE_LAG_SEC,
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

    override_state = "ON" if get_manual_override() else "OFF"
    camera_state = "ON" if is_camera_running() else "OFF"
    schedule_state = "ACTIVE" if schedule_active_with_margin() else "INACTIVE"
    button_target = "/camera/off" if get_manual_override() else "/camera/on"
    button_label = "Camera Off" if get_manual_override() else "Camera On"

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
    <p>Camera Status: <b>%s</b> | Schedule (±10 min): <b>%s</b> | Manual Override: <b>%s</b></p>
    <form action="%s" method="get"><input type="submit" value="%s"></form>
    <p><img src="stream.mjpg" width="%d" height="%d" /></p>
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
        override_state,
        button_target,
        button_label,
        resolution[1],
        resolution[0],
    )
    return PAGE


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
        "/off",
        "/on",
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
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
            return

        if suffix == "/on":
            set_manual_override(True)
            self.send_response(302)
            self.send_header("Location", self._build_index_redirect(base))
            self.end_headers()
            return

        if suffix == "/off":
            set_manual_override(False)
            self.send_response(302)
            self.send_header("Location", self._build_index_redirect(base))
            self.end_headers()
            return

        if suffix == "/status":
            status = {
                "manual_override": get_manual_override(),
                "camera_running": is_camera_running(),
                "schedule_active": schedule_active_with_margin(),
            }
            payload = str(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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


class PiCamBuffer(object):
    """Circular buffer wrapper for picamera2.

    Wraps picamera2's CircularOutput to provide a copy_to method
    that extracts video segments with timestamp files, similar to the
    legacy picamera PiCameraCircularIO interface.
    """

    def __init__(self, circular_output, camera):
        self.circular_output = circular_output
        self.camera = camera

    def copy_to(self, output, tfilename, startTime, stopTime=None):
        """Save buffered video to a file and write frame timestamps.

        Parameters:
            output      : output file path (str) or file-like object
            tfilename   : path for the timestamp file
            startTime   : start timestamp in microseconds
            stopTime    : stop timestamp in microseconds (optional)
        """
        if isinstance(output, bytes):
            output = output.decode("utf-8")
        opened = isinstance(output, str)
        if opened:
            out_file = open(output, "wb")
        else:
            out_file = output
        try:
            self.circular_output.outputframe(0, out_file)
        finally:
            if opened:
                out_file.close()

        # Write timestamps file
        try:
            with open(tfilename, "w") as tfile:
                tfile.write("%d\n" % int(startTime))
                tfile.write("0\n")
        except Exception as e:
            logging.warning("Failed to write timestamp file: %s", e)


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
        self._circular_output = None
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
            self.GPIOqueue.put((PinStatus, camTime, piTime))

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
                        self.GPIOqueue.put((PinStatus, camTime, piTime))

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
        inactivityTime=2,
        circularBufferSize=60,
    ):
        """Sets camera buffer parameters.

        Parameters:
            preEventSaveTime   : Minimum pre-event buffer in sec
            initialWaitTime    : Initial wait time in sec
            inactivityTime     : Second event wait time in sec
            circularBufferSize : Total ring buffer size in sec
        """

        self.vidBuffer = preEventSaveTime
        self.T1 = initialWaitTime
        self.T2 = inactivityTime
        self.bufferLen = circularBufferSize

    def setStorage(self, dirPath=None):
        """Set storage path for video files.

        Parameters:
            dirPath : Directory path to save video files
        """

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

        self._encoder = H264Encoder(bitrate=self.bitrate)
        self._circular_output = CircularOutput(buffersize=self.bufferLen)
        self.camera.start()
        self.camera.start_encoder(self._encoder, self._circular_output)
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

                    # stop and close video if time elapses
                    if (
                        recordFlag == 1 and (self.getTime() - lastGPIOtime) > self.T1
                    ) or (
                        recordFlag == 2 and (self.getTime() - lastGPIOtime) > self.T2
                    ):

                        with open(self.timeFileName, "a") as timeFile:
                            timeFile.write(eventLog)
                        vidStartTime = camStartTime - self.vidBuffer * 1e6
                        if recordFlag == 1:
                            vidStopTime = lastGPIO[1] + self.T1 * 1e6
                        elif recordFlag == 2:
                            vidStopTime = lastGPIO[1] + self.T2 * 1e6

                        duration = round((vidStopTime - vidStartTime) / 1e6)

                        self._circular_output.fileoutput = self.videoFileName
                        self._circular_output.start()
                        time.sleep(0.1)
                        self._circular_output.stop()
                        # Write timestamps file
                        try:
                            with open(self.framesFileName, "w") as tfile:
                                tfile.write("%d\n" % int(vidStartTime))
                                tfile.write("0\n")
                        except Exception as e:
                            logging.warning("Failed to write frames file: %s", e)
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

                # start recording
                if recordFlag == 0 and lastGPIO[0] % 2 == 1:
                    camStartTime, startTime = lastGPIO[1:]
                    lastGPIOtime = lastGPIO[2]

                    fname = "v%d-%05d" % (self.framerate, int(startTime) % 86400)
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

                eventLog += "%d, %d, %s\n" % lastGPIO

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
                        fname = "v%d-%05d" % (
                            self.framerate,
                            int(startTime) % 86400,
                        )
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
                eventLog += "%d, %d, %s\n" % lastGPIO

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
                inactivityTime=2,
                circularBufferSize=60,
            )
        cam1.recordSchedule()
        cam1.setStorage(video_dir)
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
            desired_on = get_manual_override() or schedule_active_with_margin()
            if desired_on and camThread is None:
                start_camera()
            elif (not desired_on) and camThread is not None:
                stop_camera()
            elif camThread is not None and not camThread.is_alive():
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
