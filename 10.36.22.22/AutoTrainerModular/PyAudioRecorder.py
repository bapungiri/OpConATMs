#!/usr/bin/python3

import os                           # OS module (path, ...)
import time                         # Time module
import datetime                     # Datetime utility
import logging                      # Debugging tool
import RPi.GPIO as GPIO             # GPIO utility
import threading                    # Threading utility
import netifaces                    # Network interface to get IP
import argparse                     # Input argument parser
import queue as queue               # Queue data stracture
import glob                         # File pattern search
import signal                       # Exit signal detection
import pyaudio                      # Python audio recorder
import wave                         # Interface to WAV sound format


def getTimeFormat(withTime=False, dash=False):
    """
    Get the current time format in YYYY-MM-DD HH-MM-SS.
    """

    now = datetime.datetime.now()
    if withTime:
        if dash:
            timeFormat = now.strftime('%Y-%m-%d-%H-%M-%S')
        else:
            timeFormat = now.strftime('%Y%m%d%H%M%S')
    else:
        if dash:
            timeFormat = now.strftime('%Y-%m-%d')
        else:
            timeFormat = now.strftime('%Y%m%d')

    return timeFormat


def getUserConfig(fileName, splitterChar):
    """Function to read the user configuration file as a dictionary.
    """

    dic = {}
    with open(fileName) as configFile:
        for eachLine in configFile:
            if '=' in eachLine:
                (settingName, settingValue) = eachLine.split(splitterChar)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                dic[settingName] = settingValue
    return dic


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


