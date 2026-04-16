/*
  This file defines general functions other than state machines.
*/

#ifndef _GeneralFunctions_h
#define _GeneralFunctions_h

#include "HardwareLibrary/HardwareClass.h" // ensure trialSummaryQueue & structs are visible

// -----------------------------------------   CreateHDW_DI
void CreateHDW_DI(DI_HDW &pin, String pinNAM, uint8_t pinN, OnInterruptFunc Func, int interruptMode)
{
  // Set basic pin properties
  pin.pinName = pinNAM;
  pin.pinNum = pinN;
  pin.pinTyp = DIGITAL;
  pin.pinMod = INPUT;

  // Set the pin mode
  pinMode(pin.pinNum, pin.pinMod);

  // Attach pin hardware interrupt
  pin.pinInterruptHandler = Func;
  pin.interruptMode = interruptMode;
  attachInterrupt(pinN, Func, interruptMode);

  // Adding the pointer of digital input hardware class to the digitalInHDW array
  digitalInHDW[numDigitalInputHDW++] = &pin;
}

// -----------------------------------------   CreateHDW_DO
void CreateHDW_DO(DO_HDW &pin, String pinNAM, uint8_t pinN, uint8_t pinInvStatus)
{
  // Set basic pin properties
  pin.pinName = pinNAM;
  pin.pinNum = pinN;
  pin.pinTyp = DIGITAL;
  pin.pinMod = OUTPUT;

  // Set the pin mode
  pinMode(pin.pinNum, pin.pinMod);

  // Adding the pointer of digital output hardware class to the digitalOutHDW array
  digitalOutHDW[numDigitalOutputHDW++] = &pin;

  // Set the pin invert status [High -> Low , Low -> High]
  if (pinInvStatus == invertY)
  {
    pin.pinInvertStatus = true;
    pin.pinOnValue = LOW;
    pin.pinOffValue = HIGH;
  }
  else if (pinInvStatus == invertN)
  {
    pin.pinInvertStatus = false;
    pin.pinOnValue = HIGH;
    pin.pinOffValue = LOW;
  }

  // Turn off the digital output at initialization
  pin.off();
}

// -----------------------------------------   CreateHDW_AI
void CreateHDW_AI(AI_HDW &pin, String pinNAM, uint8_t pinN, double noise)
{
  // Set basic pin properties

  pin.pinName = pinNAM;
  pin.pinNum = pinN;
  pin.pinTyp = ANALOG;
  pin.pinMod = INPUT;

  // Set analog read resolution (same for all analog channels)
  analogReadResolution(analogHDWReadResolution);

  // Set the pin mode
  pinMode(pin.pinNum, pin.pinMod);

  pin.noise = noise;
  pin.binNoise = VoltToBin(noise);

  // Adding the pointer of analog hardware class to the analogInHDW array
  analogInHDW[numAnalogInputHDW++] = &pin;

  if (!analogIntervalTimerActivated)
  {
    toDoTimer[0].begin(analogInterruptHandler, analogHDWReadFrequency); // e.g., 1000 microseconds = 1 ms = 1000 Hz = 1 kHz
    analogIntervalTimerActivated = true;
  }
}

// -----------------------------------------   CreateHardware
void CreateHDW_AO(AO_HDW &pin, String pinNAM, uint8_t pinN)
{
  // Set basic pin properties
  pin.pinName = pinNAM;
  pin.pinNum = pinN;
  pin.pinTyp = ANALOG;
  pin.pinMod = OUTPUT;

  // Set the pin mode
  pinMode(pin.pinNum, pin.pinMod);

  // Adding the pointer of analog output hardware class to the analogOutHDW array
  analogOutHDW[numAnalogOutputHDW++] = &pin;
}

