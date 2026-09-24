#!/usr/bin/python

import serial            # Python module to communicate with the Teensy serial
import time              # Python time module
import os                # Python operating system module (mkdir, rm, ...)
import datetime          # Python date and time module for time purpose
import collections       # Python advanced data type [for analog buffer]
import copy              # Python copy circular buffer in collections
import subprocess        # Python subprocess to execute bash commands
import ntplib            # Python Network Time Protocol (NTP)
import smtplib           # Python SMTP for sending email to users
import base64            # Python base64 data encodings
import email.mime.text   # Python Multipurpose Internet Mail Extensions (MIME)
import netifaces         # Python module to find device IP address
import random            # Python random number module
import RPi.GPIO as GPIO  # Python RPi GPIO utility
import re                # Python regular expression module
import signal            # Python signal module [e.g., exit signal]
from PIL import Image, ImageDraw, ImageFont  # Python Image module [change background]


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
    timeFormat = now.strftime('%Y-%m-%d-%H-%M-%S')
    return timeFormat


def writeLogFile(fileName, msgList):
    """
    Function to write lines to user log file.
    """

    msgFile = open(fileName, 'a')
    msgFile.write('--------------- \n')
    msgFile.write(getTimeFormat() + '\n')
    for item in msgList:
        if '\n' in item:
            msgFile.write(item)
        else:
            msgFile.write(item + '\n')
    msgFile.close()


def syncRPiTime(userConfig):
    """
    Function to sync system time with NTP.
    """

    try:
        client = ntplib.NTPClient()
        response = client.request(userConfig['NTPServer'], timeout=5)
        os.system('echo 3 | sudo date ' + time.strftime('%m%d%H%M%Y.%S', time.localtime(response.tx_time)) + '>/dev/null 2>&1')
        print('   ... RPi Date & Time Synced with ' + userConfig['NTPServer'] + ': ' + getTimeFormat())
    except Exception as e:
        print('   ... * EXCEPTION HAPPENED.')
        print('   ... * System time sync with NTP server failed.')
        print('   ... * Check network connection.')
        print('   ... * Error : %s: %s \n' % (e.__class__, e))
        exit('   ... * Exiting the program.')


def backupFile(fileName):
    """
    Function to backup a file. New name: current name + current date/time ## TBU
    """

    if os.path.exists(fileName):
        fileNameOnly, fileExtension = os.path.splitext(fileName)
        now = datetime.datetime.now()
        newFileName = ''.join([fileNameOnly, ' ',
                               now.strftime('%Y-%m-%d %H-%M-%S'),
                               fileExtension])
        subprocess.call(['mv', fileName, newFileName])
        print('   ... File ' + fileName + ' backed up.')
    else:
        print('   ... File ' + fileName + ' created.')


def createInitialFile(fileName, fileStatus):
    """
    Function to create an initial file.
    """
    f = open(fileName, fileStatus)
    f.close()


def getUserConfig(fileName, splitterChar):
    """
    Function to read the user configuration file as a directory.
    """

    userConfig = {}
    with open(fileName) as configFile:
        for eachLine in configFile:
            if '=' in eachLine:
                (settingName, settingValue) = eachLine.split(splitterChar)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                userConfig[settingName] = settingValue
    return userConfig


