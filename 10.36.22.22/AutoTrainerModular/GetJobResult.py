#!/usr/bin/python

import os         # Python operating system module (mkdir, rm, ...)
import glob       # Python Unix style pathname pattern expansion
import paramiko   # Python implementation of the SSHv2 protocol
import base64     # Python base64 data encodings
import time       # Python time module
import tarfile    # Python tar file operations
import shutil     # Python shell utility module
import datetime   # Python date and time module for time purpose
import collections
from RemoteJobSubmission import createSSHClient     # Func SSH client
from RemoteJobSubmission import getUserConfig       # Func read user config
from RemoteJobSubmission import printSTDOutput      # Func print STD output
from RemoteJobSubmission import userConfirm         # Func get user confirm
from RemoteJobSubmission import checkProcessStatus  # Func check process running
from RemoteJobSubmission import getCamDic           # Func get camera setting


def RPiFileDownload(ssh, root, rpiRoot, remoteFileList, opt=True):
    """
    Function to transfer files from remote directory to local directory.
    """

    # Split folder name from folder full path
    lcdirName = rpiRoot

    numFilesCopied = 0

    try:
        # Open SFTP for file transfer
        sftp = ssh.open_sftp()

        # Create remote directory if not there
        try:
            sftp.mkdir(rpiRoot)
        except IOError:
            if opt:
                print('   ... Remote folder: "' + rpiRoot + '" exists.')

        for fname in remoteFileList:
            # Specify remote file
            remote_file = os.path.join(rpiRoot, fname)

            # Specify local file
            local_file = os.path.join(root, os.path.basename(fname))

            # Put the remote file in the local folder
            sftp.get(remote_file, local_file)

            # Increment number of files transferred
            numFilesCopied += 1

            fprintName = fname.split('/')
            if opt:
                print('   ... Downloaded -> ' + fprintName[len(fprintName)-1])

    except Exception as e:
        print('   ... * EXCEPTION HAPPENED : Cannot copy file(s) from RPi: ' + remote_file)
        print('   ... * Error : %s: %s' % (e.__class__, e))

    if opt:
        print('   ... %d files downloaded from %s%s%s folder.'
              % (numFilesCopied, "\"", lcdirName, "\""))
        print('   ... ==============')

    try:
        sftp.close()
    except Exception as e:
        print('   ... * EXCEPTION HAPPENED : Cannot close sftp client.')
        print('   ... * Error : %s: %s' % (e.__class__, e))


def remoteFolderExist(ssh, folderPath):
    """
    Function to check if remote folder exists
    """

    sftp = ssh.open_sftp()

    try:
        sftp.stat(folderPath)
        return True
    except IOError:
        return False
    finally:
        sftp.close()


def extractFile(root, tarFileName):
    """
    Function to extract tar files
    """

    if os.path.isfile(tarFileName):
        # Extract compressed file
        tarObj = tarfile.open(tarFileName)
        tarObj.extractall(root)
        tarObj.close()

        # Delete compressed file
        os.remove(tarFileName)


def getAnalogOutputs_tar(ssh, root, rpiRoot, userConfig):
    """
    Function to download analog files from RPi device [tar file version].
    """

    print('   ... Downloading analog files from RPi device.')

    analogFolderPath = os.path.join(rpiRoot, ''.join(['Analog-', userConfig['Subject_Name']]))
    tarFileName = ''.join(['Analog-', userConfig['Subject_Name'], '.tar'])

    if remoteFolderExist(ssh, analogFolderPath):
        sep = ';'
        tmpCmd = ''.join(['tar -cf ', tarFileName, ' Analog-', userConfig['Subject_Name']])
        rpiCommands = ''.join(['cd ', rpiRoot,
                               sep, tmpCmd])

        stdin, stdout, stderr = ssh.exec_command(rpiCommands)

        RPiFileDownload(ssh, root, rpiRoot, [tarFileName])

        # Remove tar file
        tmpCmd = ''.join(['rm -f ', tarFileName])
        rpiCommands = ''.join(['cd ', rpiRoot,
                               sep, tmpCmd])
        stdin, stdout, stderr = ssh.exec_command(rpiCommands)

        extractFile(root, os.path.join(root, tarFileName))


