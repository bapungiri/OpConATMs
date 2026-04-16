#!/usr/bin/python3

import serial  # Python module to communicate with the Teensy serial
import hashlib  # For checksum generation
import time  # Python time module
import os  # Python operating system module (mkdir, rm, ...)
import datetime  # Python date and time module for time purpose
import collections  # Python advanced data type [for analog buffer]
import copy  # Python copy circular buffer in collections
import subprocess  # Python subprocess to execute bash commands
import ntplib  # Python Network Time Protocol (NTP)
import smtplib  # Python SMTP for sending email to users
import base64  # Python base64 data encodings
import email.mime.text  # Python Multipurpose Internet Mail Extensions (MIME)
import netifaces  # Python module to find device IP address
import random  # Python random number module
import RPi.GPIO as GPIO  # Python RPi GPIO utility
import re  # Python regular expression module
import signal  # Python signal module [e.g., exit signal]
from PIL import Image, ImageDraw, ImageFont  # Python Image module [change background]

import pickle
import StorageMonitor  # Background disk usage monitor


TRIAL_SUMMARY_HEADER = (
    "eventCode,port1Prob,port2Prob,chosenPort,rewarded,trialId,blockId,"
    "unstructuredProb,sessionStartEpochMs,blockStartRelMs,trialStartRelMs,trialEndRelMs\n"
)


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


def getTimeFormat():
    """
    Get the current time format in YYYY-MM-DD HH-MM-SS.
    """

    now = datetime.datetime.now()
    timeFormat = now.strftime("%Y-%m-%d-%H-%M-%S")
    return timeFormat


def writeLogFile(fileName, msgList):
    """
    Function to write lines to user log file.
    """

    msgFile = open(fileName, "a")
    msgFile.write("--------------- \n")
    msgFile.write(getTimeFormat() + "\n")
    for item in msgList:
        if "\n" in item:
            msgFile.write(item)
        else:
            msgFile.write(item + "\n")
    msgFile.close()


def getOutputDir(userConfig):
    """
    Resolve the base directory where .dat/.log/.trial.csv files are written.

    The resolved path always includes a subject-specific subdirectory so that
    each animal's data is grouped under ``Output_Dir/<Subject_Name>``.
    """

    try:
        raw = userConfig.get("Output_Dir", "").strip()
    except Exception:
        raw = ""

    if not raw or raw.lower() == "default":
        base_dir = "."
        userConfig["_Output_Dir_Fallback"] = "missing_or_default"
    else:
        base_dir = os.path.expandvars(os.path.expanduser(raw))

    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception as e:
        # Record fallback reason and fall back to current directory
        userConfig["_Output_Dir_Fallback"] = "create_failed:" + str(e)
        base_dir = "."
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            pass

    subject_name = userConfig.get("Subject_Name", "Subject")
    if not isinstance(subject_name, str):
        subject_name = str(subject_name)
    subject_name = subject_name.strip() or "Subject"
    safe_subject = subject_name.replace(os.sep, "_").replace("/", "_")

    final_dir = os.path.join(base_dir, safe_subject)
    try:
        os.makedirs(final_dir, exist_ok=True)
    except Exception as e:
        # If creating the subject subdirectory fails, fallback to base_dir but note it
        userConfig["_Output_Dir_Subdir_Fallback"] = "create_failed:" + str(e)
        final_dir = base_dir

    return final_dir


def syncRPiTime(userConfig):
    """
    Function to sync system time with NTP.
    """

    try:
        client = ntplib.NTPClient()
        response = client.request(userConfig["NTPServer"], timeout=5)
        os.system(
            "echo 3 | sudo date "
            + time.strftime("%m%d%H%M%Y.%S", time.localtime(response.tx_time))
            + ">/dev/null 2>&1"
        )
        print(
            "   ... RPi Date & Time Synced with "
            + userConfig["NTPServer"]
            + ": "
            + getTimeFormat()
        )
    except Exception as e:
        print("   ... * EXCEPTION HAPPENED.")
        print("   ... * System time sync with NTP server failed.")
        print("   ... * Check network connection.")
        print("   ... * Error : %s: %s \n" % (e.__class__, e))
        exit("   ... * Exiting the program.")


def backupFile(fileName):
    """
    Function to backup a file. New name: current name + current date/time ## TBU
    """

    if os.path.exists(fileName):
        fileNameOnly, fileExtension = os.path.splitext(fileName)
        now = datetime.datetime.now()
        newFileName = "".join(
            [fileNameOnly, " ", now.strftime("%Y-%m-%d %H-%M-%S"), fileExtension]
        )
        subprocess.call(["mv", fileName, newFileName])
        print("   ... File " + fileName + " backed up.")
    else:
        print("   ... File " + fileName + " created.")


