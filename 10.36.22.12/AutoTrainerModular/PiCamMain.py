#!/usr/bin/python3

import os  # OS module (path, ...)
import io  # input/output module
import sys  # System utility module
import picamera  # Pi Camera module
import time  # Time module
import datetime  # Datetime utility
import logging  # Debugging tool
import RPi.GPIO as GPIO  # GPIO utility
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
import StorageMonitor  # Background disk usage monitor


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
                (settingName, settingValue) = eachLine.split(splitterChar)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                userConfig[settingName] = settingValue
    return userConfig


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
        resolution[1],
        resolution[0],
    )
    return PAGE


class StreamingOutput(object):
    """Streaming web output object."""

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
        with piCamWebOutput.condition:
            piCamWebOutput.condition.wait()
            frame = piCamWebOutput.frame
        return frame

    def get_page(self):
        return generateHTML([360, 640], getIP())

    def do_GET(self):
        if self.path == "/":
            self.send_response(301)
            self.send_header("Location", "/index.html")
            self.end_headers()
        elif self.path == "/index.html":
            PAGE = self.get_page()
            content = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/stream.mjpg":
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
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    """Streaming server object"""

    allow_reuse_address = True
    daemon_threads = True


class PiCamBuffer(picamera.PiCameraCircularIO):
    """Modified PiCam Buffer
    Report time of each frame
        time = self.check_frametime()
        def write(self, b):
        if time is not None and time[1]>23e3:
            logging.debug('%d, %d' % time)
        return super(PiCamBuffer, self).write(b)
    """

    def find_keyframe(self, startTime=None):  # find last keyframe before startTime
        key_frame = picamera.frames.PiVideoFrameType.sps_header

        first = None
        for frame in reversed(self.frames):  # traverse backwards in time
            if frame.timestamp is not None:
                first = frame.timestamp
            if frame.frame_type is key_frame:  # keyframe
                if first is not None and (startTime is None or first <= startTime):
                    return first
        return None

    def check_frametime(self):
        lasttime = None
        for frame in reversed(self.frames):
            if frame.timestamp is not None:
                if lasttime is None:
                    lasttime = frame.timestamp
                else:
                    return (lasttime, lasttime - frame.timestamp)
        return None

    def _find_starttime(self, startTime, stopTime=None):
        key_frame = picamera.frames.PiVideoFrameType.sps_header

        firstpos = None
        lastpos = None
        first = None
        times = []
        for frame in reversed(self.frames):  # traverse backwards in time
            if frame.timestamp is not None:
                if (
                    stopTime is None or frame.timestamp <= stopTime
                ):  # starting from stopTime
                    times.append(frame.timestamp)  # store timestamps of each frame
                    first = frame.timestamp

            if len(times) > 0 and lastpos is None:
                lastpos = frame.position

            if frame.frame_type is key_frame:  # keyframe
                if first is not None and first <= startTime:
                    firstpos = frame.position  # the last key frame before startTime
                    break
        times = list(reversed(times))
        logging.debug(
            "truStart/Stop: %d to %d" % (round(times[0] / 1e3), round(times[-1] / 1e3))
        )
        return firstpos, times, lastpos

    def copy_to(self, output, tfilename, startTime, stopTime=None):

        if isinstance(output, bytes):
            output = output.decode("utf-8")
        opened = isinstance(output, str)
        if opened:
            output = open(output, "wb")
        try:
            with self.lock:
                save_pos = self.tell()
                locktime = time.time()  # for debugging
                try:
                    pos, times, lastpos = self._find_starttime(startTime, stopTime)
                    # Copy chunks efficiently from the position found
                    if pos is not None:
                        self.seek(pos)
                        while self.tell() <= lastpos:  # copy until end of buffer
                            buf = self.read1()
                            if not buf:
                                break
                            output.write(buf)

                        # write text file
                        tfile = open(tfilename, "w")
                        tstart = min(t for t in times if t is not None)

                        tfile.write("%d\n" % tstart)

                        times[:] = [t - tstart for t in times]  # subtract off start
                        # maxdiff = max([x - times[i-1] for i, x in enumerate(times)][1:])
                        timesStr = "\n".join([str(t) for t in times])
                        tfile.write(timesStr)
                        tfile.close()
                finally:
                    self.seek(save_pos)
                """
                fname = os.path.basename(tfilename)[4:9]
                debugfile = "%s/%s.log" % (os.path.dirname(tfilename), datetime.datetime.now().strftime('%Y%m%d'))
                dfile = open(debugfile,'a')
                dfile.write('%s,%d,%d\n' % (fname,round((time.time()-locktime)*1000),maxdiff))
                dfile.close()
                """
        finally:
            if opened:
                output.close()


