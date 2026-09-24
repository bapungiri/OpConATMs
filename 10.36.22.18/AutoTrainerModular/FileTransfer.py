#!/usr/bin/python3

import subprocess                    # Linux shell commands inside Python
import time                          # Python time module
import os                            # OS module (path, ...)
import logging                       # Debugging tool
import base64                        # Enode-decode text
import threading                     # threading utility
import signal                        # Exit signal detection
import datetime                      # Datetime utility
import glob                          # File pattern search
import argparse                      # Input argument parser
import re                            # Regular expression
import gzip                          # Python compress file module
import netifaces                     # Get IP address
import random                        # Generate random numbers


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


def getIP():
    """Return RPi IP address.
    """

    return netifaces.ifaddresses('eth0')[netifaces.AF_INET][0]['addr']


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


def getUserConfig(fileName, splitterChar):
    """Function to read the user configuration file as a dictionary.
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


class FileTransfer(object):
    """ Transfer object. It will be expanded to include several protocols.
    """

    def __init__(self, protocol='rsync', host=None, sshU=None, sshP=None,
                 locRt=None, rmtRt=None, ext=None, logPath=None,
                 emptyDir=False, config=None, credFile=None,
                 alarmFile=None, keepPeriod=90000, userConfig=None,
                 audioConfig=None):
        """Initialize a transfer class object
        """

        self.protocol = protocol
        self.host = host
        self.sshU = sshU
        self.sshP = sshP
        self.locRt = locRt
        self.rmtRt = rmtRt
        self.ext = ext
        self.logPath = logPath
        self.emptyDir = emptyDir
        self.config = config
        self.credFile = credFile
        self.alarmFile = alarmFile
        self.keepPeriod = keepPeriod  # 25 hours
        self.userConfig = userConfig
        self.audioConfig = audioConfig
        self.sleepInterval = 5        # 5 sec
        self.rsyncT0 = time.time()

        # ssh connection control variables
        self.waintSSH = None

        # Initialize a dictionary to keep a list of directories
        self.dirH = dict()

        # Add output format to transfer extensions
        e = re.sub(r'[^\w]', '', self.config['Output_Format'].lower())
        self.ext.append(''.join(['*.', e]))

        # Transfer settings
        self.transferStart = None
        self.transferStop = None
        self.recordStart = None
        self.recordStop = None

        self.trfError = False

        # Dayligh saving setting
        # self.DSTInfo = self.getDSTInfo('DST.dat')

        self.runStatus = False

        self.readCred()

        self.setTransferSched()

        self.setConversionSetting()

        self.setTransferThread()

        if not os.path.exists(self.locRt):
            os.makedirs(self.locRt)

        self.createRemoteDir()

    def isConnected(self, dir=None):
        """Check remote connection before rsync or scp.
        """

        if self.waintSSH:
            if (time.time() - self.waintSSH) < 1200: # wait 20 minutes
                return False
            else:
                self.waintSSH = None

        try:
            S = ''.join([self.sshU, '@', self.host])
            cmd = ' '.join(['sshpass -p', self.sshP, 'ssh -o ConnectTimeout=10 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no', S, 'date'])
            subO, subE = self.runCmd(cmd)
            assert 'timed out'.encode() not in subE
            assert 'denied'.encode() not in subE
            return True
        except AssertionError as e:
            if dir:
                loggin.debug("No connection. Skip folder: " + d)
            self.waintSSH = time.time()
            return False

    def createRemoteDir(self, path=None):
        """Create remote directory.
        """

        if path:
            rmtRt = path
        else:
            rmtRt = self.rmtRt

        try:
            logging.debug('Creating remote directory. SSH USER@HOST')
            assert not self.trfError
            S = ''.join([self.sshU, '@', self.host])
            cmd = ' '.join(['sshpass -p', self.sshP, 'ssh -o ConnectTimeout=10 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no', S, 'mkdir -p', rmtRt])
            subO, subE = self.runCmd(cmd)
            assert 'timed out'.encode() not in subE
            assert 'denied'.encode() not in subE
        except AssertionError as e:
            self.trfError = True
            logging.debug('SSH connection timeout. Check your host and your SSH credentials.')
            logging.debug('Transfer is disabled due to SSH error. Only video conversion works if enabled.')
            return

    # def getDSTInfo(self, fileName):
    #     """
    #     Function to read DST data as a dictionary.
    #     """

    #     dic = {}
    #     with open(fileName) as File:
    #         for L in File:
    #             L = L.strip()
    #             S = L.split(',')
    #             (Year, Days) = [S[0].strip(), [S[1].strip(), S[2].strip()]]
    #             dic[Year] = Days
    #     return dic

    # def dstStatus(self, dt):
    #     """
    #     Function to check Daylight Saving status.
    #     """

    #     Y = str(dt.year)
    #     d1 = int(self.DSTInfo[Y][0])
    #     d2 = int(self.DSTInfo[Y][1])
    #     dst_start = datetime.datetime(dt.year, 3, d1, 2, 0)
    #     dst_start += datetime.timedelta(6 - dst_start.weekday())
    #     dst_end = datetime.datetime(dt.year, 11, d2, 2, 0)
    #     dst_end += datetime.timedelta(6 - dst_end.weekday())
    #     return dst_start <= dt < dst_end

    def getTimeDiffUTC(self):
        """Return local time difference with UTC considering daylight saving
        """

        TimeDiffUTC = -time.timezone
        #if self.dstStatus(datetime.datetime.now()):
        #    TimeDiffUTC += 3600

        return TimeDiffUTC

    def getTime(self):
        """Return epoch time in local time zone considering daylight saving
        """

        return (time.time() + self.getTimeDiffUTC())

    def isTransferTime(self):
        now = self.getTime() % 86400
        if self.trfOpt == 'u':
            for (start, stop) in zip(self.transferStartSec, self.transferStopSec):
                if now >= start and now < stop:
                    return True
            return False

        elif self.trfOpt == 't' or self.trfOpt == 'false':
            for (start, stop) in zip(self.recordStartSec, self.recordStopSec):
                if now >= start and now < stop:
                    return False
            return True

    def getTimeFormat(self):
        """
        Get the current time format in YYYY-MM-DD HH-MM-SS.
        """

        now = datetime.datetime.now()
        timeFormat = now.strftime('%Y-%m-%d-%H-%M-%S')
        return timeFormat

    def setTransferThread(self):
        """Create transfer thread.
        """

        self.transferEvent = threading.Event()
        self.transferThread = threading.Thread(name='TRNFThread', target=self.transfer, args=(self.transferEvent, ))
        self.transferThread.daemon = True
        self.transferThread.start()

    def isRunning(self):
        """Return True if transfer thread is running.
        """
        return (self.runStatus == True)

    def startTransfer(self):
        """Starting transfer process.
        """

        logging.debug("Transfer started: " + self.getTimeFormat())
        self.runStatus = True
        self.transferEvent.set()

    def stopTransfer(self):
        """ Stopping transfer process.
        It clears thread, shutdowns streaming server, and stops camera on port 2
        """

        logging.debug("Transfer stopped: " + self.getTimeFormat())
        self.runStatus = False
        self.transferEvent.clear()

    def generateCMD(self, d, delFlag=False):
        """Function to generate rsync transfer command.
        if delFlag=True, it deletes the folder after checksum
        """

        if self.protocol == 'rsync':
            cmd = ["cd", "".join([self.locRt, ";"])]

            cmd.append("sshpass")
            cmd.append("-p")
            cmd.append(self.sshP)

            cmd.append("rsync")
            cmd.append("-mar")
            cmd.append("-e \"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no\"")

            if delFlag:
                cmd.append("--remove-source-files")
                cmd.append("--checksum")

            cmd.append("--include")
            cmd.append("".join(["\"", d, "*/\""]))

            for e in self.ext:
                cmd.append("--include")
                cmd.append("".join(["\"", e, "\""]))

            cmd.append("--exclude")
            cmd.append("\"*\" \"$from\" \"$to\"")

            cmd.append("--log-file")
            cmd.append(self.logPath)

            cmd.append("".join([self.sshU, "@", self.host, ":",  self.rmtRt]))

            cmd = ' '.join(cmd)

            return cmd

    def generateRsyncCMD(self, localDir, logFile, delFlag=False):
        """Function to generate rsync transfer command for OpCon.
        if delFlag=True, it deletes the folder after checksum.
        """

        if self.userConfig['Add_Experiment_Dir'].lower() == 'true':
            remoteDir = os.path.join(self.userConfig['Storage_Root'], self.userConfig['Storage_Dir'].lstrip(os.sep),
                                     self.userConfig['Experiment_Name'])
        elif self.userConfig['Add_Experiment_Dir'].lower() == 'box':
            boxSub = ''.join(['Results-', self.userConfig['Box_Name'], '-', self.userConfig['Subject_Name']])
            remoteDir = os.path.join(self.userConfig['Storage_Root'], self.userConfig['Storage_Dir'].lstrip(os.sep), boxSub)
        else:
            remoteDir = os.path.join(self.userConfig['Storage_Root'], self.userConfig['Storage_Dir'].lstrip(os.sep))

        ipName = ''.join([self.config['Camera_Type'].lower().title(), '-', getIP().split('.')[3]])
        remoteDir = os.path.join(remoteDir, ipName)

        self.createRemoteDir(path=remoteDir)
        ext = [e.strip() for e in self.userConfig['Exclude_Exts'].split(";")]

        cmd = [""]
        cmd.append("sshpass")
        cmd.append("-p")
        cmd.append(self.sshP)

        cmd.append("rsync")
        cmd.append("-mar")
        cmd.append("-e \"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no\"")

        if delFlag:
            cmd.append("--remove-source-files")
            cmd.append("--checksum")

        for e in ext:
            cmd.append("--exclude")
            cmd.append("".join(["\"", e, "\""]))

        cmd.append("--exclude anTemp*")

        cmd.append("--log-file")
        cmd.append(logFile)

        cmd.append(localDir)

        cmd.append("".join([self.sshU, "@", self.host, ":",  remoteDir]))

        cmd = ' '.join(cmd)

        return cmd

    def fullPath(self, d, f=None):
        """Get full path of a folder.
        """

        if f:
            return (os.path.join(self.locRt, d, f))
        else:
            return (os.path.join(self.locRt, d))

    def runCmd(self, cmd, isShell=True):
        """Run subprocess command.
        """

        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subO, subE = proc.communicate()
        except Exception as e:
            logging.debug('* EXCEPTION HAPPENED.')
            logging.debug('* Failed running command with subprocess.')
            logging.debug('* Error : %s: %s \n' % (e.__class__, e))

        return subO, subE

    def numItems(self, d):
        """Returns number of items in a folder.
        """

        return (len(os.listdir(self.fullPath(d))))

    def getMTime(self, d):
        """Returns modification time for a folder.
        """

        return (os.path.getmtime(self.fullPath(d)))

    def empty(self, d):
        """Returns True if directory is empty.
        """

        return (not os.listdir(self.fullPath(d)))

    def readCred(self):
        """Read SSH credentials.
        """

        try:
            with gzip.open(self.credFile, 'rb') as F:
                dat = F.readlines()

            u = base64.b64decode(base64.b64decode(dat[0].strip())).decode()
            p = base64.b64decode(base64.b64decode(dat[1].strip())).decode()

            (self.sshU, self.sshP) = (u, p)

        except IOError:
            logging.debug('cred.in.gz file is missing. ')
            logging.debug('Transfer is disabled due to missing cred.in.gz. Only video conversion works if enabled.')
            self.trfError = True
            return

    def setTransferSched(self):
        """Set transfer schedule.
        """

        self.trfOpt = self.config['Transfer_Schedule'].lower()

        if self.trfOpt == 'u':
            self.transferStart = eval(self.config['Transfer_Start'])
            self.transferStop = eval(self.config['Transfer_Stop'])
            self.transferStartSec = [i[0]*3600+i[1]*60 for i in self.transferStart]
            self.transferStopSec = [i[0]*3600+i[1]*60 for i in self.transferStop]
            logging.debug("".join(["The transfer start times are: ", str(self.transferStart)]))
            logging.debug("".join(["The transfer stop  times are: ", str(self.transferStop)]))

        elif self.trfOpt == 't' or self.trfOpt == 'false':
            self.recordStart = list()
            self.recordStop = list()
            try:
                F = open(self.alarmFile, 'r').readlines()
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

            self.recordStartSec = [i[0]*3600+i[1]*60 for i in self.recordStart]
            self.recordStopSec = [i[0]*3600+i[1]*60 for i in self.recordStop]

            logging.debug("".join(["The transfer start times are outside: ", str(self.recordStart)]))
            logging.debug("".join(["The transfer stop  times are outside: ", str(self.recordStop)]))

        if self.trfOpt == 'false':
            self.trfError = True
            logging.debug("Transfer process is disabled by user. Only video conversion works if enabled.")

    def anyRawFile(self, d):
        """Returns True if there is any raw video file on RPi.
        """

        if os.path.exists(self.fullPath(d)):
            e = ''.join(['*.', self.config['Camera_Format'].lower()])
            return (len(glob.glob(self.fullPath(d, e))) != 0)
        else:
            return False

    def setConversionSetting(self):
        """Set video conversion settings
        """
        self.conFormat = self.config['Output_Format'].lower()
        self.conSize = self.config['Output_Size'].lower()

    def generateConvCMD(self, f):
        """Generate conversion shell command.
        """

        cmd = "ffmpeg " + "-y " + "-r " + self.config['Camera_FPS'] + " -i " + f + " "

        if self.conSize == 'o':
            cmd += " -vcodec copy "

        fout = f.replace(self.config['Camera_Format'].lower(), self.conFormat)
        cmd += fout

        return (cmd, fout)

    def safeDelete(self, inpF, outF):
        """Safely delete a converted video file.
        """

        if os.path.exists(outF):
            if os.path.getsize(outF):
                if os.path.exists(inpF):
                    try:
                        os.remove(inpF)
                    except IOError:
                        logging.debug('Could not delete:' + inpF)

    def convertVideo(self, d, event):
        """Converts video files
        """

        if event.isSet():
            e = ''.join(['*.', self.config['Camera_Format'].lower()])
            files = sorted(glob.glob(self.fullPath(d, e)))

            for inpF in files:
                if not event.isSet():
                    logging.debug('Training session started. Ending video conversion in folder: ' + d)
                    return
                if os.path.exists(inpF):
                    try:
                        if ((time.time() - os.path.getmtime(inpF)) > 60) and os.path.getsize(inpF):
                            (cmd, outF) = self.generateConvCMD(inpF)
                            logging.debug("Converting video: " + inpF)
                            time.sleep(0.1)
                            self.runCmd(cmd)
                            time.sleep(0.1)
                            self.safeDelete(inpF, outF)
                        elif (not os.path.getsize(inpF)) and ((time.time() - os.path.getmtime(inpF)) > 300):
                            fileL = [inpF.replace(e[1:], i) for i in [e[1:], '.events', '.frames']]
                            for file in fileL:
                                if os.path.exists(file):
                                    try:
                                        logging.debug('Delete zero-size video: ' + file)
                                        os.remove(file)
                                    except IOError:
                                        logging.debug('Cannot delete zero-size video: ' + file)

                    except IOError:
                            logging.debug('* Issue with: ' + inpF)

    def transfer(self, event):
        """Transfer function.
        """

        while True:
            if event.isSet():

                # Sync OpCon and Audio Recording folder if requested
                if 'Rsync_OpCon' in self.userConfig:
                    if (self.userConfig['Rsync_OpCon'].lower() == 'true') and ((time.time() - self.rsyncT0) > int(self.userConfig['Rsync_Freq_Sec'])):
                        if self.isConnected():
                            self.rsyncT0 = time.time()
                            if self.config['Camera_Type'].lower() == 'master':
                                cmd = self.generateRsyncCMD(os.path.realpath('').rstrip('/')+'/*', '/home/pi/opcon_rsync.log')
                                logging.debug("Transfer OpCon Folder: " + os.path.basename(os.path.realpath('')))
                                self.runCmd(cmd)

                            if 'Run_Microphone' in self.userConfig:
                                if self.userConfig['Run_Microphone'].lower() == 'true':
                                    if self.config['RPi_IP'] == self.audioConfig['Microphone_RPi_IP']:
                                        cmd = self.generateRsyncCMD(self.audioConfig['RPi_Audio_Dir'], '/home/pi/audio_rsync.log', delFlag=True)  # Change delFlag to True ## User Option
                                        logging.debug("Transfer Audio Recording Folder: " + self.audioConfig['RPi_Audio_Dir'])
                                        self.runCmd(cmd)

                # Get a list of directory
                try:
                    dirList = [d for d in os.listdir(self.locRt) if (os.path.isdir(self.fullPath(d)) and d[0] != '.')]
                    dirList = sorted(dirList)
                except IOError:
                    logging.debug("Issue with path: " + self.locRt)
                    time.sleep(1)
                    continue

                for d in dirList:

                    if self.config['Convert_Video'].lower() == 'true':
                        if self.anyRawFile(d):
                            self.convertVideo(d, event)
                            time.sleep(65)

                    # Do not transfer if disabled or there is no connection
                    if self.trfError or not self.isConnected():
                        # logging.debug("Transfer is disabled.")
                        continue

                    # Remove old directory if it is empty
                    if 'Sent' in d:
                        if self.empty(d):
                            os.rmdir(self.fullPath(d))
                        else:
                            new_d = d.split('-Sent')[0]
                            os.rename(self.fullPath(d), self.fullPath(new_d))
                        continue

                    # The folder is there, add --remove-source-files flag
                    if ((d in self.dirH) and (self.numItems(d) == self.dirH[d][1])):
                        if (time.time() - self.dirH[d][0]) > self.keepPeriod:
                            cmd = self.generateCMD(d, delFlag=True)
                            logging.debug("Transfer [delete]: " + d)
                            self.runCmd(cmd)
                            if self.empty(d):
                                new_d = ''.join([d, '-Sent'])
                                os.rename(self.fullPath(d), self.fullPath(new_d))
                                del self.dirH[d]
                        continue

                    # This is a new folder or content changed, no --remove-source-files flag
                    if ((((d not in self.dirH) and ('Sent' not in d)) or ((d in self.dirH) and (self.numItems(d) != self.dirH[d][1]))) and (time.time() - self.getMTime(d) > 60)):
                        self.dirH[d] = [self.getMTime(d), self.numItems(d)]
                        cmd = self.generateCMD(d)
                        logging.debug("Transfer [keepIt]: " + d)
                        self.runCmd(cmd)
                        continue

                # logging.debug("Sleep for " + str(self.sleepInterval) + " seconds")
                self.sleepInterval = random.randint(10,15)  # avoid transfer at the same time
                time.sleep(self.sleepInterval)

            else:
                time.sleep(0.5)