def createInitialFile(fileName, fileStatus):
    """
    Function to create an initial file.
    """
    # Ensure parent directory exists
    try:
        parent = os.path.dirname(fileName)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
    except Exception:
        pass
    f = open(fileName, fileStatus)
    f.close()


def getUserConfig(fileName, splitterChar):
    """
    Function to read the user configuration file as a directory.
    """

    userConfig = {}
    with open(fileName) as configFile:
        for eachLine in configFile:
            # Remove inline comments (anything after a '#') and trim whitespace
            line = eachLine.split("#", 1)[0].strip()
            # Skip blank or comment-only lines
            if not line:
                continue
            if splitterChar in line:
                (settingName, settingValue) = line.split(splitterChar, 1)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                # Optionally strip wrapping quotes from values
                if (settingValue.startswith('"') and settingValue.endswith('"')) or (
                    settingValue.startswith("'") and settingValue.endswith("'")
                ):
                    settingValue = settingValue[1:-1]
                userConfig[settingName] = settingValue
    return userConfig


def compileUploadTeensy(userConfig):
    """
    Function to compile and upload Teensy code using Python subprocess module
    """

    if userConfig["Reset_Teensy_Build"].lower() == "true":
        if os.path.exists("/home/pi/AutoTrainerModular/Build/"):
            subprocess.call(["rm", "-rf", "/home/pi/AutoTrainerModular/Build/"])

    if not os.path.exists("/home/pi/Build/"):
        print("   ... Creating a new build directory.")
        subprocess.call(["mkdir", "/home/pi/AutoTrainerModular/Build/"])

    print("   ... Killing the previous Teensy process if running.")
    subprocess.call(["pkill", "teensy"])

    compileCmd = "arduino-cli compile -v /home/pi/AutoTrainerModular/AutoTrainerModular.ino \
                  --fqbn teensy:avr:teensy41 \
                  --output-dir /home/pi/AutoTrainerModular/Build \
                  --libraries /home/pi/.arduino15/packages/teensy/hardware/avr/1.57.2/libraries"

    # compileCmd = "xvfb-run -a arduino --upload AutoTrainerModular.ino --board teensy:avr:teensy41:usb=serial,speed=600,opt=osstd"

    uploadCmd = "teensy_loader_cli -w /home/pi/AutoTrainerModular/Build/AutoTrainerModular.ino.hex --mcu=TEENSY41 -sv"

    try:
        print("   ... Compiling and uploading the *.ino file.")
        subClient = subprocess.Popen(
            "(echo COMPILING; %s || echo FAILED TO COMPILE; exit 1) || (echo UPLOADING; (%s || %s) || echo FAILED TO UPLOAD)"
            % (compileCmd, uploadCmd, uploadCmd),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subOutput, subError = subClient.communicate()

        # Normalize to text for checks
        if isinstance(subOutput, bytes):
            subOutputText = subOutput.decode("utf-8", "ignore")
        else:
            subOutputText = str(subOutput)

        if "FAILED" in subOutputText:
            raise Exception("Error in uploading Teensy code.")

        print("   ... Program uploaded to Teensy board successfully.")

    except Exception as e:
        print("   ... * EXCEPTION HAPPENED.")
        print("   ... * Teensy code failed compilation or upload processes.")
        print("   ... * Check Teensy code and serial port & run the program.")
        print("   ... * Error : %s: %s \n" % (e.__class__, e))
        exit("   ... * Exiting the program.")

    finally:
        print("   ... Arduino compiler output:")
        print("   ... ========================")
        try:
            for line in subOutput.splitlines():
                if isinstance(line, bytes):
                    line = line.decode("utf-8", "ignore")
                print("   ... " + line)
        except Exception:
            pass
        print("   ... ========================")


def getOpenPort(port0, port1):
    """
    Function to get a working serial port (Teensy or Hardware Serial)
    """

    def portIsOpen(portName):
        """
        Function to check if a serial port is available
        """

        try:
            ser = serial.Serial(port=portName)
            return True
        except:
            return False

    timeRecordSerial = time.time()

    while True:
        if portIsOpen(port0):
            return port0
        if portIsOpen(port1):
            return port1

        if time.time() - timeRecordSerial > 10:
            print("   ... * EXCEPTION HAPPENED.")
            print("   ... * Serial ports " + port0 + " , " + port1 + " are not open.")
            print("   ... * Try < dmesg | grep tty* > in Linux shell.")
            print("   ... * Check serial and USB connections.")
            exit("   ... * Error: exiting the program.")

        time.sleep(1.0 / 10000.0)


def getSerialConnection(port0, port1, bRate):
    """
    Function to create and return a serial connection to Teensy
    """

    ser = serial.Serial(
        port=getOpenPort(port0, port1),
        baudrate=bRate,
        bytesize=8,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0,
    )

    return ser


def checkSerialConnection(ser):
    """
    Function to check a serial connection.
    """

    if not ser.isOpen():
        print("   ... The " + ser.port + " is NOT open. Re-submit the job.")
        return False
    else:
        print("   ... The serial port " + ser.port + " is open and ready.")
        return True


def getDSTInfo(fileName):
    """
    Function to read DST data as a dictionary.
    """

    DSTInfo = {}
    with open(fileName) as File:
        for L in File:
            L = L.strip()
            S = L.split(",")
            (Year, Days) = [S[0].strip(), [S[1].strip(), S[2].strip()]]
            DSTInfo[Year] = Days
    return DSTInfo


def dstStatus(dt, DSTInfo):
    """
    Function to check Daylight Saving status.
    """

    Y = str(dt.year)
    d1 = int(DSTInfo[Y][0])
    d2 = int(DSTInfo[Y][1])
    dst_start = datetime.datetime(dt.year, 3, d1, 2, 0)
    dst_start += datetime.timedelta(6 - dst_start.weekday())
    dst_end = datetime.datetime(dt.year, 11, d2, 2, 0)
    dst_end += datetime.timedelta(6 - dst_end.weekday())
    return dst_start <= dt < dst_end


def syncTimeNTP(ser, userConfig, msgFileN=None):
    """
    Function to sync Teensy date/time with Network Time Protocol (NTP)
    """

    # Find time offset between current and UTC time zone in sec
    TimeDiffUTC = -time.timezone

    # Apply Daylight Saving
    # DSTInfo = getDSTInfo('DST.dat')
    # if dstStatus(datetime.datetime.now(), DSTInfo):
    #    TimeDiffUTC += 3600

    # Get the time from NTPServer
    try:
        client = ntplib.NTPClient()
        response = client.request(userConfig["NTPServer"], timeout=5)
        timeT = "T" + str(response.tx_time + TimeDiffUTC)
        try:
            ser.write(timeT.encode("ascii", "ignore"))
        except Exception:
            ser.write(timeT)  # fallback
        if msgFileN:
            msgList = [
                "Info: syncTimeNTP",
                "RPi Time: " + getTimeFormat(),
                "NTP Time: " + timeT.replace("T", ""),
                "NTP to Local: "
                + time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(float(response.tx_time))
                ),
            ]
            writeLogFile(msgFileN, msgList)
        else:
            print("   ... Teensy date and time synced with " + userConfig["NTPServer"])

    except Exception as e:
        if msgFileN:
            msgList = [
                "Error:",
                "EXCEPTION HAPPENED.",
                "The program could not sync Teensy time with NTP time server.",
                "Check the internet connection and re-run the program.",
                "Error : %s: %s \n" % (e.__class__, e),
            ]
            writeLogFile(msgFileN, msgList)
        else:
            print("   ... * EXCEPTION HAPPENED.")
            print(
                "   ... * The program could not sync Teensy time with NTP time server."
            )
            print("   ... * Check the internet connection and re-run the program.")
            print("   ... * Error : %s: %s \n" % (e.__class__, e))
            exitInst.exitStatus = True
            return