def getAnalogOutputs(ssh, root, rpiRoot, userConfig):
    """
    Function to download analog files from RPi device.
    """

    analogFolderPath = os.path.join(rpiRoot, ''.join(['Analog-', userConfig['Subject_Name']]))
    localAnalogFolderPath = os.path.join(root, ''.join(['Analog-', userConfig['Subject_Name']]))

    if remoteFolderExist(ssh, analogFolderPath):

        # Create local analog parent directory
        if not os.path.exists(localAnalogFolderPath):
            os.makedirs(localAnalogFolderPath)

        # Get list of analog sub-foders inside remove analog folder
        sep = ';'
        rpiCommands = ''.join(['cd ', analogFolderPath,
                               sep, 'ls'])

        stdin, stdout, stderr = ssh.exec_command(rpiCommands)

        remoteDirList = [L.strip() for L in list(printSTDOutput(stdout))]

        # Scan each remote sub-directory and transfer files over [if not exist]
        if remoteDirList:
            for dir in remoteDirList:

                    dirPath = ''.join([analogFolderPath, '/', dir, '/'])
                    localDirPath = os.path.join(localAnalogFolderPath, dir)

                    printPath = ''.join(['   ... Saving analong files to: ',
                                         '/Analog/', dir, ' folder'])
                    print(printPath)

                    # Create local sub-directory inside Analog folder
                    if not os.path.exists(localDirPath):
                        os.makedirs(localDirPath)

                    # Get list of files inside sub-directory
                    rpiCommands = ''.join(['cd ', dirPath,
                                           sep, 'ls'])

                    stdin, stdout, stderr = ssh.exec_command(rpiCommands)

                    remoteFileList = [L.strip() for L in list(printSTDOutput(stdout))]

                    if remoteFileList:
                        TBD = []
                        for file in remoteFileList:
                            if 'anTemp' not in file:
                                localFilePath = os.path.join(localDirPath, file)
                                if not os.path.exists(localFilePath):
                                    TBD.append(file.strip())

                        if TBD:
                            RPiFileDownload(ssh, localDirPath, dirPath, TBD)


def deleteOldFiles(rpiSSH, rpiRoot, fileName):
    """
    Function to delete old files using a pattern. e.g., msg* or output*
    """

    sep = ';'
    rpiCommands = ''.join(['cd ', rpiRoot,
                           sep, ''.join(['ls ', fileName])])

    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

    remoteFileList = [(L.strip()).replace(' ', '\ ') for L in list(printSTDOutput(stdout))]

    # Do not delete if only one file left
    if len(remoteFileList) <= 1:
        return

    remoteFileList = sorted(remoteFileList)
    remoteFileList = remoteFileList[:-1]

    fileListTBD = ' '.join(remoteFileList)

    rpiCommands = ''.join(['cd ', rpiRoot,
                           sep, ''.join(['rm -f ', fileListTBD])])

    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)


def getLastModified(rpiRoot, rpiSSH, filePattern, fileName=None):
    """
    Function to check last modification to file(s) in RPi
    """

    sep = ';'
    rpiCommands = ''.join(['cd ', rpiRoot,
                           sep, 'date +%s',
                           sep, 'stat --format "%Y" ', filePattern])
    stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

    outList = [L.strip() for L in list(printSTDOutput(stdout))]

    currentEpoch = int(outList[0])
    outList = sorted(outList[1:], reverse=True)
    if outList:
        lastModifiedEpoch = int(outList[0])
        lastModifiedT = time.localtime(lastModifiedEpoch)
        msg = ''.join(['   ... Date and time of last modification of ',
                       fileName, ' file: ',
                       time.strftime('%Y-%m-%d %H:%M:%S', lastModifiedT)])
        print(msg)

        diffT = currentEpoch-lastModifiedEpoch
        msg = ''.join(['   ... Duration since last modification of ',
                       fileName, ' file: ',
                       '[HH:MM:SS]: ', str(datetime.timedelta(seconds=diffT))])
        print(msg)

        if diffT > 3600:
                print('   ... ***************************************************')
                print('   ... ***  No change in ' + fileName.ljust(10) + ' for the last hour. ***')
                print('   ... ***************************************************')
        print('   ... ==============')


