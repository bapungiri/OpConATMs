#!/usr/bin/python

import os  # Python operating system module (mkdir, rm, ...)
import posixpath  # POSIX-safe path joining for remote hosts
import glob  # Python Unix style pathname pattern expansion
import paramiko  # Python implementation of the SSHv2 protocol
import base64  # Python base64 data encodings
import time  # Python time module
import sys  # Python system module
import gzip  # Python compress file module
import getpass  # Python get user input secure
import re  # Python regular expression
from datetime import datetime  # Timestamp for remote backups


_BACKED_UP_TARGETS = set()


def createSSHClient(rpiHost, rpiUser, rpiPass):
    """
    Function to create an SSH client with python paramiko
    """

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(rpiHost, username=rpiUser, password=rpiPass)
        return ssh
    except Exception as e:
        print("   ... * EXCEPTION HAPPENED : Cannot create RPi SSH client.")
        print("   ... * Error : %s: %s" % (e.__class__, e))


def getUserConfig(fileName, splitterChar):
    """
    Function to read the user configuration file as a dictionary.
    """

    userConfig = {}
    with open(fileName) as configFile:
        for eachLine in configFile:
            if "=" in eachLine:
                (settingName, settingValue) = eachLine.split(splitterChar)
                settingName = settingName.strip()
                settingValue = settingValue.strip()
                userConfig[settingName] = settingValue
    return userConfig


def createDicStr(str, splitterChar):
    """
    Function to create a dictionary from a formatted text.
    """

    dicT = {}
    for L in str:
        if "=" in L:
            (N, V) = L.split(splitterChar)
            N = N.strip()
            V = V.strip()
            dicT[N] = V
    return dicT


def userConfirm(prompt=None, resp=False):
    """
    Function to get confirmation from user.
    """

    if prompt is None:
        prompt = "   ... Confirm"

    if resp:
        prompt = "   ... %s [%s]|%s: " % (prompt, "y", "n")
    else:
        prompt = "   ... %s [%s]|%s: " % (prompt, "n", "y")

    while True:

        if sys.version_info[0] < 3:
            ans = raw_input(prompt)
        else:
            ans = input(prompt)

        if not ans:
            return resp
        if ans not in ["y", "Y", "n", "N"]:
            print("   ... Please enter y or n.")
            continue
        if ans == "y" or ans == "Y":
            return True
        if ans == "n" or ans == "N":
            return False


def printSTDOutput(std):
    """
    Function to print standard output/error from paramiko ssh client command.
    """

    std = std.readlines()
    for line in std:
        txt = line.encode("ascii")
        txt = txt.strip()
        yield ("   " + txt.decode("utf-8"))


def backup_remote_directory(
    ssh,
    source_dir,
    backup_root="/home/pi/ATM_backups",
    host_key=None,
    subject_name=None,
):
    """Create a timestamped backup of ``source_dir`` on the remote host.

    Hidden folders (starting with ".") and files with extensions .dat, .log,
    .pyc, and .csv are excluded from the copy.
    """

    if ssh is None:
        return

    source_dir = source_dir.rstrip("/")
    if not source_dir:
        return

    cache_key = host_key or source_dir
    if cache_key in _BACKED_UP_TARGETS:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    src_name = os.path.basename(source_dir)
    if not src_name:
        src_name = "AutoTrainerModular"

    subject_part = subject_name.strip().replace("/", "_") if subject_name else ""
    if subject_part:
        backup_root = posixpath.join(backup_root, subject_part)

    backup_dir = posixpath.join(backup_root, f"{src_name}-{timestamp}")
    exclude_patterns = [
        "--exclude='.*'",
        "--exclude='*/.*'",
        "--exclude='*.dat'",
        "--exclude='*.log'",
        "--exclude='*.pyc'",
        "--exclude='*.csv'",
    ]

    command = (
        "if [ -d '{src}' ]; then "
        "mkdir -p '{backup_dir}' && "
        "rsync -a {excludes} '{src}/' '{backup_dir}/' && "
        "echo BACKUP_CREATED '{backup_dir}'; "
        "else "
        "echo SKIP_BACKUP_NO_SOURCE; "
        "fi"
    ).format(src=source_dir, backup_dir=backup_dir, excludes=" ".join(exclude_patterns))

    stdin, stdout, stderr = ssh.exec_command(command)

    stdout_lines = [line.strip() for line in stdout.readlines() if line.strip()]
    stderr_lines = [line.strip() for line in stderr.readlines() if line.strip()]

    reported = False
    for line in stdout_lines:
        if line.startswith("BACKUP_CREATED"):
            reported = True
            backup_path = line.split("BACKUP_CREATED", 1)[1].strip().strip("'")
            print(f"   ... Backup created on remote Pi: {backup_path}")
        elif line.startswith("SKIP_BACKUP_NO_SOURCE"):
            reported = True
            print(f"   ... No existing directory at {source_dir} to backup.")
        else:
            print("   " + line)

    if stderr_lines:
        for line in stderr_lines:
            print("   " + line)
    elif not reported:
        print(f"   ... Backup command completed with no output for {source_dir}.")

    _BACKED_UP_TARGETS.add(cache_key)