def sendEmail(errorMessage, userConfig, msgFileN, emailSubject=None):
    """
    Function to send customized emails to users.
    """

    if userConfig["Enable_Email"].lower() == "true":
        recipientName = userConfig["Name"]
        recipientEmail = userConfig["Email"]
        emailUser = userConfig["WD_Email"]

        tmpCred = userConfig["WD_Pass"].split("|||")
        for i in range(int(tmpCred[0])):
            tmpCred[1] = base64.b64decode(tmpCred[1])
        emailPass = tmpCred[1]

        ipAddress = netifaces.ifaddresses("eth0")[netifaces.AF_INET][0]["addr"]

        sent_from = emailUser
        to = [recipientEmail]

        if emailSubject is None:
            subject = "Issue with experiment in box: " + userConfig["Box_Name"]
        else:
            subject = emailSubject + " in box: " + userConfig["Box_Name"]

        body = "".join(
            [
                "Hello ",
                recipientName,
                ",\n\n",
                "There is an issue with your experiment.\n\n",
                "The error message:\n\n",
                errorMessage,
                "\n\n",
                "Please check your box as soon as possible.\n\n",
                "Date and Time: ",
                getTimeFormat(),
                "\n\n",
                "The IP address: ",
                ipAddress,
                "\n\n",
                "-RPi Watchdog",
            ]
        )

        try:
            msg = email.mime.text.MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = emailUser
            msg["To"] = recipientEmail

            smtpAddress = userConfig["WD_SMTP"].lower()
            smtpPort = int(userConfig["WD_SMTP_Port"])
            if userConfig["WD_SSL"].lower() == "true":
                s = smtplib.SMTP_SSL(smtpAddress, smtpPort)
            else:
                s = smtplib.SMTP(smtpAddress, smtpPort)

            s.ehlo()
            s.login(emailUser, emailPass)
            s.sendmail(emailUser, recipientEmail, msg.as_string())
            s.close()

            print("   ... An email sent to: " + recipientName)

        except Exception as e:
            msgList = [
                "Error:",
                "       Error happened in sending email.",
                "       Email authentication failed.",
                "       Error : %s: %s" % (e.__class__, e),
            ]
            writeLogFile(msgFileN, msgList)