// -----------------------------------------   AlarmCalBack
void AlarmCallBack()
{

  // Get the id of current triggered alarm to pull up details of triggered alarm
  AlarmID_t currentAlarmId = Alarm.getTriggeredAlarmId(); // Global variable

  // Get the type of the triggered alarm
  alarmType aType = alarms[currentAlarmId].type;

  // Switch-Case based on alarm type
  switch (aType)
  {
  case Training:
    ReportData(71, 1, (millis() - stateMachineStartTime));

    stateStop = 1;

    previousTrainingProtocol = currentTrainingProtocol;
    previousStateMachine = currentStateMachine;

    nextTrainingProtocol = alarms[currentAlarmId].protocol;
    nextStateMachine = trainingProtocol[nextTrainingProtocol][currentStage[nextTrainingProtocol]][0];

    startStateMachine = alarms[currentAlarmId].startSM;
    endStateMachine = alarms[currentAlarmId].endSM;
    break;

  case Special:
    stateStop = 1;

    previousTrainingProtocol = currentTrainingProtocol;
    previousStateMachine = currentStateMachine;

    nextStateMachine = alarms[currentAlarmId].specialSM;
    nextTrainingProtocol = currentTrainingProtocol; // Just for code purpose

    startStateMachine = alarms[currentAlarmId].startSM;
    endStateMachine = alarms[currentAlarmId].endSM;
    break;

  case Utility:

    previousStateMachine = currentStateMachine;
    currentStateMachine = alarms[currentAlarmId].startSM;

    // Run utility state machine
    stateMachineFunc[currentStateMachine]();

    stateStop = 1; // Since it will reset to zero in the above call

    // Change current state machine back to previous state machine
    currentStateMachine = previousStateMachine;
    previousStateMachine = alarms[currentAlarmId].startSM;

    // Overwrite the next state machine and training protocol
    nextStateMachine = currentStateMachine;
    nextTrainingProtocol = currentTrainingProtocol; // Just for code purpose

    break;

  case Disable:

    // Do nothing if the current state machine is a non-session
    if (currentStateMachine == trainingProtocol[currentTrainingProtocol][currentStage[currentTrainingProtocol]][1])
    {
      break;
    };

    stateStop = 1;
    // Change the current training protocol if trainingNo >= 0
    // trainingNo = -1 is just a flag1 variable to leave the current training protocol untouched

    if (alarms[currentAlarmId].protocol != -1)
    {
      previousTrainingProtocol = currentTrainingProtocol;
      nextTrainingProtocol = alarms[currentAlarmId].protocol;
    }
    else
    {
      previousTrainingProtocol = currentTrainingProtocol;
      nextTrainingProtocol = currentTrainingProtocol;
    }

    previousStateMachine = currentStateMachine;

    // Set the next state machine to the non-session state machine of current stage of next training protocol
    nextStateMachine = trainingProtocol[nextTrainingProtocol][currentStage[nextTrainingProtocol]][1];
    break;

  default:
    break;
  }
}

// -----------------------------------------   RunStartANDEndStateMachine
void RunStartANDEndStateMachine(stateMachine *StMachine)
{
  /*
  Check if any start or end state machine exists. This happens at the beginning
  or end of training session. It resets the StMachine to DoNothing at the end.
  */
  if (*StMachine != DoNothing)
  {
    // Change current state machine to StMachine momentarily
    previousStateMachine = currentStateMachine;
    currentStateMachine = *StMachine;

    // Run starting state machine
    stateMachineFunc[currentStateMachine]();

    // Change current state machine back to previous state machine
    currentStateMachine = previousStateMachine;
    previousStateMachine = *StMachine;

    // Reset the starting or ending state machine to DoNothing to avoid re-entry in case of stage promotion
    *StMachine = DoNothing;
  }
}

// -----------------------------------------   AdvanceCurrentStage
void AdvanceCurrentStage(bool changeSMFlag = true)
{
  /*
  Advance the current stage of the current training protocol if:
    1. it is not the last one.
    2. its next stage is not "DoNothing"
  */
  if (currentStage[currentTrainingProtocol] + 1 < maxNumStage)
  {
    if (trainingProtocol[currentTrainingProtocol][currentStage[currentTrainingProtocol] + 1][0] != DoNothing)
    {
      currentStage[currentTrainingProtocol]++;
    }
  }

  if (changeSMFlag)
  {
    previousStateMachine = currentStateMachine;
    previousTrainingProtocol = currentTrainingProtocol;
    nextTrainingProtocol = currentTrainingProtocol; // Remains the same
    nextStateMachine = trainingProtocol[nextTrainingProtocol][currentStage[nextTrainingProtocol]][0];
  }
};

// -----------------------------------------   EndCurrentStateMachine
void EndCurrentStateMachine()
{
  /*
  End the current stage of the current training protocol.
  */
  ReportData(62, 1, (millis() - stateMachineStartTime));
  currentStateMachine = nextStateMachine;
}

// -----------------------------------------   EndCurrentTrainingProtocol
void EndCurrentTrainingProtocol()
{
  /*
  End the current training protocol.
  */
  ReportData(72, 1, (millis() - stateMachineStartTime));
  currentTrainingProtocol = nextTrainingProtocol;
}