def checkCameraTransfer(userConfig, rpiUser, rpiPass, root):
    """Function to check picamera/transfer code status on RPi
    """

    camDic = getCamDic(userConfig)
    for cam in camDic:
        ipAdd = camDic[cam][0]
        setFile = camDic[cam][1]

        if not os.path.exists(setFile):
            print("   ... Missing camera configuration file: " + setFile)
            exit("   ... Exiting the program.")

        camSet = getUserConfig(setFile, '=')

        if ipAdd != camSet['RPi_IP']:
            print('   ... * EXCEPTION HAPPENED: camera IP mismatch!')
            print('   ... IP address of RPi in user and camera setting does not match. Exit!')
            print('   ... IP in user setting: ' + ipAdd + ' , IP in camera setting: ' + camSet['RPi_IP'])
            print('   ... Camera type: ' + camSet['Camera_Type'] + ' , Camera setting file: ' + setFile)
            exit()

        sshCL = createSSHClient(ipAdd, rpiUser, rpiPass)

        # Check if picamera still running
        if not checkProcessStatus(sshCL, 'PiCamMain', userConfig, 'S'):
            print('   ... ********************************************')
            print('   ... *** There is NO picamera running on ' + '[' + camSet['Camera_Type'] + ']-[' + ipAdd + ']' + ' ***')
            print('   ... ********************************************')

        # Check if file transfer still running
        if not checkProcessStatus(sshCL, 'FileTransfer', userConfig, 'S'):
            print('   ... ********************************************')
            print('   ... *** There is NO transfer running on ' + '[' + camSet['Camera_Type'] + ']-[' + ipAdd + ']' + ' ***')
            print('   ... ********************************************')

        # Download camera/transfer logs
        print('   ... Downloading camera/transfer logs ' + '[' + camSet['Camera_Type'] + ']-[' + ipAdd + ']')
        rpiRoot = '/home/pi/'
        remoteFileList = ['log2.out', 'log3.out', 'picamera.log', 'transfer.log']
        logRoot = os.path.join(root, 'LogFiles-' + camSet['Camera_Type'] + '-' + ipAdd.split(".")[-1:][0])
        if not os.path.exists(logRoot):
            os.makedirs(logRoot)

        for item in remoteFileList:
            if os.path.exists(os.path.join(logRoot, item)):
                os.remove(os.path.join(logRoot, item))

        RPiFileDownload(sshCL, logRoot, rpiRoot, remoteFileList, opt=False)

        try:
            sshCL.close()
        except Exception as e:
            print('   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.')
            print('   ... * Error : %s: %s' % (e.__class__, e))
            pass