def getAnalogDirPath(userConfig):
    """
    Function to get analog folder path.
    """

    now = datetime.datetime.now()
    analogFolderDateName = now.strftime("%Y-%m-%d")
    analogDirPath = "".join(
        ["Analog-", userConfig["Subject_Name"], "/", analogFolderDateName]
    )

    if not os.path.exists(analogDirPath):
        os.makedirs(analogDirPath)

    return analogDirPath


def getAnalogTempFileName(userConfig):
    """
    Function to get temporary file name for analog files
    """

    tempName = "".join(
        [getAnalogDirPath(userConfig), "/anTemp.", str(int(time.time()))]
    )

    return tempName


def checkDailyWater(dailyWater, userConfig, msgFileN):
    """
    Function to check daily water and to send daily emails to users.
    """

    if dailyWater > 0:

        dailyWaterQuota = int(userConfig["Daily_Water"])
        minWaterPercentage = int(userConfig["Water_Minimum"].replace("%", ""))
        minWater = int(minWaterPercentage * 1.0 / 100 * dailyWaterQuota)

        if dailyWater < minWater:
            emailSubject = "Low daily water consumption"
            emailText = "".join(
                [
                    "Your subject consumed ",
                    str(dailyWater),
                    " pulses of water.",
                    " It is less than ",
                    str(minWaterPercentage),
                    "% of daily water quota of ",
                    str(dailyWaterQuota),
                    " pulses",
                ]
            )
            time.sleep(1 * random.random())
            sendEmail(emailText, userConfig, msgFileN, emailSubject)

    return 0


def renameQueueFiles(Q1, Q2, msgFileN):
    """
    Function to rename file names from two queues
    """

    if len(Q1) and len(Q2):
        F1 = Q1.popleft()
        F2 = Q2.popleft()

        if os.path.exists(F1):
            os.rename(F1, F2)
        else:
            msgList = [
                "Error:",
                "       Error in analog file name.",
                "       Queue did not work.",
                "       Modify analog saving.",
                F1,
                "       anFileName:",
                F2,
            ]
            writeLogFile(msgFileN, msgList)


def elapsedTime(D, T, option="S"):
    """
    Function to return elapsed time from a datetime object
    """

    cases = {
        "S": (T - D).seconds % 60,
        "M": ((T - D).seconds % 3600) // 60,
        "H": (T - D).days * 24 + (T - D).seconds // 3600,
    }

    return cases[option]


def changeOutputFileN(D, FN, Dic):
    """
    Function to change the output file name.
    Preserves the directory of the current file name (FN) and rotates only the base name.
    """

    freq = Dic.get("Output_Name_Freq", "false").lower()
    if freq != "false":

        H = int(freq.replace("hr", ""))

        T = datetime.datetime.now()

        if elapsedTime(D, T, "H") >= H:
            dirName = os.path.dirname(FN)
            baseName = "".join([Dic["Subject_Name"], "-", getTimeFormat(), ".dat"])
            FN = os.path.join(dirName if dirName else ".", baseName)
            D = T

    return [D, FN]


def setupGPIO(userConfig):
    """
    Function to setup GPIO.
    """

    # Keep Teensy Reset & Program pins HIGH
    if "GPIO_Pin_Type" in userConfig:
        print("   ... Writing GPIO.HIGH to Teensy reset and program pins")
        teensyProgPin = int(userConfig["Program_Pin"])
        if userConfig["GPIO_Pin_Type"].lower() == "bcm":
            GPIO.setmode(GPIO.BCM)
        elif userConfig["GPIO_Pin_Type"].lower() == "board":
            GPIO.setmode(GPIO.BOARD)
        GPIO.setup(teensyProgPin, GPIO.OUT)
        GPIO.output(teensyProgPin, GPIO.HIGH)


def includeSMHeader(srcF, destF):
    """
    Function to include state machine header files.
    """

    with open(srcF, "r") as f:
        dat = f.readlines()
    d = "".join(dat)
    smList = re.findall(r"SM{1}\((\w+)\)", d)

    dat = [
        "/*\n",
        "  Include the header file for all state machines.\n",
        "*/\n",
        "\n",
        "#ifndef _AllStateMachineHeaders_h\n",
        "#define _AllStateMachineHeaders_h\n",
        "\n",
        "//-->[0]\n",
        "//<--[0]\n",
        "\n",
        "#endif\n",
    ]

    with open(destF, "w") as f:
        for i, L in enumerate(dat):
            if "//-->[0]" in L:
                for sm in smList:
                    L = "".join([L, '#include "StateMachines/', sm, 'Machine.h"\n'])
                dat[i] = L
                f.write("".join(dat))
                break

    # Check 'SpecificFunctions.h' in StateMachines folder
    if not os.path.exists("StateMachines/SpecificFunctions.h"):
        dat = [
            "/*\n",
            "  This file defines specific functions shared between state machines.\n",
            "*/\n",
            "\n",
            "#ifndef _SpecificFunctions_h\n",
            "#define _SpecificFunctions_h\n",
            "\n",
            "\n",
            "\n",
            "#endif\n",
        ]

        with open("StateMachines/SpecificFunctions.h", "w") as f:
            f.write("".join(dat))