def compileUploadTeensy(userConfig):
    """
    Function to compile and upload Teensy code using Python subprocess module
    """

    if userConfig['Reset_Teensy_Build'].lower() == 'true':
        if os.path.exists('/home/pi/build/'):
            subprocess.call(['rm', '-rf', '/home/pi/build/'])

    if not os.path.exists('/home/pi/build/'):
        print('   ... Creating a new build directory.')
        subprocess.call(['mkdir', '/home/pi/build/'])

    print('   ... Killing the previous Teensy process if running.')
    subprocess.call(['pkill', 'teensy'])

    try:
        # Run bash script without showing Teensy graphical window by xvfb-run
        print('   ... Compiling and uploading the *.ino file.')
        subClient = subprocess.Popen("xvfb-run /home/pi/ArduinoATM/arduino-1.8.19/arduino \
                                     --board teensy:avr:teensy41 --pref \
                                     build.path=/home/pi/build/ \
                                     --port '/dev/ttyACM0' \
                                     --upload *.ino",
                                     shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

        subOutput, subError = subClient.communicate()

        if 'error' in subOutput:
            raise Exception('Error in uploading Teensy code.')

        print('   ... Program uploaded to Teensy board successfully.')

    except Exception as e:
        print('   ... * EXCEPTION HAPPENED.')
        print('   ... * Teensy code failed compilation or upload processes.')
        print('   ... * Check Teensy code and serial port & run the program.')
        print('   ... * Error : %s: %s \n' % (e.__class__, e))
        exit('   ... * Exiting the program.')

    finally:
        print('   ... Arduino compiler output:')
        print('   ... ========================')
        for line in subOutput.splitlines():
            print(''.join(['   ... ', line]))
        print('   ... ========================')


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
            print(' ... Serial port: '+portName+' ')
            return True
        except:
            return False

    timeRecordSerial = time.time()

    while True:
        if portIsOpen(port0):
            return port0
        if portIsOpen(port1):
            return port1

        if (time.time() - timeRecordSerial > 10):
            print('   ... * EXCEPTION HAPPENED.')
            print('   ... * Serial ports '+port0+' , '+port1+' are not open.')
            print('   ... * Try < dmesg | grep tty* > in Linux shell.')
            print('   ... * Check serial and USB connections.')
            exit('   ... * Error: exiting the program.')

        time.sleep(1.0/10000.0)


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
        timeout=0
    )

    return ser


def checkSerialConnection(ser):
    """
    Function to check a serial connection.
    """

    if not ser.isOpen():
        print('   ... The ' + ser.port + ' is NOT open. Re-submit the job.')
        return False
    else:
        print('   ... The serial port ' + ser.port + ' is open and ready.')
        return True


def getDSTInfo(fileName):
    """
    Function to read DST data as a dictionary.
    """

    DSTInfo = {}
    with open(fileName) as File:
        for L in File:
            L = L.strip()
            S = L.split(',')
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
    #DSTInfo = getDSTInfo('DST.dat')
    #if dstStatus(datetime.datetime.now(), DSTInfo):
    #    TimeDiffUTC += 3600

    # Get the time from NTPServer
    try:
        client = ntplib.NTPClient()
        response = client.request(userConfig['NTPServer'], timeout=5)
        timeT = 'T' + str(response.tx_time + TimeDiffUTC)
        ser.write(timeT)
        if msgFileN:
            msgList = ['Info: syncTimeNTP', 'RPi Time: '+getTimeFormat(),
                       'NTP Time: '+timeT.replace('T', ''),
                       'NTP to Local: '+time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(response.tx_time)))]
            writeLogFile(msgFileN, msgList)
        else:
            print('   ... Teensy date and time synced with ' + userConfig['NTPServer'])

    except Exception as e:
        if msgFileN:
            msgList = ['Error:',
                       'EXCEPTION HAPPENED.',
                       'The program could not sync Teensy time with NTP time server.',
                       'Check the internet connection and re-run the program.',
                       'Error : %s: %s \n' % (e.__class__, e)]
            writeLogFile(msgFileN, msgList)
        else:
            print('   ... * EXCEPTION HAPPENED.')
            print('   ... * The program could not sync Teensy time with NTP time server.')
            print('   ... * Check the internet connection and re-run the program.')
            print('   ... * Error : %s: %s \n' % (e.__class__, e))
            exitInst.exitStatus = True
            return