// -----------------------------------------   GetUpcomingNonSessionStateMachine
void GetUpcomingNonSessionStateMachine()
{
  /*
  Return the upcoming non-session state machine of current stage of upcoming training protocol
  */
  previousStateMachine = currentStateMachine;
  previousTrainingProtocol = currentTrainingProtocol;

  if (alarms[currentAlarmId + 1].protocol != -1)
  {
    nextTrainingProtocol = alarms[currentAlarmId + 1].protocol;
  }
  else
  {
    nextTrainingProtocol = currentTrainingProtocol;
  }

  nextStateMachine = trainingProtocol[nextTrainingProtocol][currentStage[nextTrainingProtocol]][1];
}

// -----------------------------------------   GetCurrentNonSessionStateMachine
void GetCurrentNonSessionStateMachine()
{
  /*
  Return the current non-session state machine of current stage of current training protocol
  */

  previousStateMachine = currentStateMachine;
  nextTrainingProtocol = currentTrainingProtocol; // Keep training protocol same
  nextStateMachine = trainingProtocol[nextTrainingProtocol][currentStage[nextTrainingProtocol]][1];
}

// -----------------------------------------   HouseKeeping
void HouseKeeping(unsigned long delayT = 0)
{
  /*
     Alarms and Timers are only checked and their functions called when you use
     this delay function. We pass 0 for minimal delay.
     Alarm.delay(milliseconds);
  */

  // Check serialEvent() function
  serialEvent();

  // Hourly update to RPi [in case Teensy crashes]
  if ((now() - timeStampTeensy) >= 3600)
  {
    ReportData(97, 97, (millis() - stateMachineStartTime));
    timeStampTeensy = now();
  }

  // Send report queue data if is not empty
  if (reportQueue.count() > 1000)
  {
    Serial.println("E,Report queue size > 1000.");
  }
  if (trialSummaryQueue.count() > 500)
  {
    Serial.println("E,Trial summary queue size > 500.");
  }

  if (delayT == 0)
  {
    delayT = maxTimeSerialOutHK;
  }

  unsigned long t44 = millis();
  // Fair interleaved draining of both queues so trial summaries are not starved
  while ((millis() - t44) < delayT && (!reportQueue.isEmpty() || !trialSummaryQueue.isEmpty()))
  {
    if (!reportQueue.isEmpty())
    {
      ReportPrintStr = reportQueue.dequeue();
      Serial.print(ReportPrintStr.eventType);
      Serial.print(',');
      Serial.print(ReportPrintStr.value);
      Serial.print(',');
      Serial.print(ReportPrintStr.currentSM);
      Serial.print(',');
      Serial.print(ReportPrintStr.currentTP);
      Serial.print(',');
      Serial.print(ReportPrintStr.smTime);
      Serial.print(',');
      Serial.print(ReportPrintStr.nowTime);
      Serial.print(',');
      Serial.print(ReportPrintStr.dIntake);
      Serial.print(',');
      Serial.print(ReportPrintStr.wIntake);
      Serial.println();
    }
    if (!trialSummaryQueue.isEmpty() && (millis() - t44) < delayT)
    {
      TrialSummaryPrintStr = trialSummaryQueue.dequeue();
      Serial.print(TrialSummaryPrintStr.eventCode);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.port1Prob);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.port2Prob);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.chosenPort);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.rewarded);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialId);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.blockId);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.unstructuredProb);
      Serial.print(',');
      // Full 64-bit session start epoch ms (previously truncated by cast)
      {
        uint64_t v = TrialSummaryPrintStr.sessionStartEpochMs;
        if (v == 0)
        {
          Serial.print('0');
        }
        else
        {
          char buf[21];
          buf[20] = '\0';
          int idx = 20;
          while (v > 0 && idx > 0)
          {
            uint8_t digit = v % 10ULL;
            v /= 10ULL;
            buf[--idx] = '0' + digit;
          }
          Serial.print(&buf[idx]);
        }
      }
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.blockStartRelMs);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialStartRelMs);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialEndRelMs);
      Serial.println();
    }
  }

  if ((millis() - t44) > delayT)
  {
    Serial.println("E,Sending queue data took more than set time.");
  }

  Alarm.delay(0); // 0 milliseconds
}