def checkAudioRecording(userConfig, audioConfig, rpiUser, rpiPass, root):
    """Function to check audio recording code status on RPi
    """

    if 'Run_Microphone' in userConfig:
        ipAdd = audioConfig['Microphone_RPi_IP']

        if ipAdd != userConfig['Microphone_RPi_IP']:
            print('   ... * EXCEPTION HAPPENED: audio recorder IP mismatch!')
            print('   ... IP address of RPi in user and audio setting does not match. Exit!')
            print('   ... IP in user setting: ' + ipAdd + ' , IP in audio setting: ' + userConfig['Microphone_RPi_IP'])
            exit()

        sshCL = createSSHClient(ipAdd, rpiUser, rpiPass)

        # Check if audio recording still running
        if not checkProcessStatus(sshCL, 'AudioRecorder', userConfig, 'S'):
            print('   ... ********************************************')
            print('   ... *** There is NO audio recorder running on ' + '[' + ipAdd + ']' + ' ***')
            print('   ... ********************************************')

        # Download audio recorder logs
        print('   ... Downloading audio recorder logs ' + '[' + ipAdd + ']')
        rpiRoot = '/home/pi/'
        remoteFileList = ['log4.out', 'pyaudiorecord.log', 'audio_rsync.log', 'opcon_rsync.log']
        logRoot = os.path.join(root, 'LogFiles-Audio-' + ipAdd.split(".")[-1:][0])
        if not os.path.exists(logRoot):
            os.makedirs(logRoot)

        for item in remoteFileList:
            if os.path.exists(os.path.join(logRoot, item)):
                os.remove(os.path.join(logRoot, item))

        RPiFileDownload(sshCL, logRoot, rpiRoot, remoteFileList, opt=False)

        try:
            sshCL.close()
        except Exception as e:
            print('   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.')
            print('   ... * Error : %s: %s' % (e.__class__, e))
            pass


def getCamHosts(userConfig, camSet=None):
    """Function to get all RPi hostnames (IP) and settings.
    """

    camStruct = list()

    camDic = getCamDic(userConfig)

    for cam in camDic:
        ipAdd = camDic[cam][0]
        setFile = camDic[cam][1]
        camSet = getUserConfig(setFile, '=')
        typ = camSet['Camera_Type'].title()

        if ipAdd != camSet['RPi_IP']:
            print('   ... * EXCEPTION HAPPENED: camera IP mismatch!')
            print('   ... IP address of RPi in user and camera setting does not match. Exit!')
            print('   ... IP in user setting: ' + ipAdd + ' , IP in camera setting: ' + camSet['RPi_IP'])
            print('   ... Camera type: ' + camSet['Camera_Type'] + ' , Camera setting file: ' + setFile)
            exit()

        key = typ + '-[' + ipAdd + ']'

        camStruct.append(collections.namedtuple("setting", "key"))
        camStruct[-1].setting = camSet
        camStruct[-1].key = key

    return camStruct