def sendEmail(errorMessage, userConfig, msgFileN, emailSubject=None):
    """
    Function to send customized emails to users.
    """

    if userConfig['Enable_Email'].lower() == 'true':
        recipientName = userConfig['Name']
        recipientEmail = userConfig['Email']
        emailUser = userConfig['WD_Email']

        tmpCred = userConfig['WD_Pass'].split('|||')
        for i in range(int(tmpCred[0])):
            tmpCred[1] = base64.b64decode(tmpCred[1])
        emailPass = tmpCred[1]

        ipAddress = netifaces.ifaddresses('eth0')[netifaces.AF_INET][0]['addr']

        sent_from = emailUser
        to = [recipientEmail]

        if emailSubject is None:
            subject = 'Issue with experiment in box: ' + userConfig['Box_Name']
        else:
            subject = emailSubject + ' in box: ' + userConfig['Box_Name']

        body = ''.join(['Hello ', recipientName, ',\n\n',
                        'There is an issue with your experiment.\n\n',
                        'The error message:\n\n', errorMessage, '\n\n',
                        'Please check your box as soon as possible.\n\n',
                        'Date and Time: ', getTimeFormat(), '\n\n',
                        'The IP address: ', ipAddress, '\n\n',
                        '-RPi Watchdog'])

        try:
            msg = email.mime.text.MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = emailUser
            msg['To'] = recipientEmail

            smtpAddress = userConfig['WD_SMTP'].lower()
            smtpPort = int(userConfig['WD_SMTP_Port'])
            if userConfig['WD_SSL'].lower() == 'true':
                s = smtplib.SMTP_SSL(smtpAddress, smtpPort)
            else:
                s = smtplib.SMTP(smtpAddress, smtpPort)

            s.ehlo()
            s.login(emailUser, emailPass)
            s.sendmail(emailUser, recipientEmail, msg.as_string())
            s.close()

            print('   ... An email sent to: ' + recipientName)

        except Exception as e:
            msgList = ['Error:',
                       '       Error happened in sending email.',
                       '       Email authentication failed.',
                       '       Error : %s: %s' % (e.__class__, e)]
            writeLogFile(msgFileN, msgList)


def getAnalogDirPath(userConfig):
    """
    Function to get analog folder path.
    """

    now = datetime.datetime.now()
    analogFolderDateName = now.strftime('%Y-%m-%d')
    analogDirPath = ''.join(['Analog-', userConfig['Subject_Name'], '/', analogFolderDateName])

    if not os.path.exists(analogDirPath):
        os.makedirs(analogDirPath)

    return analogDirPath


def getAnalogTempFileName(userConfig):
    """
    Function to get temporary file name for analog files
    """

    tempName = ''.join([getAnalogDirPath(userConfig), '/anTemp.', str(int(time.time()))])

    return tempName


def checkDailyWater(dailyWater, userConfig, msgFileN):
    """
    Function to check daily water and to send daily emails to users.
    """

    if dailyWater > 0:

        dailyWaterQuota = int(userConfig['Daily_Water'])
        minWaterPercentage = int(userConfig['Water_Minimum'].replace('%', ''))
        minWater = int(minWaterPercentage*1.0/100*dailyWaterQuota)

        if dailyWater < minWater:
            emailSubject = 'Low daily water consumption'
            emailText = ''.join(['Your subject consumed ',
                                 str(dailyWater), ' pulses of water.',
                                 ' It is less than ',
                                 str(minWaterPercentage),
                                 '% of daily water quota of ',
                                 str(dailyWaterQuota),
                                 ' pulses'])
            time.sleep(1*random.random())
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
            msgList = ['Error:',
                       '       Error in analog file name.',
                       '       Queue did not work.',
                       '       Modify analog saving.',
                       F1,
                       '       anFileName:',
                       F2]
            writeLogFile(msgFileN, msgList)