// -----------------------------------------   delayHK
void delayHK(unsigned long delayT)
{
  /*
     Modified delay function to push serial queue data out of Teensy board
  */

  unsigned long t44 = millis();
  while ((millis() - t44) < delayT)
  {
    if (!reportQueue.isEmpty())
    {
      ReportPrintStr = reportQueue.dequeue();

      Serial.print(ReportPrintStr.eventType);
      Serial.print(',');
      Serial.print(ReportPrintStr.value);
      Serial.print(',');
      Serial.print(ReportPrintStr.currentSM);
      Serial.print(',');
      Serial.print(ReportPrintStr.currentTP);
      Serial.print(',');
      Serial.print(ReportPrintStr.smTime);
      Serial.print(',');
      Serial.print(ReportPrintStr.nowTime);
      Serial.print(',');
      Serial.print(ReportPrintStr.dIntake);
      Serial.print(',');
      Serial.print(ReportPrintStr.wIntake);
      Serial.println();

      // Call serialEvent()
      serialEvent();
    }
    // Interleave trial summary queue flushing to avoid starvation
    if (!trialSummaryQueue.isEmpty())
    {
      TrialSummaryPrintStr = trialSummaryQueue.dequeue();
      Serial.print(TrialSummaryPrintStr.eventCode);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.port1Prob);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.port2Prob);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.chosenPort);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.rewarded);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialId);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.blockId);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.unstructuredProb);
      Serial.print(',');
      {
        uint64_t v = TrialSummaryPrintStr.sessionStartEpochMs;
        if (v == 0)
        {
          Serial.print('0');
        }
        else
        {
          char buf[21];
          buf[20] = '\0';
          int idx = 20;
          while (v > 0 && idx > 0)
          {
            uint8_t digit = v % 10ULL;
            v /= 10ULL;
            buf[--idx] = '0' + digit;
          }
          Serial.print(&buf[idx]);
        }
      }
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.blockStartRelMs);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialStartRelMs);
      Serial.print(',');
      Serial.print(TrialSummaryPrintStr.trialEndRelMs);
      Serial.println();
      serialEvent();
    }
  }
}

// -----------------------------------------   InitializeStateMachine
void InitializeStateMachine()
{
  stateStop = 0;                    // Allow state machine to cycle
  ClearDigitalInputValues();        // Clear all digital inputs (e.g., lever, lick)
  ClearAnalogTriggers();            // Clear all analog input triggers (e.g., analog lever)
  stateMachineStartTime = millis(); // Time in milliseconds from start of state machine
  entryTime = now();                // Time in seconds      from start of experiment
  ReportData(61, 1, (millis() - stateMachineStartTime));
}

// -----------------------------------------   ReportData
void ReportData(int type, int value, int sessionTime)
{
  ReportStr.eventType = type;
  ReportStr.value = value;
  ReportStr.currentSM = currentStateMachine;
  ReportStr.currentTP = currentTrainingProtocol;
  ReportStr.smTime = sessionTime;
  ReportStr.nowTime = now();
  ReportStr.dIntake = dailyIntake;
  ReportStr.wIntake = weeklyIntake;

  reportQueue.enqueue(ReportStr);
}

// -----------------------------------------   ReportTrialSummary
// Writes a compact single CSV line capturing an entire trial.
// Now uses its own queue (trialSummaryQueue) to remain non-blocking like ReportData.
// Use distinct eventCodes (e.g., 200 lick trial, 201 missed trial) to distinguish from regular ReportData lines.
void ReportTrialSummary(int eventCode,
                        int port1Prob,
                        int port2Prob,
                        int chosenPort,
                        int rewarded,
                        int trialId,
                        int blockId,
                        int unstructuredProb,
                        uint64_t sessionStartEpochMs,
                        unsigned long blockStartRelMs,
                        unsigned long trialStartRelMs,
                        unsigned long trialEndRelMs)
{
  TrialSummaryStr.eventCode = eventCode;
  TrialSummaryStr.port1Prob = port1Prob;
  TrialSummaryStr.port2Prob = port2Prob;
  TrialSummaryStr.chosenPort = chosenPort;
  TrialSummaryStr.rewarded = rewarded;
  TrialSummaryStr.trialId = trialId;
  TrialSummaryStr.blockId = blockId;
  TrialSummaryStr.unstructuredProb = unstructuredProb;
  TrialSummaryStr.sessionStartEpochMs = sessionStartEpochMs;
  TrialSummaryStr.blockStartRelMs = blockStartRelMs;
  TrialSummaryStr.trialStartRelMs = trialStartRelMs;
  TrialSummaryStr.trialEndRelMs = trialEndRelMs;
  trialSummaryQueue.enqueue(TrialSummaryStr);
}