class AudioRecordObject(object):
    """Audio Recorder class definition.
        Attributes:
        channels            : 1 (mono), 2(stereo)
        rate                : recording rate
        frames_per_buffer   : number of frames per buffer
        input_device        : input device ID
        format              : format of audio samples (default: pyaudio.paInt32)
        audioFormat         : Audio file format (wav)
        gpioPin             : GPIO pin to record Teensy GPIO writes
        interval            : Recording intervals
        config              : Audio setting file
    """

    def __init__(self, channels=1,
                       rate=44100,
                       frames_per_buffer=1024,
                       input_device=2,
                       format=pyaudio.paInt32,
                       audioFormat='wav',
                       gpioPin=26,
                       interval=2,
                       config=None):
        self.channels = channels
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self.input_device = input_device
        self.format = format
        self.audioFormat = audioFormat
        self.gpioPin = gpioPin
        self.interval = interval
        self.config = config

        # Flag for recording start
        self.flag = None

        # Flag for splitting wave files
        self.wavFlag = True

        self.paud = pyaudio.PyAudio()

        # Flag for recording status for GPIO file split
        self.runStatus = False

        self._stream = None

        # Set exit signal
        signal.signal(signal.SIGHUP, self.signalReceived)

        self.recordStart = None
        self.recordStop = None

        self.setupGPIO()

        # Dayligh saving setting
        self.DSTInfo = self.getDSTInfo('DST.dat')

    def interruptGPIO(self, channel):
        """Activates when GPIO value is changed.
        """

        if self.runStatus:
            piTime = self.getTime()
            pinStatus = int(GPIO.input(self.gpioPin) == GPIO.HIGH)
            self.GPIOqueue.put((pinStatus, piTime))
        return

    def setupGPIO(self):
        """Setup GPIO to communicate with Teensy board
        """

        self.GPIOqueue = queue.Queue()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpioPin, GPIO.IN, GPIO.PUD_DOWN)
        GPIO.add_event_detect(self.gpioPin, GPIO.BOTH, self.interruptGPIO)

    def setStorage(self, dirPath=None):
        """Set storage path for audio files.

        Parameters:
            dirPath : Directory path to save audio files
        """

        self.root = os.path.realpath('')

        if dirPath is None:
            self.storagePath = os.path.join(self.root, 'Audio')
        else:
            self.storagePath = dirPath

        if not os.path.exists(self.storagePath):
            os.makedirs(self.storagePath)

    def setRecordSched(self, dic, file):
        """Set audio record schedule.
        """

        self.recOpt = self.config['Record_Schedule'].lower()

        if self.recOpt == 'u':
            self.recordStart = eval(self.config['Record_Start'])
            self.recordStop = eval(self.config['Record_Stop'])
            logging.debug("".join(["The audio record start times are: ", str(self.recordStart)]))
            logging.debug("".join(["The audio record stop  times are: ", str(self.recordStop)]))

        elif self.recOpt == 't':
            self.recordStart = list()
            self.recordStop = list()

            try:
                F = open(file, 'r').readlines()
            except IOError:
                logging.debug('* EXCEPTION HAPPENED.')
                logging.debug('* Alarm schedule find not found.')
                return

            st, sp = (list(), list())
            for i, L in enumerate(F):
                if ('Training' in L) and ('SetDailyAlarms' in L) and (L.strip()[0:2] != '//') and (L.strip()[0:1] != '/'):
                    st.append(L)
                    sp.append(F[i+1])

            for i in range(len(st)):
                t1 = tuple(map(int, (st[i][st[i].find("(")+1:st[i].find(")")]).split(',')[:2]))
                t2 = tuple(map(int, (sp[i][sp[i].find("(")+1:sp[i].find(")")]).split(',')[:2]))
                self.recordStart.append(t1)
                self.recordStop.append(t2)

            logging.debug("".join(["The audio record start times are: ", str(self.recordStart)]))
            logging.debug("".join(["The audio record stop  times are: ", str(self.recordStop)]))

        self.recordSchedule()

    def getDSTInfo(self, fileName):
        """
        Function to read DST data as a dictionary.
        """

        dic = {}
        with open(fileName) as File:
            for L in File:
                L = L.strip()
                S = L.split(',')
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
        """Return local time difference with UTC considering daylight saving
        """

        TimeDiffUTC = -time.timezone
        if self.dstStatus(datetime.datetime.now()):
            TimeDiffUTC += 3600

        return TimeDiffUTC

    def getTime(self):
        """Return epoch time in local time zone considering daylight saving
        """

        return (time.time() + self.getTimeDiffUTC())

    def signalReceived(self, sigID, stack):
        """Receives signal from other processors or even from itself.
        """
        logging.debug("A signal received with ID: " + str(sigID))

    def record(self, duration):
        """blocking mode.
        """

        self._stream = self.paud.open(format=self.format,
                                      channels=self.channels,
                                      rate=self.rate,
                                      input=True,
                                      frames_per_buffer=self.frames_per_buffer,
                                      input_device_index=self.input_device)
        for _ in range(int(self.rate / self.frames_per_buffer * duration)):
            audio = self._stream.read(self.frames_per_buffer)
            self.wavefile.writeframes(audio)

    def start_recording(self):
        """non-blocking mode.
        """
        self._stream = self.paud.open(format=self.format,
                                     channels=self.channels,
                                     rate=self.rate,
                                     input=True,
                                     frames_per_buffer=self.frames_per_buffer,
                                     input_device_index=self.input_device,
                                     stream_callback=self.get_callback())

        self._stream.start_stream()

    def stop_recording(self):
        """stop audio recording in non-blocking mode
        """
        self._stream.stop_stream()

    def get_callback(self):
        """callback function in non-blocking mode
        """
        def callback(in_data, frame_count, time_info, status):

            if self.wavFlag:
                self.wavefile.writeframes(in_data)

                #  current_time: PaStreamCallbackTimeInfo
                #  input_buffer_adc_time: The time when the first sample of the input buffer was captured at the ADC input
                #  output_buffer_dac_time: The time when the first sample of the output buffer will output the DAC
                # time.time(): current RPi time

                sw = [time_info['input_buffer_adc_time'],
                      time_info['current_time'],
                      time_info['output_buffer_dac_time'],
                      self.getTime()]
                sw = ' , '.join([str(i) for i in sw])
                self.timefile.write(sw + '\n')

            return in_data, pyaudio.paContinue
        return callback

    def close(self):
        """close wave and time log files
        """
        self.wavefile.close()
        self.timefile.close()

    def setAudioFile(self, fname, mode='wb'):
        """Setup wave file
        """
        self.wavefile = wave.open(fname, mode)
        self.wavefile.setnchannels(self.channels)
        self.wavefile.setsampwidth(self.paud.get_sample_size(self.format))
        self.wavefile.setframerate(self.rate)

    def setTimeFile(self, fname):
        """Setup time file
        """
        self.timefile = open(fname, 'w')

    def writeGPIOFile(self, fname):
        """Dump GPIO values to a file.
        """
        with open(fname, 'w') as gpioFile:
            while not self.GPIOqueue.empty():
                resQ = self.GPIOqueue.get()
                gpioFile.write(str(resQ[0]) + " " + str(resQ[1]) + "\n")

    def recordAudioFiles(self, event):
        """Record audio files
        """

        while True:
            if event.isSet():

                self.runStatus = True

                fname = "a-%d-%05d" % (int(self.rate), int(self.getTime()) % 86400)
                dname = getTimeFormat()
                pname = os.path.join(self.storagePath, dname)
                if not os.path.exists(pname):
                    os.makedirs(pname)
                afile = os.path.join(pname, ''.join([fname, '.', self.audioFormat]))
                gfile = os.path.join(pname, ''.join([fname, '.gpio']))

                self.setAudioFile(afile, 'wb')
                self.setTimeFile(afile.split(".")[0]+'.times')

                self.wavFlag = True

                if not self.flag:
                    self.start_recording()
                    self.flag = True

                time.sleep(self.interval)

                self.runStatus = False
                self.writeGPIOFile(gfile)

                self.wavFlag = False

                self.close()
            else:
                time.sleep(0.1)

    def setRecordThread(self):
        """Sets audio recording thread event.
        """

        logging.debug("Setting audio recording thread.")

        self.audioEvent = threading.Event()

        self.audioThread = threading.Thread(name='AudioRecording', target=self.recordAudioFiles, args=(self.audioEvent,))
        self.audioThread.daemon = True
        self.audioThread.start()

    def exitSafely(self):
        """Function to exit code safely.
        """

        if self.isRunning:
            self.audioEvent.clear()
        GPIO.cleanup()
        try:
            self._stream.close()
            self.paud.terminate()
        except:
            pass
        logging.debug('Audio recording program ended with exit signal = ' + str(exitInst.exitStatus))
        logging.debug('Audio recording program is stopped successfully.')

    def recordSchedule(self):
        """Sets recording schedule.
        """

        self.startSec = [i[0]*3600+i[1]*60 for i in self.recordStart]
        self.stopSec = [i[0]*3600+i[1]*60 for i in self.recordStop]

    def isRunning(self):
        """Return True if audio recording thread is running.
        """
        return (self.runStatus == True)

    def getTimeFormat(self):
        """
        Get the current time format in YYYY-MM-DD HH-MM-SS.
        """

        now = datetime.datetime.now()
        timeFormat = now.strftime('%Y-%m-%d-%H-%M-%S')
        return timeFormat

    def stop(self):
        """ Stopping recording process. It clears thread.
        """

        logging.debug("Audio recording stopped: " + self.getTimeFormat())
        self.runStatus = False
        try:
            self.audioEvent.clear()
            self._stream.close()
            self.paud.terminate()
        except:
            pass

    def start(self):
        """Starting recording process.
        """

        logging.debug("Audio recording started: " + self.getTimeFormat())
        self.runStatus = True
        self.flag = False
        self.audioEvent.set()

    def isRecordingTime(self):
        """Return True if it is time for recording.
        """

        now = self.getTime() % 86400
        for (start, stop) in zip(self.startSec, self.stopSec):
            if now >= start and now < stop:
                return True
        return False