def RPiFileUpload(ssh, localDir, remoteDir, fileExt, iPrint=True):
    """
    Function to transfer files from local directory to remote directory
    following a file pattern.
    """

    # Split folder name from folder full path
    lcdirName = os.path.basename(localDir)

    numFilesCopied = 0

    ignoreList = [
        ".xlsx",
        ".pyc",
        ".in.BK",
        ".md",
        "RemoteJobSubmission",
        "GetJobResult",
    ]

    try:
        # Open SFTP for file transfer
        sftp = ssh.open_sftp()

        # Create remote directory if not there
        try:
            sftp.mkdir(remoteDir)
        except IOError:
            if iPrint:
                print("   ... Remote folder: " + remoteDir + " exists.")

        # Go over all files in the folder and transfer files
        for fname in glob.glob(localDir + os.sep + fileExt):

            # Specify local file
            local_file = os.path.join(localDir, fname)

            # Ignore some files
            contFlag = False
            for item in ignoreList:
                if item in local_file:
                    contFlag = True
            if contFlag:
                continue

            # Specify remote file
            remote_file = "".join([remoteDir, os.path.basename(fname)])

            # Put the local file in the remote folder
            sftp.put(local_file, remote_file)

            # Increment number of files transferred
            numFilesCopied += 1

            fprintName = fname.split(os.sep)
            if iPrint:
                print("   ... Uploaded -> " + fprintName[len(fprintName) - 1])

    except Exception as e:
        print("   ... * EXCEPTION HAPPENED : Cannot copy file(s) to RPi.")
        print("   ... * Error : %s: %s" % (e.__class__, e))

    if iPrint:
        print("   ... ==============")
        print(
            "   ... %d files uploaded from %s%s%s folder."
            % (numFilesCopied, '"', lcdirName, '"')
        )
        print("   ... ==============")

    try:
        sftp.close()
    except Exception as e:
        print("   ... * EXCEPTION HAPPENED : Cannot close sftp client.")
        print("   ... * Error : %s: %s" % (e.__class__, e))


def getFileUpdatedContent(tailSFTPClient, logFilePath):
    """
    Get updated content of file by opening file using sftp client
    """

    global fileSize
    lineSep = "\r\n"

    fileToRead = tailSFTPClient.open(logFilePath, "r")
    fileToRead.seek(fileSize, 0)
    dataRead = fileToRead.readline()
    while dataRead:
        yield dataRead.strip(lineSep)
        dataRead = fileToRead.readline()

    fileToRead.close()


def remoteFileCat(tailSFTPClient, logFilePath):
    """
    Read content of a remote file using an SFTP client
    """

    global fileSize
    fileStatus = tailSFTPClient.stat(logFilePath)
    if fileSize != -1:
        if fileStatus.st_size > fileSize:
            for lineFeed in getFileUpdatedContent(tailSFTPClient, logFilePath):
                yield lineFeed

    fileSize = fileStatus.st_size