// --------------------   GiveReward ## Pass pin class to make it more modular
void GiveReward(int numPulses)
{
  ReportData(51, numPulses, (millis() - stateMachineStartTime));
  // Deliver water, runs for 40ms for each reward pulse, interrupts still active, not slowed
  for (int i = 0; i < numPulses; i++)
  {
    WaterDO.on(); // Water ON
    delayHK(rewardTime);
    WaterDO.off(); // Water Off
    delayHK(20);
    dailyIntake++;
    weeklyIntake++;
  }
  ReportData(52, 0, (millis() - stateMachineStartTime));
}

// -----------------------------------------   CheckArraySize
void CheckArraySize(String parName, int arrSize, int S)
{
  if (S > arrSize)
  {
    String errMsg;
    errMsg = "E,Array " + parName + " index out of bound " + String(S) + ">" + String(arrSize) + " in SM " + stateMachineName[currentStateMachine] + ", Now(s): " + String(now());
    Serial.println(errMsg);
  }
}

// -----------------------------------------   SyncInitialTime
void SyncInitialTime()
{
  Serial.println("I,Waiting for time sync message from master R-Pi (e.g. T1506298500)");
  while (timeStatus() == timeNotSet)
  {
    serialEvent();
  }

  // Check the time sync status
  if (timeStatus() == timeNotSet)
  {
    Serial.println("E,Time is not synced.");
  }
  else
  {
    Serial.println("I,Teensy time is synced with NTP. Continue ...");
  }
}

// -----------------------------------------   DigitalClockDisplay
void DigitalClockDisplay()
{
  Serial.print("I,Date: ");
  Serial.print(year());
  Serial.print('-');
  Serial.print(month());
  Serial.print('-');
  Serial.print(day());
  Serial.print(" , Time: ");
  Serial.print(hour());
  PrintClockDigits(minute());
  PrintClockDigits(second());
  Serial.println();
}

// -----------------------------------------   PrintClockDigits
void PrintClockDigits(int digits)
{
  Serial.print(':');
  if (digits < 10)
  {
    Serial.print('0');
  }
  Serial.print(digits);
}

// -----------------------------------------   SetDailyAlarms
void SetDailyAlarms(int H, int M, int S, alarmType typ, int ptcl, stateMachine stSM, stateMachine enSM, stateMachine spSM)
{
  // Find total number of alarms
  numAlarms = Alarm.count();

  // Check if numAlarms < maxNumAlarms
  if (numAlarms > maxNumAlarms)
  {
    Serial.println("E,Total number of alarms exceeds.");
    Serial.println("E,Change maxNumAlarms in DeclareVariables.h and dtNBR_ALARMS in TimeAlarms.h");
  }
  else
  {
    alarms[numAlarms].type = typ;
    alarms[numAlarms].protocol = ptcl;
    alarms[numAlarms].startSM = stSM;
    alarms[numAlarms].endSM = enSM;
    alarms[numAlarms].specialSM = spSM;
    alarms[numAlarms].id = Alarm.alarmRepeat(H, M, S, AlarmCallBack);
  }

  if ((typ == Utility) && ((stSM == HouseLightsOn) || (stSM == HouseLightsOff)))
  {

    if (ligS.H3 < 0)
    {
      ligS.H3 = H;
      ligS.M3 = M;
      ligS.S3 = S;
      ligS.E3 = stSM;
    }
    else
    {
      if (totSec(H, M, S) > totSec(ligS.H3, ligS.M3, ligS.S3))
      {
        ligS.H2 = H;
        ligS.M2 = M;
        ligS.S2 = S;
        ligS.E2 = stSM;
        ligS.H1 = ligS.H3;
        ligS.M1 = ligS.M3;
        ligS.S1 = ligS.S3;
        ligS.E1 = ligS.E3;
      }
      else
      {
        ligS.H1 = H;
        ligS.M1 = M;
        ligS.S1 = S;
        ligS.E1 = stSM;
        ligS.H2 = ligS.H3;
        ligS.M2 = ligS.M3;
        ligS.S2 = ligS.S3;
        ligS.E2 = ligS.E3;
      }
    }
  }
}