def elapsedTime(D, T, option='S'):
    """
    Function to return elapsed time from a datetime object
    """

    cases = {'S': (T-D).seconds % 60,
             'M': ((T-D).seconds % 3600) // 60,
             'H': (T-D).days * 24 + (T-D).seconds // 3600}

    return cases[option]


def changeOutputFileN(D, FN, Dic):
    """
    Function to change the output file name.
    """

    if Dic['Output_Name_Freq'].lower() != 'false':

        H = int((Dic['Output_Name_Freq'].lower()).replace('hr', ''))

        T = datetime.datetime.now()

        if elapsedTime(D, T, 'H') >= H:
            FN = ''.join([Dic['Subject_Name'], '-', getTimeFormat(), '.dat'])
            D = T

    return [D, FN]


def setupGPIO(userConfig):
    """
    Function to setup GPIO.
    """

    # Keep Teensy Reset & Program pins HIGH
    if 'GPIO_Pin_Type' in userConfig:
        print('   ... Writing GPIO.HIGH to Teensy reset and program pins')
        teensyProgPin = int(userConfig['Program_Pin'])
        if userConfig['GPIO_Pin_Type'].lower() == 'bcm':
            GPIO.setmode(GPIO.BCM)
        elif userConfig['GPIO_Pin_Type'].lower() == 'board':
            GPIO.setmode(GPIO.BOARD)
        GPIO.setup(teensyProgPin, GPIO.OUT)
        GPIO.output(teensyProgPin, GPIO.HIGH)


def includeSMHeader(srcF, destF):
    """
    Function to include state machine header files.
    """

    with open(srcF, 'r') as f:
        dat = f.readlines()
    d = ''.join(dat)
    smList = re.findall(r'SM{1}\((\w+)\)', d)

    dat = ['/*\n',
           '  Include the header file for all state machines.\n',
           '*/\n',
           '\n',
           '#ifndef _AllStateMachineHeaders_h\n',
           '#define _AllStateMachineHeaders_h\n',
           '\n',
           '//-->[0]\n',
           '//<--[0]\n',
           '\n',
           '#endif\n']

    with open(destF, 'w') as f:
        for i, L in enumerate(dat):
            if '//-->[0]' in L:
                for sm in smList:
                    L = ''.join([L, '#include "StateMachines/', sm, 'Machine.h"\n'])
                dat[i] = L
                f.write(''.join(dat))
                break

    # Check 'SpecificFunctions.h' in StateMachines folder
    if not os.path.exists('StateMachines/SpecificFunctions.h'):
        dat = ['/*\n',
               '  This file defines specific functions shared between state machines.\n',
               '*/\n',
               '\n',
               '#ifndef _SpecificFunctions_h\n',
               '#define _SpecificFunctions_h\n',
               '\n',
               '\n',
               '\n',
               '#endif\n']

        with open('StateMachines/SpecificFunctions.h', 'w') as f:
            f.write(''.join(dat))


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
    imgTemplate = Image.new('RGB', (deskW, deskH), color=(64, 48, 83))

    fontSpec = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 25)
    drwSpec = ImageDraw.Draw(imgTemplate)

    # Text to be written
    S1 = ''.join(['User: ', userConfig['Name']])
    S2 = ''.join(['IP: ', userConfig['RPi_IP']])
    S3 = ''.join(['Box: ', userConfig['Box_Name']])
    S4 = ''.join(['Subject: ', userConfig['Subject_Name']])

    # Add text to image
    for i in range(4):
        for j in range(5):
            x = 200 + i*475
            y = 70 + j*200
            printText((x, y), (x, y+30), (x, y+60), (x, y+90), S1, S2, S3, S4, fontSpec, drwSpec)

    # Save image to Desktop
    imgTemplate.save('/home/pi/backImage.jpg')
    subprocess.call(["pcmanfm", '--set-wallpaper=/home/pi/backImage.jpg'],
                    env=dict(os.environ, DISPLAY=":0.0", XAUTHORITY="/home/pi/.Xauthority"))
    print('   ... Desktop background changed.')

def sendSerialInput(ser, userConfig):

    paramsFile = getParamsFilename(userConfig) 
    with open(paramsFile, 'r') as f: 
        lines = f.read().splitlines()
        last_line = lines[-1]
    last_line = list(last_line.split(","))[1:]

    # Write the last line to the serial port 
    for i in last_line:
        ser.write(i)
    ser.write('-1')
    return 