class PtsOutput(object):
    def __init__(self, camera, video_filename, pts_filename):
        self.camera = camera
        self.video_output = io.open(video_filename, "wb")
        self.pts_output = io.open(pts_filename, "w")
        self.start_time = None

    def write(self, buf):
        self.video_output.write(buf)
        if self.camera.frame.complete and self.camera.frame.timestamp:
            if self.start_time is None:
                self.start_time = self.camera.frame.timestamp
                self.pts_output.write("%d\n" % self.start_time)
            self.pts_output.write(
                "%d\n" % (self.camera.frame.timestamp - self.start_time)
            )

    def flush(self):
        self.video_output.flush()
        self.pts_output.flush()

    def close(self):
        self.video_output.close()
        self.pts_output.close()


class PiCameraObject(object):
    """PiCamera class definition.
    Attributes:
        camType      : type of the PiCamera object [Master | Slave]
        resolution   : resolution of video [default is 640*360]
        framerate    : frame per second [default is 60 frames per second]
        rotation     : camera rotation angle [default is 0 degree]
        bitrate      : camera bit rate [default is 3 Mbps]
        camPin       : GPIO pin number on RPi to receive events from Teensy
        splitter_port: Splitter port number on Pi camera
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
        signal.signal(signal.SIGHUP, self.signalReceived)

        self.recordStart = None
        self.recordStop = None

        self.camera = picamera.PiCamera(clock_mode="raw")

        self.setSensorMode()

        self.camera.led = False

        self.setupGPIO()

        self.GPIO_Old = None

        # Dayligh saving setting
        # self.DSTInfo = self.getDSTInfo('DST.dat')

    def setSensorMode(self):
        """Sets sensor mode."""

        if self.camera._revision == "ov5647":  # version 1
            if self.framerate > 60:
                self.camera.sensor_mode = 7
            elif self.framerate > 42:
                self.camera.sensor_mode = 6
            else:
                self.camera.sensor_mode = 4
        else:  # version 2
            if self.framerate > 40:
                self.camera.sensor_mode = 6
                logging.debug("For v2 cameras, FOV will be cropped at fps > 40.")
                logging.debug("Using 640 x 360 resolution (16:9 aspect ratio).")
                self.resolution = (640, 360)
            else:
                self.camera.sensor_mode = 4
        if self.rotation % 180 > 0:
            self.resolution = tuple(reversed(self.resolution))

        self.camera.resolution = self.resolution
        self.camera.framerate = self.framerate
        self.camera.rotation = self.rotation

    def interruptGPIO(self, channel):
        """Activates when GPIO value is changed."""

        camTime = self.camera.timestamp
        piTime = self.getTime()
        PinStatus = int(GPIO.input(self.camPin) == GPIO.HIGH)

        # Denoising
        if PinStatus != self.GPIO_Old:
            self.GPIO_Old = PinStatus
        else:
            return

        self.GPIOqueue.put((PinStatus, camTime, piTime))
        return

    def setupGPIO(self):
        """Setup GPIO to communicate with Teensy board ## BCM to BOARD"""

        self.GPIOqueue = queue.Queue()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.camPin, GPIO.IN, GPIO.PUD_DOWN)
        GPIO.add_event_detect(self.camPin, GPIO.BOTH, self.interruptGPIO)

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
                (Year, Days) = [S[0].strip(), [S[1].strip(), S[2].strip()]]
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

    def getGains(self):
        """Get camera gains."""

        params = numpy.empty([6, 1])
        g = self.camera.awb_gains
        params[0] = self.camera.exposure_speed
        params[1] = self.camera.iso
        params[2] = g[0]
        params[3] = g[1]
        params[4] = self.camera.analog_gain
        params[5] = self.camera.digital_gain
        return params

    def resetGains(self):
        """Reset camera gain."""

        logging.debug("Resetting camera to auto mode ...")
        self.camera.awb_mode = "auto"
        self.camera.iso = 0
        self.camera.shutter_speed = 0
        self.camera.exposure_compensation = 0
        self.camera.exposure_mode = "sports"

    def loadGains(self, params=""):
        """Loads camera gains."""

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
            except:
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
            if self.camera.recording:
                logging.debug("Cannot load rotation/framerate/bitrate while recording!")
            else:
                self.setSensorMode()
        else:
            logging.debug("Wrong number of parameters!")
            return None

        self.resetGains()
        logging.debug("Setting camera to loaded gain values ...")
        self.camera.iso = int(params[1])
        time.sleep(1)
        self.camera.shutter_speed = int(params[0])
        time.sleep(1)
        self.camera.awb_mode = "auto"  # 'off'
        self.camera.awb_gains = (params[2], params[3])
        while (
            abs(self.camera.digital_gain - params[5]) > 0.05
            and abs(self.camera.exposure_compensation) < 25
        ):
            if self.camera.digital_gain > params[5]:  # gain too high, make darker
                self.camera.exposure_compensation -= 1
            else:
                self.camera.exposure_compensation += 1
            time.sleep(0.3)
        self.camera.exposure_mode = "off"
        self.camera.exposure_compensation = 0
        ebest = (None, 1000000)
        s = int(params[0])
        while abs(params[0] - self.camera.exposure_speed) <= ebest[1] and ebest[1] > 0:
            ebest = (s, abs(params[0] - self.camera.exposure_speed))
            s = s + 10
            self.camera.shutter_speed = s
            time.sleep(0.3)
        self.camera.shutter_speed = ebest[0]
        time.sleep(0.3)

        if len(params) == 9:
            logging.debug(
                "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
            )
        else:
            logging.debug("Loaded: %d %d %1.3f %1.3f %1.3f %1.3f" % tuple(params))
        logging.debug("Actual exposure time: %d" % self.camera.exposure_speed)
        logging.debug("Actual digital gain: %1.3f" % self.camera.digital_gain)

        if len(params) == 9:
            if int(params[8]) is not None:
                self.bitrate = int(int(params[8]) * 1e6)
        else:
            return None

    def setGainsParam(self, ShSp, ISO, WG1, WG2, AnG, DiG, Rot, FPS, BRate):
        """Loads camera gains."""

        params = [ShSp, ISO, WG1, WG2, AnG, DiG, Rot, FPS, BRate]

        # Set rotation, fps, and bitrate
        self.rotation = int(params[6])
        self.framerate = int(params[7])
        if self.camera.recording:
            logging.debug("Cannot load rotation/framerate/bitrate while recording!")
        else:
            self.setSensorMode()
            self.bitrate = int(int(params[8]) * 1e6)

        # Reset camera gains
        self.resetGains()

        logging.debug("Setting camera to loaded gain values ...")

        # Set camera ISO
        self.camera.iso = int(params[1])
        time.sleep(1)

        # Set camera shutter speed
        self.camera.shutter_speed = int(params[0])
        time.sleep(1)

        # Set camera auto white balance
        self.camera.awb_mode = "auto"  # 'off'
        self.camera.awb_gains = (params[2], params[3])

        # Set camera digital gain
        while (
            abs(self.camera.digital_gain - params[5]) > 0.05
            and abs(self.camera.exposure_compensation) < 25
        ):
            if self.camera.digital_gain > params[5]:  # gain too high, make darker
                self.camera.exposure_compensation -= 1
            else:
                self.camera.exposure_compensation += 1
            time.sleep(0.3)

        # Set camera shutter speed
        self.camera.exposure_mode = "off"
        self.camera.exposure_compensation = 0
        ebest = (None, 1000000)
        s = int(params[0])
        while abs(params[0] - self.camera.exposure_speed) <= ebest[1] and ebest[1] > 0:
            ebest = (s, abs(params[0] - self.camera.exposure_speed))
            s = s + 10
            self.camera.shutter_speed = s
            time.sleep(0.3)
        self.camera.shutter_speed = ebest[0]
        time.sleep(0.3)

        logging.debug(
            "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
        )

        logging.debug("Actual exposure time: %d" % self.camera.exposure_speed)
        logging.debug("Actual digital gain: %1.3f" % self.camera.digital_gain)

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
        if self.camera.recording:
            logging.debug("Cannot load rotation/framerate/bitrate while recording!")
        else:
            self.setSensorMode()
            self.bitrate = int(int(params[8]) * 1e6)

        # Reset camera gains
        self.resetGains()

        logging.debug("Setting camera to loaded gain values ...")

        # Set camera ISO
        self.camera.iso = int(params[1])
        time.sleep(1)

        # Set camera shutter speed
        self.camera.shutter_speed = int(params[0])
        time.sleep(1)

        # Set camera auto white balance
        self.camera.awb_mode = "auto"
        self.camera.awb_gains = (params[2], params[3])

        # Set camera digital gain
        while (
            abs(self.camera.digital_gain - params[5]) > 0.05
            and abs(self.camera.exposure_compensation) < 25
        ):
            if self.camera.digital_gain > params[5]:  # gain too high, make darker
                self.camera.exposure_compensation -= 1
            else:
                self.camera.exposure_compensation += 1
            time.sleep(0.3)

        # Set camera shutter speed
        self.camera.exposure_mode = "off"
        self.camera.exposure_compensation = 0
        ebest = (None, 1000000)
        s = int(params[0])
        while abs(params[0] - self.camera.exposure_speed) <= ebest[1] and ebest[1] > 0:
            ebest = (s, abs(params[0] - self.camera.exposure_speed))
            s = s + 10
            self.camera.shutter_speed = s
            time.sleep(0.3)
        self.camera.shutter_speed = ebest[0]
        time.sleep(0.3)

        logging.debug(
            "Loaded: %d %d %1.3f %1.3f %1.3f %1.3f %d %d %1.1f" % tuple(params)
        )

        logging.debug("Actual exposure time: %d" % self.camera.exposure_speed)
        logging.debug("Actual digital gain: %1.3f" % self.camera.digital_gain)

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

    def initiateCamera(self):
        """Initiates camera for recording."""

        # Specify pi camera output buffer
        self.bufferOutput = PiCamBuffer(self.camera, seconds=self.bufferLen)

        # Start camera recording with specified output buffer, format, bitrate, and splitter port
        self.camera.start_recording(
            self.bufferOutput,
            format=self.format,
            bitrate=self.bitrate,
            splitter_port=self.splitter_port,
            level="4.2",
        )
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
        """Starting Pi Camera web preview"""

        self.camera.start_recording(piCamWebOutput, format="mjpeg", splitter_port=2)
        self.previewEvent.set()

    def stopWebPreview(self):
        """Stop pi camera web preview
        It clears thread, shutdowns streaming server, and stops camera on port 2
        """

        self.previewEvent.clear()
        piCamStreamServer.shutdown()
        self.camera.stop_recording(splitter_port=2)

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

        if self.previewEvent.isSet():
            self.stopWebPreview()
        if self.gainThreadRunning:
            self.gainEvent.clear()
        if self.camera.recording:
            self.camera.stop_recording(splitter_port=self.splitter_port)
        self.camera.close()
        GPIO.cleanup()
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

                # wait until queue is populated
                while self.GPIOqueue.empty():

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

                # start recording
                if recordFlag == 0 and lastGPIO[0] % 2 == 1:
                    (camStartTime, startTime) = lastGPIO[1:]
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
                            self.camera.rotation,
                            self.camera.framerate,
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

                # Wait until queue is populated
                while self.GPIOqueue.empty():

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
                            self.camera.stop_recording(splitter_port=self.splitter_port)
                            self.recordingStatus = False
                            logging.debug("Stopped recording.")
                            logging.debug("Waiting for alarm ...")

                    # start/split new recording
                    if startFlag or splitFlag:
                        startTime = self.getTime()
                        fname = "v%d-%05d" % (
                            self.camera.framerate,
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

                        # setup output
                        currOutput = PtsOutput(
                            self.camera, videoFileName, framesFileName
                        )
                        if splitFlag:
                            self.camera.split_recording(
                                currOutput, splitter_port=self.splitter_port
                            )
                        else:
                            logging.debug("Started recording.")
                            self.camera.start_recording(
                                currOutput,
                                format=self.format,
                                bitrate=self.bitrate,
                                splitter_port=self.splitter_port,
                                level="4.2",
                            )
                            self.recordingStatus = True

                        logging.debug(
                            "%s: Begin %s"
                            % (datetime.datetime.now().strftime("%H:%M:%S"), fname)
                        )

                        # start events file
                        with open(timeFileName, "w") as timeFile:
                            params = tuple(self.getGains())
                            params = params + (
                                self.camera.rotation,
                                self.camera.framerate,
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

    logging.debug(
        "Picamera code started on ["
        + cameraConfig["Camera_Type"]
        + "]"
        + "["
        + cameraConfig["RPi_IP"]
        + "]: "
        + getTimeFormat(withTime=True, dash=True)
    )

    # Initialize pi camera object
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

    # Set video local storage
    subject_output_dir = resolve_subject_output_dir(userConfig)
    video_dir = os.path.join(subject_output_dir, "Video")
    cameraConfig["RPi_Video_Dir"] = video_dir
    cam1.setStorage(video_dir)

    # IMPORTANT: any change to fps, rotation, bitrate: first stop camera, start it again
    #                (ShSp, ISO, WG1,   WG2,   AnG,   DiG,   Rot, FPS, BRate)
    # cam1.setGainsParam(3972, 800, 2.223, 0.965, 9.848, 1.414, 0, 90, 3.0)

    # Set initial gain
    cam1.loadGainsFile()

    # Create Pi camera streaming output object, and streaming web server object
    if cameraConfig["WebCam_Preview"].lower() == "true":
        logging.debug(
            "Picamera web preview started on: "
            + cameraConfig["RPi_IP"]
            + ":"
            + cameraConfig["Stream_Port"]
        )
        piCamWebOutput = StreamingOutput()
        streamingPort = ("", int(cameraConfig["Stream_Port"]))
        piCamStreamServer = StreamingServer(streamingPort, StreamingHandler)
        cam1.setWebCamThread()
        cam1.startWebPreview()

    # Set camera gain thread [Needs modification in Teensy code and MainCode]
    # ... As soon as a new gain file is located in GainSettings/ folder,
    # ... the code adjusts camera gains
    cam1.setGainThread()

    # Start camera recording based on user preference
    if not exitInst.exitStatus:
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

        if cameraConfig["Recording_Mode"].lower() == "b":
            logging.debug("Recording in circular buffer mode.")
            cam1.setBuffer(
                preEventSaveTime=2,
                initialWaitTime=10,
                inactivityTime=2,
                circularBufferSize=60,
            )
            cam1.recordCircular()
        elif cameraConfig["Recording_Mode"].lower() == "c":
            logging.debug("Recording in continuous mode.")
            cam1.recordContinuous()

    try:
        while not exitInst.exitStatus:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logging.debug("Program ended.")