def readCompilerOutput(fileName, rpiRoot, rpiHost, rpiUser, rpiPass, iFlag=True):
    """
    Read content of compiler output, e.g., log.out
    """

    logFilePath = "".join([rpiRoot, fileName])
    global fileSize
    fileSize = -1

    tailSSH = createSSHClient(rpiHost, rpiUser, rpiPass)
    tailSFTPClient = tailSSH.open_sftp()

    try:
        while True:
            for lineFeed in remoteFileCat(tailSFTPClient, logFilePath):
                print(lineFeed)

            time.sleep(1)

    except KeyboardInterrupt:
        print("")
        if iFlag:
            print("   ... User interrupted program.")
    except Exception as e:
        print("   ... * EXCEPTION HAPPENED : Cannot read remote file.")
        print("   ... * Error : %s: %s" % (e.__class__, e))
    finally:
        if iFlag:
            print("   ... Closing SSH and SFTP clients.")
            print("   ... Ending read of remote file.")
        tailSSH.close()
        tailSFTPClient.close()


def resetTeensy(iTry, rpiRoot, rpiSSH):
    """
    Function to reset Teensy USB connection.
    """

    sep = ";"
    resetPath = os.path.join(rpiRoot, "ResetTeensyCode")

    if iTry == 1:
        rpiCommands = "".join(
            [
                "cd ",
                resetPath,
                sep,
                "chmod +x *.py",
                sep,
                "mv teensy_loader_cli.BK teensy_loader_cli",
                sep,
                "chmod +x teensy_loader_cli",
                sep,
                "./*.py",
            ]
        )
    else:
        rpiCommands = "".join(["cd ", resetPath, sep, "./*.py"])

    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
    printSTDOutput(stdout)
    printSTDOutput(stderr)

    # Wait enough time until the Teensy is reset
    time.sleep(2)

    rpiCommands = "".join(
        ["cd ", resetPath, sep, "./teensy_loader_cli --mcu=mk66fx1m0 -w *.hex"]
    )
    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
    printSTDOutput(stdout)
    printSTDOutput(stderr)

    # Wait enough time until the Teensy is reset
    time.sleep(3)


def checkTeensyUSBConnection(rpiRoot, rpiSSH, userConfig):
    """
    Function to check Teensy USB connection to RPi.
    """

    sep = ";"
    iFlag = False
    iTry = 1

    while not iFlag and iTry < 6:
        print(
            "".join(
                [
                    "   ... Checking Teensy USB connection. Let's try it for ",
                    str(iTry),
                    " time [",
                    str(5 - iTry),
                    " Maximum tries are left] [5 seconds delay].",
                ]
            )
        )

        rpiCommands = "".join(
            [
                "cd ",
                rpiRoot,
                sep,
                "pkill MainCode*",
                sep,
                "pkill java",
                sep,
                "pkill arduino-builder",
                sep,
                "pkill cc1plus",
                sep,
                "pkill teensy",
                sep,
                "pkill teensy_reboot",
                sep,
                "find /dev/ -name ttyAC*",
            ]
        )
        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

        outputMsg = printSTDOutput(stdout)
        printSTDOutput(stderr)

        for line in outputMsg:
            if "ttyACM0" in line.strip() or "ttyACM1" in line.strip():
                iFlag = True
                print(
                    "".join(
                        [
                            "   ... Good news ",
                            userConfig["Name"],
                            ", Teensy USB is connected to RPi.",
                        ]
                    )
                )
                return

        if not iFlag:
            resetTeensy(iTry, rpiRoot, rpiSSH)

        iTry = iTry + 1

    # Report Teensy USB connection and exit.
    print(
        "".join(
            [
                "   ... Maximum number of tries reached. Sorry ",
                userConfig["Name"],
                ", I am not that genius and I have to exit.",
            ]
        )
    )
    exit("   ... * EXCEPTION HAPPENED : Cannot find Teensy USB connection.")