def killJob(camStruct=None, rpiUser=None, rpiPass=None, rpiSSH=None, userConfig=None,
            audioConfig=None, rpiRoot=None, jobName=None, jobPName=None,
            OpCon=False, deleteAll=False, killMicro=False):
    """Function to kill specific program on RPi.
       Note: deleteAll=True kills OpCon, PiCamera, FileTransfer and deletes all.
    """

    print('   ... **************************************')
    print('   ... ******* CAUTION CAUTION CAUTION ******')
    print('   ... **************************************')

    sep = ';'

    if OpCon or (deleteAll and rpiRoot):

        userMsg = ''.join([userConfig['Name'],
                           ', Are you sure to KILL OpCon job on Master RPi?'])

        userResponse = userConfirm(prompt=userMsg, resp=False)
        if userResponse:
            if deleteAll and rpiRoot:
                rpiCommands = ''.join(['pkill MainCode*'])
            else:
                rpiCommands = ''.join(['pkill ', jobPName, '*'])
            stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
            print('   ... *** OpCon job terminated on Master RPi. ***')
        else:
            print('   ... Skipping OpCon job termination.')
            print('   ... ==============')

    if not OpCon:

        # Kill microphone job if requested
        if (deleteAll and rpiRoot) or killMicro:
            if userConfig['Run_Microphone'].lower() == 'true':
                userMsg = ''.join([userConfig['Name'],
                          ', Are you sure to KILL microphone job on ',
                          userConfig['Microphone_RPi_IP']])
                userResponse = userConfirm(prompt=userMsg, resp=False)
                if userResponse:
                    rpiCommands = ''.join(['pkill AudioRecorder*'])
                    sshCL = createSSHClient(audioConfig['Microphone_RPi_IP'], rpiUser, rpiPass)
                    stdin, stdout, stderr = sshCL.exec_command(rpiCommands)
                    print('   ... *** Microphone job(s) terminated. ***')
                    try:
                        sshCL.close()
                    except Exception as e:
                        print('   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.')
                        print('   ... * Error : %s: %s' % (e.__class__, e))
                        pass
                else:
                    print('   ... Skipping Microphone job(s) termination.')
                    print('   ... ==============')

            if killMicro:
                return

        for item in camStruct:
            camSet = item.setting
            ipAdd = camSet['RPi_IP']
            sshCL = createSSHClient(ipAdd, rpiUser, rpiPass)

            if deleteAll and rpiRoot:
                jobName = 'PiCamera and FileTransfer'

            userMsg = ''.join([userConfig['Name'],
                               ', Are you sure to KILL ', jobName, ' job(s) on ', item.key])

            if deleteAll and rpiRoot:
                userMsg = userMsg + ', and DELETE code folder as well?'

            userResponse = userConfirm(prompt=userMsg, resp=False)
            if userResponse:
                if deleteAll and rpiRoot:
                    buildPath = '/home/pi/build/'
                    videoPath = camSet['RPi_Video_Dir']
                    audioPath = audioConfig['RPi_Audio_Dir']
                    rpiCommands = ''.join(['pkill FileTransfer*',
                                           sep, 'pkill PiCamMain*',
                                           sep, 'rm -rf ', rpiRoot,
                                           sep, 'rm -rf ', buildPath,
                                           sep, 'rm -rf ', videoPath,
                                           sep, 'rm -rf ', audioPath])
                else:
                    rpiCommands = ''.join(['pkill ', jobPName, '*'])
                stdin, stdout, stderr = sshCL.exec_command(rpiCommands)
                print('   ... *** ' + jobName + ' job(s) terminated. ***')
            else:
                print('   ... Skipping ' + jobName + ' job(s) termination.')
                print('   ... ==============')

            try:
                sshCL.close()
            except Exception as e:
                print('   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.')
                print('   ... * Error : %s: %s' % (e.__class__, e))
                pass