if __name__ == "__main__":

    # Parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", help='Logging debug output option [1: Log File, 0:Screen]', default=1, type=int)
    parser.add_argument("-v", "--verbose", help='Verbose state [0 | 1]', default=1, type=int)
    args = parser.parse_args()

    # Setup exit signal
    global exitInst
    exitInst = safeExit()

    removeFDir('/home/pi/pyaudiorecord.log')

    if args.debug:
        logging.basicConfig(filename='/home/pi/pyaudiorecord.log', level=logging.DEBUG, format='(%(threadName)-9s) %(message)s',)
    else:
        logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-9s) %(message)s',)    # [.DEBUG or .INFO]

    # Read audio configuration
    audioConfig = getUserConfig('audioInfo.in', '=')
    userConfig = getUserConfig('userInfo.in', '=')

    logging.debug('Audio recorder started on [' + audioConfig['Microphone_RPi_IP'] + ']: ' + getTimeFormat(withTime=True, dash=True))

    # Initialize audio recording object
    audObj = AudioRecordObject(channels=int(audioConfig['Microphone_channels']),
                               rate=int(audioConfig['Microphone_rate']),
                               frames_per_buffer=int(audioConfig['Microphone_FPB']),
                               input_device=int(audioConfig['Microphone_input_device']),
                               audioFormat=audioConfig['Microphone_audioFormat'],
                               gpioPin=int(audioConfig['Microphone_GPIO_pin']),
                               interval=int(audioConfig['Microphone_rec_interval']),
                               config=audioConfig)

    audObj.setRecordSched(audioConfig, 'SetInitialAlarms.h')

    # Set audio local storage
    audObj.setStorage(audioConfig['RPi_Audio_Dir'])

    audObj.setRecordThread()

    # Start audio recording
    try:
        while not exitInst.exitStatus:
            if audObj.isRunning():
                if not audObj.isRecordingTime():
                    audObj.stop()
            elif audObj.isRecordingTime():
                audObj.start()

            time.sleep(0.5)

    except KeyboardInterrupt:
        logging.debug("User interrupted the audio recording program.")

    except Exception as e:
        logging.debug('* EXCEPTION HAPPENED.')
        logging.debug('* Error : %s: %s \n' % (e.__class__, e))

    finally:
        audObj.stop()
        audObj.exitSafely()
        logging.debug('Program ended with exit signal = ' + str(exitInst.exitStatus))