def checkProcessStatus(rpiSSH, procN, userConfig, opt=None):
    """
    Function to check a process status [return: continue, false: stop code]
    """

    sep = ";"
    iProcFlag = False
    rpiCommands = "".join(["ps cax | grep ", procN])
    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

    cmdList = printSTDOutput(stdout)

    for L in cmdList:
        if procN in L.strip():
            iProcFlag = True
            break

    if opt:
        return iProcFlag

    if iProcFlag:
        print("   ... **************************************")
        print("   ... ***     ATM is running in RPi.     ***")
        print("   ... **************************************")
        rpiCommands = "".join(
            [
                "cd ",
                "$(readlink -f /proc/$(pgrep MainCode*)/cwd/) 2>/dev/null",
                sep,
                "cat *.in",
            ]
        )
        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
        cmdList = printSTDOutput(stdout)
        runningExpInfo = createDicStr(cmdList, "=")

        if runningExpInfo:
            print("   ... The running job information:")
            print("   ... ======================================")
            print("".join(["   ... Name of user: ", runningExpInfo["Name"]]))
            print("".join(["   ... RPi IP addresss: ", runningExpInfo["RPi_IP"]]))
            print("".join(["   ... Box name: ", runningExpInfo["Box_Name"]]))
            print("".join(["   ... Subject name: ", runningExpInfo["Subject_Name"]]))
            print("   ... ======================================")

            if userConfig["Name"] != runningExpInfo["Name"]:
                print(
                    "".join(
                        [
                            "   ... It looks like the box belongs to: ",
                            runningExpInfo["Name"],
                        ]
                    )
                )

        userMsg = "".join(
            [userConfig["Name"], ", Do you want to overwrite the current job? "]
        )
        userResponse = userConfirm(prompt=userMsg, resp=False)

        if not userResponse:
            return False

    return True


def createCredFile(dic):
    """Create ssh cred. file."""

    if not os.path.exists(dic["Cred_File"]):
        print("   ... The credential file for storage SSH connection is missing.")
        print("   ... Let's create a new credential file for storage SSH connection.")
        u = getpass.getpass("   ... Enter your SSH username:")
        uE = base64.b64encode(base64.b64encode(u.encode()))
        p = getpass.getpass("   ... Enter your SSH password:")
        pE = base64.b64encode(base64.b64encode(p.encode()))
        with gzip.open(dic["Cred_File"], "wb") as F:
            F.write(uE + "\n".encode())
            F.write(pE + "\n".encode())
        print("   ... The credential file for storage connection is created.")


def getCamDic(dic):
    """Function to return dictionary of camera settings [ip and config file]"""

    camDic = dict()
    for k in dic:
        if "camera_" in k.lower():
            ke = dic[k]
            b = re.findall(r"\[(.*?)\]", ke)[0]
            c = [i.strip() for i in b.split(";")]
            camDic[k] = [c[0], c[1]]

    return camDic


def deployAudioRecording(
    userConfig, rpiUser, rpiPass, rpiRoot, sep, localDir, remoteDir, fileExt
):
    """Deploy audio recording code to RPi devicess."""

    print("   ... ==============")
    ipAdd = userConfig["Microphone_RPi_IP"]
    setFile = userConfig["Audio_Setting_File"]

    if not os.path.exists(setFile):
        print("   ... Missing audio recording configuration file: " + setFile)
        exit("   ... Exiting the program.")

    audioSet = getUserConfig(setFile, "=")

    if ipAdd != audioSet["Microphone_RPi_IP"]:
        print("   ... * EXCEPTION HAPPENED: audio IP mismatch!")
        print(
            "   ... IP address of RPi in user and audio recording setting does not match. Exit!"
        )
        print(
            "   ... IP in user setting: "
            + ipAdd
            + " , IP in camera setting: "
            + audioSet["Microphone_RPi_IP"]
        )
        exit()

    rpiSSH = createSSHClient(ipAdd, rpiUser, rpiPass)

    backup_remote_directory(
        rpiSSH,
        rpiRoot.rstrip("/"),
        host_key=f"{ipAdd}:{rpiRoot.rstrip('/')}",
        subject_name=userConfig.get("Subject_Name"),
    )

    # Transfer files over to RPi [Master or Slave]
    for i, item in enumerate(localDir):
        RPiFileUpload(rpiSSH, item, remoteDir[i], fileExt, iPrint=False)

    # Check current running audio recorder
    runFlag = True
    if checkProcessStatus(rpiSSH, "PyAudioRecorder", userConfig, opt=True):
        userMsg = "   ... Terminated -> current audio recording: " + "[" + ipAdd + "]"
        print(userMsg)
        # runFlag = userConfirm(prompt=userMsg, resp=False)

    print("   ... Deployed -> new audio recording: [" + setFile + "]-[" + ipAdd + "]")

    S1 = " ".join(
        ["nohup ./PyAudioRecorder.py", "</dev/null >/home/pi/log4.out 2>&1 &"]
    )
    rpiCommands = "".join(
        [
            "cd ",
            rpiRoot,
            sep,
            "pkill PyAudioRecorder",
            sep,
            "chmod +x PyAudioRecorder.py",
            sep,
            "sleep 1",
            sep,
            "mv /home/pi/log4.out /home/pi/log4_old.out 2>/dev/null",
            sep,
            "export PYTHONUNBUFFERED=1",
            sep,
            S1,
        ]
    )

    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
    rpiSSH.close()
    print("   ... ==============")