def getParamsFilename(userConfig):
    return ''.join([userConfig['Subject_Name'], '.params'])

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
        logFile = open('log.out', 'a')
        logFile.write('   ... SubmitComplete\n')
        logFile.close()

        # Open output file and message log file initially
        outputFileN = ''.join([userConfig['Subject_Name'], '-', getTimeFormat(), '.dat'])
        msgFileN = ''.join([userConfig['Subject_Name'], '-', getTimeFormat(), '.log'])
        paramFileN = getParamsFilename(userConfig)
        createInitialFile(outputFileN, 'a')
        createInitialFile(msgFileN, 'a')

        # Log the current date
        currentDate = datetime.datetime.now()

        totalDataRead = ''

        if analogEnabled:
            totalAnalogRead = ''
            if not os.path.exists(''.join(['Analog-', userConfig['Subject_Name']])):
                os.makedirs(''.join(['Analog-', userConfig['Subject_Name']]))
            anBufferSize = int(userConfig['Analog_Buffer'])
            anBuffer = collections.deque(maxlen=anBufferSize)
            anInitialWriteStatus = False
            anWriteStatus = False
            anTempFileName = ''
            anFileName = ''
            anFileNamePins = ''
            anFileNameBuffer = collections.deque(maxlen=10)
            anTempFileNameBuffer = collections.deque(maxlen=10)

        # Reset daily Water
        dailyWater = 0

        # Serial time out check
        lastTimeSerialCheck = int(time.time())
        serialTimeOutCheck = int(userConfig['Serial_TimeOut'])

        # Teensy time sync
        lastTimeSync = int(time.time())
        teensyTimeSyncFreq = int(float((userConfig['TimeSyncFreq'].lower()).replace('hr', '')) * 3600)

        while True:

            # This helps in optimization of CPU usage
            time.sleep(1.0/100000.0)  # should be smaller than the 1kHz

            # Check available data in serial and read them
            try:
                dataToRead = ser.inWaiting()
                dataRead = ser.read(dataToRead)

            except KeyboardInterrupt:
                raise Exception('Teensy Serial Port User Interrupt Error')
            except Exception as e:
                # Send an email if serial is not available
                sendEmail('The serial port is not open.', userConfig, msgFileN)
                raise Exception('Teensy Serial Port Not Available Error')

            # Join data until all lines end in \n
            totalDataRead = ''.join([totalDataRead, dataRead])

            # True indicates all lines ends in \n
            completeLine = True

            # Check if all lines end in \n
            for line in totalDataRead.splitlines(True):
                if '\n' not in line:
                    completeLine = False
                    break

            # Open output file to append text
            f = open(outputFileN, 'a')

            if len(totalDataRead) == 0:
                if (int(time.time())-lastTimeSerialCheck) > serialTimeOutCheck:
                    msgList = ['Error:', 'Teensy serial port is idle']
                    writeLogFile(msgFileN, msgList)

                    # Send an email if serial is not available
                    sendEmail('Teensy serial port is idle.', userConfig, msgFileN)

                    lastTimeSerialCheck = int(time.time())
                    # raise Exception('Teensy Serial Port IDLE Error')
            else:
                lastTimeSerialCheck = int(time.time())

            # If all lines end in \n, then write to output file or analog file
            if completeLine and len(totalDataRead) > 1:
                for eachLine in totalDataRead.splitlines(True):
                    words = eachLine.split(',')

                    # This tag indicates (I)nformation from Teensy
                    if words[0] == 'I':
                        msgList = ['Info:', eachLine[2:]]
                        writeLogFile(msgFileN, msgList)

                    # This tag indicates (E)rror from Teensy
                    elif words[0] == 'E':
                        msgList = ['Error:', eachLine[2:]]
                        writeLogFile(msgFileN, msgList)

                    # This tag indicates daily water report from Teensy
                    elif words[0] == 'D':
                        dailyWater = int(words[1])

                    # This tag indicates pin numbers in analog reading
                    elif words[0] == 'P':
                        if analogEnabled:
                            anFileNamePins = '.' + '.'.join([words[i] for i in range(1, len(words))]).rstrip()

                    # This tag indicates to write to the session parameter file 
                    elif words[0] == 'G':
                        msgList = eachLine[2:]
                        with open(paramFileN, 'a') as p:
                            p.write(getTimeFormat() + ",")
                            for item in msgList:
                                p.write(item.strip())
                            p.write("\n")
                        p.close()
                        

                    # This tag indicates to send data from the session parameter file 
                    elif words[0] == 'S':
                        sendSerialInput(ser, userConfig)

                    # Otherwise, it is a regular output, just append to output
                    else:
                        if len(words) != 8:
                            msgList = ['Error:',
                                       '       Error in reading serial.',
                                       '       Modify serial read.',
                                       eachLine]
                            writeLogFile(msgFileN, msgList)
                        else:
                            if analogEnabled:
                                # This tag indicates start of analog saving
                                if words[0] == '99':
                                        if anFileNamePins:
                                            analogDirPath = getAnalogDirPath(userConfig)
                                            anFileName = analogDirPath + '/an.' + '.'.join([words[i] for i in reversed(range(4, 6))]).rstrip()
                                            anFileName = ''.join([anFileName, anFileNamePins])
                                        else:
                                            msgList = ['Error:',
                                                       '       Error in analog file name.',
                                                       '       Analog pin file names missing.',
                                                       '       Modify analog saving.']
                                            writeLogFile(msgFileN, msgList)

                                # This tag indicates end of analog saving
                                if words[0] == '98':
                                    if anFileName:
                                        anFileNameBuffer.append(anFileName)
                                    else:
                                        msgList = ['Error:',
                                                   '       Error in analog file name.',
                                                   '       Real analog file name missing.',
                                                   '       Modify analog saving.']
                                        writeLogFile(msgFileN, msgList)

                            f.write(eachLine)

                # Reset accumulated string
                totalDataRead = ''

            if analogEnabled:
                # Check available data in analog USB serial and read them
                try:
                    anDataToRead = anSer.inWaiting()
                    anDataRead = anSer.read(anDataToRead)
                except KeyboardInterrupt:
                    raise Exception('Analog USB Port User Interrupt Error')
                except Exception as e:
                    # Send an email if serial is not available
                    sendEmail('The analog USB port is not open.', userConfig, msgFileN)
                    raise Exception('Analog USB Port Not Available Error')

                totalAnalogRead = ''.join([totalAnalogRead, anDataRead])

                anCompleteLine = True

                for line in totalAnalogRead.splitlines(True):
                    if '\n' not in line:
                        anCompleteLine = False
                        break

                if anCompleteLine and len(totalAnalogRead) > 1:
                    for eachLine in totalAnalogRead.splitlines(True):
                        words = eachLine.split(',')

                        # This tag indicates start of analog file saving
                        if words[0] == 'V':
                            anTempFileName = getAnalogTempFileName(userConfig)
                            anFile = open(anTempFileName, 'a')
                            anInitialWriteStatus = True

                        # This tag indicates each analog read for all channels
                        elif words[0] == 'A':
                            anLineToWrite = ','.join([words[i] for i in range(1, len(words))])

                            # Sending single value
                            if anWriteStatus:
                                if os.path.exists(anTempFileName):
                                    anFile.write(anLineToWrite)

                            anBuffer.append(anLineToWrite)

                            # Sending initial analog buffer
                            if anInitialWriteStatus:
                                anBufferTemp = copy.deepcopy(anBuffer)
                                if os.path.exists(anTempFileName):
                                    for i in range(anBufferTemp.maxlen):
                                        anFile.write(anBufferTemp.popleft())
                                anInitialWriteStatus = False
                                anWriteStatus = True

                        # This tag indicates end of analog file saving
                        elif words[0] == 'W':
                            anWriteStatus = False
                            anInitialWriteStatus = False
                            if os.path.exists(anTempFileName):
                                anFile.close()
                                anTempFileNameBuffer.append(anTempFileName)
                            else:
                                msgList = ['Error:',
                                           '       Error in analog file name.',
                                           '       Temporary analog file missig.',
                                           '       Modify analog saving.']
                                writeLogFile(msgFileN, msgList)

                        # This tag indicates (I)nformation from Teensy
                        elif words[0] == 'I':
                            msgList = ['Info:', eachLine[2:]]
                            writeLogFile(msgFileN, msgList)

                        # This tag indicates (E)rror from Teensy
                        elif words[0] == 'E':
                            msgList = ['Error:', eachLine[2:]]
                            writeLogFile(msgFileN, msgList)

                        # Otherwise, there is an error, report it
                        else:
                            msgList = ['Error:',
                                       '       Error in reading analog.',
                                       '       Check analog output.',
                                       '       Modify serial read.',
                                       eachLine]
                            writeLogFile(msgFileN, msgList)

                    # Reset accumulated string
                    totalAnalogRead = ''

            # close the fild until next read [for tail -f output]
            f.close()

            # Change temporary analog file names
            if analogEnabled:
                renameQueueFiles(anTempFileNameBuffer, anFileNameBuffer, msgFileN)

            # Check daily water and report it to user
            dailyWater = checkDailyWater(dailyWater, userConfig, msgFileN)

            # Check Teensy time synced
            if ((int(time.time())-lastTimeSync) > teensyTimeSyncFreq):
                syncTimeNTP(ser, userConfig, msgFileN)
                lastTimeSync = int(time.time())

            # Check output [result] file name and changed it daily
            if 'Output_Name_Freq' in userConfig:
                [currentDate, outputFileN] = changeOutputFileN(currentDate, outputFileN, userConfig)

            # Check exit signal
            if exitInst.exitStatus:
                raise Exception('An exit signal received by OS.')

    except KeyboardInterrupt:
        print('   ... Program ended: User interrupted the program.')
        f.close()

    except Exception as e:
        print('   ... Program ended: Error occurred.')
        print('   ... Error : %s: %s \n' % (e.__class__, e))
        #f.close()

    finally:
        print('   ... The current time: ' + getTimeFormat())
        msgList = ['Program ended with exit signal = ' + str(exitInst.exitStatus)]
        writeLogFile(msgFileN, msgList)