def printText(L1, L2, L3, L4, S1, S2, S3, S4, fontSpec, drwSpec):
    """
    Function to print text to image
    """

    drwSpec.text(L1, S1, font=fontSpec, fill=(255, 255, 0))
    drwSpec.text(L2, S2, font=fontSpec, fill=(255, 255, 0))
    drwSpec.text(L3, S3, font=fontSpec, fill=(255, 255, 0))
    drwSpec.text(L4, S4, font=fontSpec, fill=(255, 255, 0))


def changeDesktopBackground(userConfig):
    """
    Function to change desktop background
    """

    deskW = 1920
    deskH = 1080
    imgTemplate = Image.new("RGB", (deskW, deskH), color=(64, 48, 83))

    fontSpec = ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeSans.ttf", 25)
    drwSpec = ImageDraw.Draw(imgTemplate)

    # Text to be written
    S1 = "".join(["User: ", userConfig["Name"]])
    S2 = "".join(["IP: ", userConfig["RPi_IP"]])
    S3 = "".join(["Box: ", userConfig["Box_Name"]])
    S4 = "".join(["Subject: ", userConfig["Subject_Name"]])

    # Add text to image
    for i in range(4):
        for j in range(5):
            x = 200 + i * 475
            y = 70 + j * 200
            printText(
                (x, y),
                (x, y + 30),
                (x, y + 60),
                (x, y + 90),
                S1,
                S2,
                S3,
                S4,
                fontSpec,
                drwSpec,
            )

    # Save image to Desktop
    imgTemplate.save("/home/pi/backImage.jpg")
    subprocess.call(
        ["pcmanfm", "--set-wallpaper=/home/pi/backImage.jpg"],
        env=dict(os.environ, DISPLAY=":0.0", XAUTHORITY="/home/pi/.Xauthority"),
    )
    print("   ... Desktop background changed.")