def main():
    """
    Main function to get experiment results.
    """

    # Bash command separator
    sep = ';'

    # Read user configuration
    userConfig = getUserConfig('userInfo.in', '=')

    # Get root directory working for both windows and linux (or Mac)
    if not userConfig['Result_Path'] or userConfig['Result_Path'] == '.':
        root = os.path.realpath('')
    else:
        root = os.path.normpath(userConfig['Result_Path'])

    rootBase = os.path.basename(os.path.realpath(''))

    # Create result folder
    resultDirPath = os.path.join(root, ''.join(['Results-', userConfig['Box_Name'],
                                                '-', userConfig['Subject_Name']]))
    if not os.path.exists(resultDirPath):
        os.makedirs(resultDirPath)

    root = resultDirPath

    # First copy user setting file to result folder for further checking
    shutil.copyfile(os.path.join(os.path.realpath(''), 'userInfo.in'),
                    os.path.join(root, 'userInfo.in'))

    # Get remote directory working for linux on RPi
    rpiRoot = ''.join(['/home/pi/', rootBase, '/'])

    rpiHost = userConfig['RPi_IP']
    rpiUser = userConfig['RPi_ID']
    rpiPass = base64.b64decode(base64.b64decode((userConfig['RPi_Pass'])))

    # Create SSH client
    rpiSSH = createSSHClient(rpiHost, rpiUser, rpiPass)

    # Download files from RPi if requested
    if userConfig['Get_Exp_Result'].lower() == 'true':
        # Specify file pattern to copy from remote to local directory
        fileExt = userConfig['Remote_File_Exts'].split(',')
        fileFormat = ' '.join([''.join([userConfig['Subject_Name'], i.strip()]) for i in fileExt])

        rpiCommands = ''.join(['cd ', rpiRoot,
                               sep, ''.join(['ls ', fileFormat])])
        stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)

        remoteFileList = [L.strip() for L in list(printSTDOutput(stdout))]

        RPiFileDownload(rpiSSH, root, rpiRoot, remoteFileList)

    # Get analog data [if activated]
    if userConfig['Analog'].lower() == 'true':
        if userConfig['Get_Exp_Result'].lower() == 'true':
            if userConfig['Get_Analog_Results'].lower() == 'true':
                getAnalogOutputs(rpiSSH, root, rpiRoot, userConfig)

    # Delete old files if asked by user
    if userConfig['Delete_Old_Results'].lower() == 'true':
        userMsg = ''.join([userConfig['Name'],
                          ', Are you sure to delete old results from RPi? '])
        userResponse = userConfirm(prompt=userMsg, resp=False)
        if userResponse:
            print('   ... **************************************')
            print('   ... *** Deleting old results from RPi. ***')
            print('   ... **************************************')
            deleteOldFiles(rpiSSH, rpiRoot, ''.join([userConfig['Subject_Name'],
                                                     '*.log']))
            deleteOldFiles(rpiSSH, rpiRoot, ''.join([userConfig['Subject_Name'],
                                                     '*.dat']))

            # Delete analog files if enabled
            if userConfig['Analog'].lower() == 'true':
                rpiCommands = ''.join(['cd ', os.path.join(rpiRoot,
                                       ''.join(['Analog-', userConfig['Subject_Name']])),
                                       sep, 'find . -type f -name \'an.*\' -delete'])
                stdin, stdout, stderr = rpiSSH.exec_command(rpiCommands)
        else:
            print('   ... Skipping the removal of old results from RPi.')
            print('   ... ==============')

    camStruct = getCamHosts(userConfig)
    audioConfig = getUserConfig('audioInfo.in', '=')

    if userConfig['Delete_Kill_All'].lower() == 'true':
        killJob(camStruct, rpiUser, rpiPass, rpiSSH, userConfig, audioConfig, rpiRoot, jobName='all', deleteAll=True)

    if userConfig['Kill_OpCon'].lower() == 'true':
        killJob(camStruct, rpiUser, rpiPass, rpiSSH, userConfig, jobName='OpCon', jobPName='MainCode', OpCon=True)

    if userConfig['Kill_Camera'].lower() == 'true':
        killJob(camStruct, rpiUser, rpiPass, rpiSSH, userConfig, jobName='PiCamera', jobPName='PiCamMain')

    if userConfig['Kill_Transfer'].lower() == 'true':
        killJob(camStruct, rpiUser, rpiPass, rpiSSH, userConfig, jobName='FileTransfer', jobPName='FileTransfer')

    if 'Run_Microphone' in userConfig:
        if userConfig['Kill_Microphone'].lower() == 'true' and userConfig['Delete_Kill_All'].lower() != 'true':
            killJob(camStruct, rpiUser, rpiPass, rpiSSH, userConfig, audioConfig, killMicro=True)

    time.sleep(1)

    # Check if job still running
    if not checkProcessStatus(rpiSSH, 'MainCode', userConfig, 'S'):
        print('   ... ********************************************')
        print('   ... *** There is NO job running on your master RPi. ***')
        print('   ... ********************************************')

    # Check camera/transfer code status on all attached RPi devices
    checkCameraTransfer(userConfig, rpiUser, rpiPass, root)

    # Check audio recording code status
    if 'Run_Microphone' in userConfig:
        if userConfig['Run_Microphone'].lower() == 'true':
            checkAudioRecording(userConfig, audioConfig, rpiUser, rpiPass, root)

    # Get last modification of result and log files
    getLastModified(rpiRoot, rpiSSH, '*.dat', 'result')
    getLastModified(rpiRoot, rpiSSH, '*.log', 'log')

    # Wait 60 sec before closing the program
    print('   ... This program will end in 60 seconds.')

    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print('')

    try:
        rpiSSH.close()
    except Exception as e:
        print('   ... * EXCEPTION HAPPENED : Cannot close RPi SSH client.')
        print('   ... * Error : %s: %s' % (e.__class__, e))
        pass


if __name__ == "__main__":
    main()