// -----------------------------------------   SetWeeklyAlarms
void FinalSetup()
{

  // Send analog input pin numbers to RPi for file names
  if (numAnalogInputHDW > 0)
  {
    Serial.print('P');
    for (int i = 0; i < numAnalogInputHDW; i++)
    {

      Serial.print(',');
      Serial.print(analogInHDW[i]->pinNum);
    }
    Serial.println();
  }

  // Check HouseLights
  if (sigH(totSec(ligS.H1, ligS.M1, ligS.S1), totSec(ligS.H2, ligS.M2, ligS.S2), totSec(hour(), minute(), second())))
  {
    Serial.println("I,The initial house light status: " + String(stateMachineName[ligS.E1]));
    stateMachineFunc[ligS.E1]();
  }
  else
  {
    Serial.println("I,The initial house light status: " + String(stateMachineName[ligS.E2]));
    stateMachineFunc[ligS.E2]();
  }
}

// -----------------------------------------   SetWeeklyAlarms
void SetWeeklyAlarms(timeDayOfWeek_t DOW, int H, int M, int S, alarmType typ, int ptcl, stateMachine stSM, stateMachine enSM, stateMachine spSM)
{
  // Find total number of alarms
  numAlarms = Alarm.count();

  // Check if numAlarms < maxNumAlarms
  if (numAlarms > maxNumAlarms)
  {
    Serial.println("E,Total number of alarms exceeds.");
    Serial.println("E,Change maxNumAlarms in DeclareVariables.h and dtNBR_ALARMS in TimeAlarms.h");
  }
  else
  {
    alarms[numAlarms].type = typ;
    alarms[numAlarms].protocol = ptcl;
    alarms[numAlarms].startSM = stSM;
    alarms[numAlarms].endSM = enSM;
    alarms[numAlarms].specialSM = spSM;
    alarms[numAlarms].id = Alarm.alarmRepeat(DOW, H, M, S, AlarmCallBack);
  }
}

// -----------------------------------------   WaitForSerialConnections
void WaitForSerialConnections()
{
  while (!Serial)
  {
    // Wait for serial port to connect
  }

  // Check for analog USB serial be added in GUI ##
  // if (numAnalogInputHDW > 0)
  // {
  //   while ( ! anSerial ){
  //     // Wait for analog USB serial port to connect
  //   }
  // }

  reportQueue.setPrinter(Serial);
}

// -----------------------------------------   serialEvent
void serialEvent()
{

  if (Serial.available())
  {

    char firstChar = Serial.read();

    // Syncing NTP time
    if (firstChar == 'T')
    {
      Serial.println("I,Setting time ...");
      long pctime;
      pctime = Serial.parseInt();
      setTime(pctime);
      DigitalClockDisplay();

      // Reset Teensy health report time
      timeStampTeensy = now();
    }

    // Changing alarms
    if (firstChar == 'A')
    {
    }

    // while (Serial.available()){Serial.read();};
  } // if Serial.available()
} // void serialEvent

// ----------------------------------------- reportGlobalVariables
void writeGlobalParameters()
{
  /*
     Global variable parameters that are stored onto a file.
  */

  Serial.print('G');
  Serial.print(',');
  String currTP = String(currentTrainingProtocol);
  Serial.print(currTP);
  Serial.print(',');
  String currStage = String(currentStage[currentTrainingProtocol]);
  Serial.print(currStage);
  Serial.print(',');
  String dailyIn = String(dailyIntake);
  Serial.print(dailyIn);
  Serial.print(',');
  String weekIn = String(weeklyIntake);
  Serial.print(weekIn);
  Serial.println();

  // Call serialEvent()
  serialEvent();
}

// Returns Unix epoch in milliseconds (64‑bit)
uint64_t epochMillis()
{
  static time_t lastSec = 0;
  static unsigned long secBaseMillis = 0;
  time_t s = now();
  // When the second value changes, capture the millis() at that boundary
  if (s != lastSec)
  {
    lastSec = s;
    secBaseMillis = millis();
  }
  // millisSinceSec: how many ms since the captured second boundary
  unsigned long msSinceSec = millis() - secBaseMillis; // handles rollover via unsigned arithmetic
  if (msSinceSec > 999)
    msSinceSec = 999; // clamp (in case of slight scheduling lag)
  return (uint64_t)s * 1000ULL + (uint64_t)msSinceSec;
}
#endif