def printSerialOutput(ser, anSer, userConfig, analogEnabled, expStartTime):
    """
    Function to read the available serial port.
    """

    # Final check for serial access
    if not checkSerialConnection(ser):
        return
    if analogEnabled:
        if not checkSerialConnection(anSer):
            return

    # Change desktop background
    changeDesktopBackground(userConfig)

    # Read serial port and write to output and analog folder [if enabled]
    try:

        # Write SubmitComplete to log.out fileExt
        logFile = open("log.out", "a")
        logFile.write("   ... SubmitComplete\n")
        logFile.close()

        # Open output file and message log file initially
        out_dir = getOutputDir(userConfig)
        # Log resolved output directory & any fallback
        fallbackReason = userConfig.get("_Output_Dir_Fallback")
        with open("log.out", "a") as _lf:
            if fallbackReason:
                _lf.write(
                    "WARNING: Output_Dir fallback to '.' ({}) at {}\n".format(
                        fallbackReason, getTimeFormat()
                    )
                )
            _lf.write(
                "INFO: Using Output_Dir={} at {}\n".format(out_dir, getTimeFormat())
            )
        base = "".join([userConfig["Subject_Name"], "-", getTimeFormat()])
        outputFileN = os.path.join(out_dir, base + ".dat")
        msgFileN = os.path.join(out_dir, base + ".log")
        # Parallel trial summary file (.trial.csv) to hold extended trial summary lines (eventCode >=200)
        trialSummaryFileN = outputFileN.replace(".dat", ".trial.csv")
        createInitialFile(outputFileN, "a")
        createInitialFile(msgFileN, "a")
        # Ensure trial summary file exists before size check
        createInitialFile(trialSummaryFileN, "a")
        try:
            needHeader = os.path.getsize(trialSummaryFileN) == 0
        except OSError:
            needHeader = True
        if needHeader:
            with open(trialSummaryFileN, "a") as tsf_init:
                tsf_init.write(TRIAL_SUMMARY_HEADER)

        # Initialize counters for session integrity
        dataLineCount = 0  # number of legacy 8-field lines written to .dat
        trialSummaryLineCount = 0  # number of trial summary lines written to .trial.csv

        # Log the current date
        currentDate = datetime.datetime.now()

        totalDataRead = ""

        if analogEnabled:
            totalAnalogRead = ""
            if not os.path.exists("".join(["Analog-", userConfig["Subject_Name"]])):
                os.makedirs("".join(["Analog-", userConfig["Subject_Name"]]))
            anBufferSize = int(userConfig["Before_Buffer"])
            anBuffer = collections.deque(maxlen=anBufferSize)
            anInitialWriteStatus = False
            anWriteStatus = False
            anTempFileName = ""
            anFileName = ""
            anFileNamePins = ""
            anFileNameBuffer = collections.deque(maxlen=10)
            anTempFileNameBuffer = collections.deque(maxlen=10)

        # Reset daily Water
        dailyWater = 0

        # Serial time out check
        lastTimeSerialCheck = int(time.time())
        serialTimeOutCheck = int(userConfig["Serial_TimeOut"])

        # Teensy time sync
        lastTimeSync = int(time.time())
        teensyTimeSyncFreq = int(
            float((userConfig["TimeSyncFreq"].lower()).replace("hr", "")) * 3600
        )

        while True:

            # This helps in optimization of CPU usage
            # time.sleep(1.0/100000.0)  # should be smaller than the 1kHz

            # Check available data in serial and read them
            try:
                dataToRead = ser.inWaiting()
                dataRead = ser.read(dataToRead)
            except KeyboardInterrupt:
                raise Exception("Teensy Serial Port User Interrupt Error")
            except Exception:
                sendEmail("The serial port is not open.", userConfig, msgFileN)
                raise Exception("Teensy Serial Port Not Available Error")

            if isinstance(dataRead, bytes):
                dataRead = dataRead.decode("utf-8", "ignore")

            totalDataRead = "".join([totalDataRead, dataRead])

            # True indicates all lines ends in \n
            completeLine = True

            # Check if all lines end in \n
            for line in totalDataRead.splitlines(True):
                if "\n" not in line:
                    completeLine = False
                    break

            # Open output file to append text
            f = open(outputFileN, "a")
            tsf = open(trialSummaryFileN, "a")  # open trial summary file for this cycle

            if len(totalDataRead) == 0:
                if (int(time.time()) - lastTimeSerialCheck) > serialTimeOutCheck:
                    msgList = ["Error:", "Teensy serial port is idle"]
                    writeLogFile(msgFileN, msgList)

                    # Send an email if serial is not available
                    sendEmail("Teensy serial port is idle.", userConfig, msgFileN)

                    lastTimeSerialCheck = int(time.time())
                    # raise Exception('Teensy Serial Port IDLE Error')
            else:
                lastTimeSerialCheck = int(time.time())

            # If all lines end in \n, then write to output file or analog file
            if completeLine and len(totalDataRead) > 1:
                for eachLine in totalDataRead.splitlines(True):
                    words = eachLine.split(",")

                    # This tag indicates (I)nformation from Teensy
                    if words[0] == "I":
                        msgList = ["Info:", eachLine[2:]]
                        writeLogFile(msgFileN, msgList)

                    # This tag indicates (E)rror from Teensy
                    elif words[0] == "E":
                        msgList = ["Error:", eachLine[2:]]
                        writeLogFile(msgFileN, msgList)

                    # This tag indicates daily water report from Teensy
                    elif words[0] == "D":
                        dailyWater = int(words[1])

                    # This tag indicates pin numbers in analog reading
                    elif words[0] == "P":
                        if analogEnabled:
                            anFileNamePins = (
                                "."
                                + ".".join(
                                    [words[i] for i in range(1, len(words))]
                                ).rstrip()
                            )

                    # Otherwise, it is a regular output, just append to output
                    else:
                        # Detect trial summary lines (event codes >=200) independent of field count
                        isNumeric = words[0].isdigit()
                        if isNumeric and int(words[0]) >= 200:
                            tsf.write(eachLine)
                            trialSummaryLineCount += 1
                            continue

                        # Legacy regular output lines must have exactly 8 fields
                        if len(words) != 8:
                            msgList = [
                                "Error:",
                                "       Error in reading serial (unexpected field count).",
                                "       Modify serial read or update parser.",
                                eachLine,
                            ]
                            writeLogFile(msgFileN, msgList)
                        else:
                            if analogEnabled:
                                # This tag indicates start of analog saving
                                if words[0] == "99":
                                    if anFileNamePins:
                                        analogDirPath = getAnalogDirPath(userConfig)
                                        anFileName = (
                                            analogDirPath
                                            + "/an."
                                            + ".".join(
                                                [
                                                    words[i]
                                                    for i in reversed(range(4, 6))
                                                ]
                                            ).rstrip()
                                        )
                                        anFileName = "".join(
                                            [anFileName, anFileNamePins]
                                        )
                                    else:
                                        msgList = [
                                            "Error:",
                                            "       Error in analog file name.",
                                            "       Analog pin file names missing.",
                                            "       Modify analog saving.",
                                        ]
                                        writeLogFile(msgFileN, msgList)

                                # This tag indicates end of analog saving
                                if words[0] == "98":
                                    if anFileName:
                                        anFileNameBuffer.append(anFileName)
                                    else:
                                        msgList = [
                                            "Error:",
                                            "       Error in analog file name.",
                                            "       Real analog file name missing.",
                                            "       Modify analog saving.",
                                        ]
                                        writeLogFile(msgFileN, msgList)

                            f.write(eachLine)
                            dataLineCount += 1

                # Reset accumulated string
                totalDataRead = ""

            if analogEnabled:
                # Check available data in analog USB serial and read them
                try:
                    anDataToRead = anSer.inWaiting()
                    anDataRead = anSer.read(anDataToRead)
                except KeyboardInterrupt:
                    raise Exception("Analog USB Port User Interrupt Error")
                except Exception:
                    sendEmail("The analog USB port is not open.", userConfig, msgFileN)
                    raise Exception("Analog USB Port Not Available Error")

                if isinstance(anDataRead, bytes):
                    anDataRead = anDataRead.decode("utf-8", "ignore")
                totalAnalogRead = "".join([totalAnalogRead, anDataRead])
            # ...existing code...

            # close the file until next read [for tail -f output]
            f.close()
            tsf.close()

            # Change temporary analog file names
            if analogEnabled:
                renameQueueFiles(anTempFileNameBuffer, anFileNameBuffer, msgFileN)

            # Check daily water and report it to user
            dailyWater = checkDailyWater(dailyWater, userConfig, msgFileN)

            # Check Teensy time synced
            if (int(time.time()) - lastTimeSync) > teensyTimeSyncFreq:
                syncTimeNTP(ser, userConfig, msgFileN)
                lastTimeSync = int(time.time())

            # Check output [result] file name and changed it daily
            if "Output_Name_Freq" in userConfig:
                prevDat = outputFileN
                prevTrial = trialSummaryFileN
                prevDataCount = dataLineCount
                prevTrialCount = trialSummaryLineCount
                [currentDate, outputFileN] = changeOutputFileN(
                    currentDate, outputFileN, userConfig
                )
                if prevDat != outputFileN:  # rotation occurred
                    # Write rotation marker to old files (not counted in checksum metrics)
                    rotEpoch = int(time.time())
                    try:
                        with open(prevDat, "a") as pf:
                            pf.write(
                                "ROTATE,{},{},{}\n".format(
                                    rotEpoch, prevDataCount, prevTrialCount
                                )
                            )
                        with open(prevTrial, "a") as ptf:
                            ptf.write(
                                "ROTATE,{},{},{}\n".format(
                                    rotEpoch, prevDataCount, prevTrialCount
                                )
                            )
                    except Exception:
                        pass
                    # Files remain on disk uncompressed after rotation

                    # Prepare new trial summary file matching rotated .dat
                    trialSummaryFileN = outputFileN.replace(".dat", ".trial.csv")
                    createInitialFile(trialSummaryFileN, "a")
                    try:
                        needHeaderNew = os.path.getsize(trialSummaryFileN) == 0
                    except OSError:
                        needHeaderNew = True
                    if needHeaderNew:
                        with open(trialSummaryFileN, "a") as tsf_init:
                            tsf_init.write(TRIAL_SUMMARY_HEADER)

            # Check exit signal
            if exitInst.exitStatus:
                raise Exception("An exit signal received by OS.")

    except KeyboardInterrupt:
        print("   ... Program ended: User interrupted the program.")
        try:
            if "f" in locals() and hasattr(f, "close"):
                f.close()
            if "tsf" in locals() and hasattr(tsf, "close"):
                tsf.close()
        except Exception:
            pass

    except Exception as e:
        print("   ... Program ended: Error occurred.")
        print("   ... Error : %s: %s \n" % (e.__class__, e))
        try:
            if "f" in locals() and hasattr(f, "close"):
                f.close()
            if "tsf" in locals() and hasattr(tsf, "close"):
                tsf.close()
        except Exception:
            pass

    finally:
        # Session-end flush / integrity marker (with checksums & counts)
        try:

            def file_md5(p):
                if not os.path.exists(p):
                    return "NA"
                h = hashlib.md5()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(8192), b""):
                        h.update(chunk)
                return h.hexdigest()

            dat_md5 = file_md5(outputFileN)
            trial_md5 = file_md5(trialSummaryFileN)
            epoch_end = int(time.time())
            marker = "SE,{},{},{},{},{}\n".format(
                epoch_end, dataLineCount, trialSummaryLineCount, dat_md5, trial_md5
            )
            # with open(outputFileN, "a") as f_end:
            #     f_end.write(marker)
            with open(trialSummaryFileN, "a") as tsf_end:
                tsf_end.write(marker)
        except Exception as e:
            msgList = [
                "Error:",
                "       Failed to write session-end marker: {0}".format(e),
            ]
            writeLogFile(msgFileN, msgList)

        print("   ... The current time: " + getTimeFormat())
        # Build session-end summary line without f-strings for wider Python compatibility
        _dat_md5_val = locals().get("dat_md5", "NA")
        _trial_md5_val = locals().get("trial_md5", "NA")
        msgList = [
            "Program ended with exit signal = " + str(exitInst.exitStatus),
            "Session-End Marker: dataLines={0}, trialLines={1}, dat_md5={2}, trial_md5={3}".format(
                dataLineCount, trialSummaryLineCount, _dat_md5_val, _trial_md5_val
            ),
        ]
        writeLogFile(msgFileN, msgList)