def deployPiCamTransfer(
    userConfig, rpiUser, rpiPass, rpiRoot, sep, localDir, remoteDir, fileExt
):
    """Deploy picamera and transfer code to RPi devicess."""

    camDic = getCamDic(userConfig)
    for cam in camDic:
        print("   ... ==============")
        ipAdd = camDic[cam][0]
        setFile = camDic[cam][1]

        if not os.path.exists(setFile):
            print("   ... Missing camera configuration file: " + setFile)
            exit("   ... Exiting the program.")

        camSet = getUserConfig(setFile, "=")

        if ipAdd != camSet["RPi_IP"]:
            print("   ... * EXCEPTION HAPPENED: camera IP mismatch!")
            print(
                "   ... IP address of RPi in user and camera setting does not match. Exit!"
            )
            print(
                "   ... IP in user setting: "
                + ipAdd
                + " , IP in camera setting: "
                + camSet["RPi_IP"]
            )
            print(
                "   ... Camera type: "
                + camSet["Camera_Type"]
                + " , Camera setting file: "
                + setFile
            )
            exit()

        rpiSSH = createSSHClient(ipAdd, rpiUser, rpiPass)

        backup_remote_directory(
            rpiSSH,
            rpiRoot.rstrip("/"),
            host_key=f"{ipAdd}:{rpiRoot.rstrip('/')}",
            subject_name=userConfig.get("Subject_Name"),
        )

        # Transfer files over to RPi [Master or Slave]
        for i, item in enumerate(localDir):
            RPiFileUpload(rpiSSH, item, remoteDir[i], fileExt, iPrint=False)

        # Set camera gain if user set
        gN = "Gain_" + re.findall("[0-9]+", cam)[0]
        if gN in userConfig:
            gF = rpiRoot + "GainSettings/"
            gFCMD = "mkdir -p " + gF
            if userConfig[gN].lower() != "false":
                print(
                    "   ... Gain Set -> RPi: ["
                    + camSet["Camera_Type"]
                    + "]-["
                    + ipAdd
                    + "] -> "
                    + userConfig[gN]
                )
                gL = re.findall(r"\[(.*?)\]", userConfig[gN])[0]
                gCMD = "".join(["echo ", gL, " >> gain-1234567890.in"])
                rpiCommands = "".join(
                    [
                        "cd ",
                        rpiRoot,
                        sep,
                        gFCMD,
                        sep,
                        "cd GainSettings/",
                        sep,
                        "rm -f *.in",
                        sep,
                        gCMD,
                    ]
                )
            else:
                if userConfig["Use_Setup_Gain"].lower() == "false":
                    rpiCommands = "".join(
                        [
                            "cd ",
                            rpiRoot,
                            sep,
                            gFCMD,
                            sep,
                            "cd GainSettings/",
                            sep,
                            "rm -f *.in",
                        ]
                    )
                    print(
                        "   ... No Gain Set -> RPi: ["
                        + camSet["Camera_Type"]
                        + "]-["
                        + ipAdd
                        + "]"
                    )
                elif userConfig["Use_Setup_Gain"].lower() == "true":
                    rnmCMD = 'for file in *.params; do mv $file "gain-"$(stat --format %Y $file)".in"; done'
                    gainPath = rpiRoot + "GainSettings/"
                    rpiCommands = "".join(
                        [
                            "mkdir -p ",
                            gainPath,
                            sep,
                            "cd ",
                            gainPath,
                            sep,
                            "rm -f *.in",
                            sep,
                            "cd ",
                            userConfig["Setup_Gain_Path"],
                            sep,
                            rnmCMD,
                            sep,
                            "cp gain* ",
                            gainPath,
                        ]
                    )
                    print(
                        "   ... Initial Box Setup Gain Set -> RPi: ["
                        + camSet["Camera_Type"]
                        + "]-["
                        + ipAdd
                        + "]"
                    )

            stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

        # Check current running picamera/transfer
        runFlag = True
        if checkProcessStatus(rpiSSH, "PiCamMain", userConfig, opt=True):
            userMsg = (
                "   ... Terminated -> current picamera/transfer: ["
                + camSet["Camera_Type"]
                + "]-["
                + ipAdd
                + "]"
            )
            print(userMsg)
            # runFlag = userConfirm(prompt=userMsg, resp=False)

        print(
            "   ... Deployed -> new picamera/transfer: ["
            + setFile
            + "]-["
            + camSet["Camera_Type"]
            + "]-["
            + ipAdd
            + "]"
        )

        S1 = " ".join(
            ["nohup ./PiCamMain.py -f", setFile, "</dev/null >/home/pi/log2.out 2>&1 &"]
        )
        rpiCommands = "".join(
            [
                "cd ",
                rpiRoot,
                sep,
                "pkill PiCamMain*",
                sep,
                "chmod +x PiCamMain.py",
                sep,
                "sleep 1",
                sep,
                "mv /home/pi/log2.out /home/pi/log2_old.out 2>/dev/null",
                sep,
                "export PYTHONUNBUFFERED=1",
                sep,
                S1,
            ]
        )
        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

        S2 = " ".join(
            [
                "nohup ./FileTransfer.py -f",
                setFile,
                "</dev/null >/home/pi/log3.out 2>&1 &",
            ]
        )
        rpiCommands = "".join(
            [
                "cd ",
                rpiRoot,
                sep,
                "pkill FileTransfer*",
                sep,
                "chmod +x FileTransfer.py",
                sep,
                "sleep 1",
                sep,
                "mv /home/pi/log3.out /home/pi/log3_old.out 2>/dev/null",
                sep,
                "export PYTHONUNBUFFERED=1",
                sep,
                S2,
            ]
        )

        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

        # time.sleep(1)
        # readCompilerOutput('transfer.log', '/home/pi/', ipAdd, rpiUser, rpiPass, iFlag=False)
        rpiSSH.close()
    print("   ... ==============")