def main():
    """
    Main function to compile/upload Teensy code and log the Teensy outputs.
    """

    # Include state machine header files
    includeSMHeader('SetStateMachineTP.h', 'StateMachineHeaders.h')

    # Read user configuration
    userConfig = getUserConfig('userInfo.in', '=')

    # Sync RPi system time
    syncRPiTime(userConfig)

    # Experiment start timeT
    expStartTime = time.time()

    # Compile and upload Teensy code
    compileUploadTeensy(userConfig)

    # Check analog serial status [True: Enabled, False: Disabled]
    analogEnabled = False
    if userConfig['Analog'].lower() == 'true':
        analogEnabled = True

    # Open Teensy main serial port
    ser = getSerialConnection('/dev/ttyACM0', '/dev/ttyACM1', 1000000)

    # Open analog serial port [if enabled]
    anSer = False
    if analogEnabled:
        anSer = getSerialConnection('/dev/serial0', '/dev/serial1', 1000000)

    # Setup GPIO and write HIGH to Teensy program pin
    setupGPIO(userConfig)

    # Sync Teensy time with NTPServer
    syncTimeNTP(ser, userConfig)

    paramsFileName = getParamsFilename(userConfig)

    if not os.path.exists(paramsFileName):
        createInitialFile(paramsFileName, 'a')
        print('   ... Session parameter file created.')
    else:
        print('   ... Session parameter file exists.')

    if not exitInst.exitStatus:
        # Print serial output and analog serial output [if enabled]
        printSerialOutput(ser, anSer, userConfig, analogEnabled, expStartTime)

    # Close serial and analog serial and clean GPIO
    ser.close()
    if analogEnabled:
        anSer.close()
    GPIO.cleanup()


if __name__ == "__main__":
    global exitInst
    exitInst = safeExit()
    main()
    print('   ... Program ended successfully.')