def getEverything(ser, duration):
    everything = []
    startTime = time.time()

    while True:
        # line = anSer.readline()
        # everything.append(line)
        everything.append(ser.readline())

        if time.time() - startTime >= duration:
            print("BREAKING")
            break

    with open("everything.list", "wb") as file:
        pickle.dump(everything, file)

    print("EXITING")
    exit()


def liveMonitor(ser):
    while True:
        line = ser.readline()

        if line != "":
            print(line)


def addCrontab(userConfig):
    minute = userConfig["Daily_Time"].split(":")[1]
    hour = userConfig["Daily_Time"].split(":")[0]
    cmd = (
        'script="convertAndTransfer.py" ; cwd="$PWD/" ; echo "%s %s * * * cd $cwd ; sudo python3 $cwd/$script" | crontab -'
        % (minute, hour)
    )

    try:
        subClient = subprocess.Popen(
            cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE
        )
        subOut, subErr = subClient.communicate()

    except Exception as e:
        print(
            "failed to add convertAndTransfer icrontab:\n%s\n%s\n%s"
            % (subOut, subErr, e)
        )


def removeCrontab():
    cmd = "crontab -r"

    try:
        subClient = subprocess.Popen(
            cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE
        )
        subOut, subErr = subClient.communicate()

    except Exception as e:
        print(
            "failed to remove convertAndTransfer crontab:\n%s\n%s\n%s"
            % (subOut, subErr, e)
        )