def main():
    """
    Main function to submit an experiment remotely.
    """

    sep = ";"

    # Read user configuration
    userConfig = getUserConfig("userInfo.in", "=")

    # Get root directory working for both windows and linux (or Mac)
    root = os.path.realpath("")
    rootBase = os.path.basename(root)
    dirlist = [
        item
        for item in os.listdir(root)
        if (os.path.isdir(os.path.join(root, item)) and item[0] != ".")
    ]

    # Get remote directory working for linux on RPi
    rpiRoot = "".join(["/home/pi/", rootBase, "/"])

    # Specify local and remote directories
    localDir = [root]
    remoteDir = [rpiRoot]
    for dir in dirlist:
        if "__" not in dir and "Results" not in dir:
            localDir.append(os.path.join(root, dir))
            remoteDir.append("".join([rpiRoot, dir, "/"]))

    # Specify file pattern to copy from local to remote directory
    fileExt = "*.*"

    rpiHost = userConfig["RPi_IP"]
    rpiUser = userConfig["RPi_ID"]
    rpiPass = userConfig[
        "RPi_Pass"
    ]  # base64.b64decode(base64.b64decode((userConfig['RPi_Pass'])))

    # Create an SSH client to master RPi
    rpiSSH = createSSHClient(rpiHost, rpiUser, rpiPass)

    # Check if a job is already running in RPi
    if ("Run_Camera" in userConfig) or ("Run_Microphone" in userConfig):
        if (userConfig["Run_Camera"].lower() != "only") or (
            userConfig["Run_Microphone"].lower() != "only"
        ):
            if not checkProcessStatus(rpiSSH, "MainCode", userConfig):
                return

    backup_remote_directory(
        rpiSSH,
        rpiRoot.rstrip("/"),
        host_key=f"{rpiHost}:{rpiRoot.rstrip('/')}",
        subject_name=userConfig.get("Subject_Name"),
    )

    # Run picamera/transfer code
    if "Run_Camera" in userConfig:
        if userConfig["Run_Camera"].lower() != "false":
            # Create SSH credential file
            createCredFile(userConfig)
            print(
                "   ... Let's run picamera/transfer codes on Master & Slave RPi devices."
            )
            deployPiCamTransfer(
                userConfig, rpiUser, rpiPass, rpiRoot, sep, localDir, remoteDir, fileExt
            )
        else:
            print("   ... Skipping picamera/transfer code.")

        if userConfig["Run_Camera"].lower() == "only":
            print("   ... Skipping AutoTrainerModular code.")
            return

    # Run audio recording code
    if "Run_Microphone" in userConfig:
        if userConfig["Run_Microphone"].lower() != "false":
            print("   ... Let's run audio recording code on RPi.")
            deployAudioRecording(
                userConfig, rpiUser, rpiPass, rpiRoot, sep, localDir, remoteDir, fileExt
            )
        else:
            print("   ... Skipping audio recording code code.")

        if userConfig["Run_Microphone"].lower() == "only":
            print("   ... Skipping AutoTrainerModular code.")
            return

    # Check OpCon Rsync
    trFlag = False
    if "Rsync_OpCon" in userConfig:
        if userConfig["Rsync_OpCon"].lower() == "true":
            if "Run_Camera" in userConfig:
                if userConfig["Run_Camera"].lower() == "false":
                    trFlag = True
            else:
                trFlag = True
            if trFlag:
                createCredFile(userConfig)
        else:
            print("   ... Skipping opcon file sync with SSH storage.")

    # Transfer files over to Master RPi
    for i, item in enumerate(localDir):
        RPiFileUpload(rpiSSH, item, remoteDir[i], fileExt)

    # Run OpCon Sync
    if trFlag:
        # Run FileTransfer on Master RPi
        print(
            "   ... Deployed -> file transfer (OpCon Sync) on Master RPi: ["
            + userConfig["RPi_IP"]
            + "]"
        )
        S2 = " ".join(
            [
                "nohup ./FileTransfer.py -f camInfoM.in </dev/null >/home/pi/log5.out 2>&1 &"
            ]
        )
        rpiCommands = "".join(
            [
                "cd ",
                rpiRoot,
                sep,
                "pkill FileTransfer*",
                sep,
                "chmod +x FileTransfer.py",
                sep,
                "sleep 1",
                sep,
                "mv /home/pi/log5.out /home/pi/log5_old.out 2>/dev/null",
                sep,
                "export PYTHONUNBUFFERED=1",
                sep,
                S2,
            ]
        )

        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
        print("   ... ==============")

    # Check Teensy USB connection
    checkTeensyUSBConnection(rpiRoot, rpiSSH, userConfig)

    # Run main Python code on RPi
    rpiCommands = "".join(
        [
            "cd ",
            rpiRoot,
            sep,
            "rm -f log.out",
            sep,
            "chmod +x MainCode.py",
            sep,
            "export PYTHONUNBUFFERED=1",
            sep,
            "nohup ./MainCode.py  > log.out &",
        ]
    )

    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

    printSTDOutput(stdout)
    printSTDOutput(stderr)

    # Read the log.out content as soon as the compile/upload process ends
    readCompilerOutput("log.out", rpiRoot, rpiHost, rpiUser, rpiPass)

    try:
        rpiSSH.close()
    except Exception as e:
        print("   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.")
        print("   ... * Error : %s: %s" % (e.__class__, e))
        pass


if __name__ == "__main__":
    main()