if __name__ == "__main__":

    # Parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", help='Camera Setting File Name', type=str)
    parser.add_argument("-d", "--debug", help='Logging debug output option [1: Log File, 0:Screen]', default=1, type=int)
    parser.add_argument("-v", "--verbose", help='Verbose state [0 | 1]', default=1, type=int)
    args = parser.parse_args()

    # Setup exit signal
    global exitInst
    exitInst = safeExit()

    removeFDir("/home/pi/transfer.log")
    removeFDir("/home/pi/opcon_rsync.log")

    # Code debugging setting
    if args.debug:
        logging.basicConfig(filename='/home/pi/transfer.log', level=logging.DEBUG, format='(%(threadName)-9s) %(message)s',)
    else:
        logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-9s) %(message)s',)   # or logging.INFO

    # Create transfer configuration dictionary
    trfConfig = getUserConfig(args.file, '=')

    # Create user and audio configuration dictionary
    userConfig = getUserConfig('userInfo.in', '=')
    if 'Run_Microphone' in userConfig:
        audioConfig = getUserConfig('audioInfo.in', '=')
    else:
        audioConfig = None

    logging.debug('Transfer code started on [' + trfConfig['Camera_Type'] + ']' + '[' + trfConfig['RPi_IP'] + ']: ' + getTimeFormat(withTime=True, dash=True))

    # Removing old transfer log file
    removeFDir(trfConfig['Log_File_Dir'])

    # Create transfer object
    trfObj = FileTransfer(protocol=trfConfig['Protocol'].lower(),
                          host=trfConfig['Storage_Host'],
                          locRt=trfConfig['RPi_Video_Dir'],
                          rmtRt=os.path.join(trfConfig['Storage_Root'], trfConfig['Storage_Video_Dir'].lstrip(os.sep)),
                          ext=[e.strip() for e in trfConfig['Transfer_Ext'].split(";")],
                          logPath=trfConfig['Log_File_Dir'],
                          config=trfConfig,
                          credFile='cred.in.gz',
                          alarmFile=trfConfig['Teensy_Alarm_File'],
                          keepPeriod=86400,
                          userConfig=userConfig,
                          audioConfig=audioConfig)

    # Loop forever
    try:
        while not exitInst.exitStatus:
            if trfObj.isRunning():
                if not trfObj.isTransferTime():
                    trfObj.stopTransfer()
            elif trfObj.isTransferTime():
                trfObj.startTransfer()

            time.sleep(0.5)

    except KeyboardInterrupt:
        logging.debug("User interrupted the program.")

    except Exception as e:
        logging.debug('* EXCEPTION HAPPENED.')
        logging.debug('* Error : %s: %s \n' % (e.__class__, e))

    finally:
        trfObj.stopTransfer()
        logging.debug('Program ended with exit signal = ' + str(exitInst.exitStatus))