def main():
    """
    Main function to compile/upload Teensy code and log the Teensy outputs.
    """

    # Include state machine header files
    includeSMHeader("SetStateMachineTP.h", "StateMachineHeaders.h")

    # Read user configuration
    userConfig = getUserConfig("userInfo.in", "=")

    # Sync RPi system time
    syncRPiTime(userConfig)

    # Start background storage monitor (checks root filesystem by default)
    try:
        check_path = userConfig.get("Storage_Check_Path", "/")
        threshold_pct = float(userConfig.get("Storage_Fill_Threshold", 85))
        interval_sec = int(userConfig.get("Storage_Check_Interval_Sec", 600))
        cooldown_sec = int(userConfig.get("Storage_Notify_Cooldown_Sec", 86400))
        StorageMonitor.start_storage_monitor(
            user_config=userConfig,
            check_path=check_path,
            threshold_pct=threshold_pct,
            interval_sec=interval_sec,
            cooldown_sec=cooldown_sec,
        )
        print(
            "   ... Storage monitor started (path={}, threshold={}%, interval={}s)".format(
                check_path, threshold_pct, interval_sec
            )
        )
    except Exception as _e:
        # Non-fatal: continue even if storage monitor fails to start
        try:
            print("   ... Storage monitor could not be started: {}".format(_e))
        except Exception:
            pass

    # Experiment start timeT
    expStartTime = time.time()

    # Compile and upload Teensy code
    compileUploadTeensy(userConfig)

    # Check analog serial status [True: Enabled, False: Disabled]
    analogEnabled = False
    if userConfig["Analog"].lower() == "true":
        analogEnabled = True

    # Open Teensy main serial port
    ser = getSerialConnection("/dev/ttyACM0", "/dev/ttyACM1", 1000000)

    # Open analog serial port [if enabled]
    anSer = False
    if analogEnabled:
        anSer = getSerialConnection("/dev/serial0", "/dev/serial1", 1000000)

    # Setup GPIO and write HIGH to Teensy program pin
    setupGPIO(userConfig)

    # Sync Teensy time with NTPServer
    syncTimeNTP(ser, userConfig)

    addCrontab(userConfig)

    if not exitInst.exitStatus:
        # Print serial output and analog serial output [if enabled]
        printSerialOutput(ser, anSer, userConfig, analogEnabled, expStartTime)
        # getEverything(anSer, 120)
        # liveMonitor(anSer)

    removeCrontab()

    # Close serial and analog serial and clean GPIO
    ser.close()
    if analogEnabled:
        anSer.close()
    GPIO.cleanup()

    # Trigger transfer/backup pipeline after every run


if __name__ == "__main__":
    global exitInst
    exitInst = safeExit()
    main()
    print("   ... Program ended successfully.")
