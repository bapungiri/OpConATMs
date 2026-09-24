/*
  This file declares the variables as well as functions used in the code.
*/

#ifndef _DeclareVariables_h
#define _DeclareVariables_h

// #include <Time.h>               // Provides timekeeping functionality for Arduino and Teensy
#include <TimeLib.h>    // Provides timekeeping functionality for Arduino and Teensy
#include <TimeAlarms.h> // Runs functions at specific times
#include <stdlib.h>     // Standard library for C/C++

#define maxNumAlarms 20 // Maximum number of alarms {update TimeAlarms.h too}

// Define string list of state machine for reporting or printing, print name by calling stateMachineName[currentStateMachine]
#define GENERATE_STRING(x) #x,
static const char *stateMachineName[] = {
    FOREACH_STATEMACHINE(GENERATE_STRING)};

// Preprocessor operators to create state machine functions and a list of them
#define MAKE_FN_DECLARE(x) void x##Machine(void);
#define FUNCTION_DECLARE(x) MAKE_FN_DECLARE(x)
#define MAKE_FN_NAME(x) x##Machine,
#define FUNCTION_NAME(x) MAKE_FN_NAME(x)

// Declare state machine functions
FOREACH_STATEMACHINE(FUNCTION_DECLARE);

// Declare list of state machine functions, How to use: stateMachineFunc[i]();
void (*stateMachineFunc[numStates])() = {
    FOREACH_STATEMACHINE(FUNCTION_NAME)};

// Reset an array values to zero
#define resetToZero(a) memset(a, 0, sizeof(a));

// Training protocols [previous, current, next]
int previousTrainingProtocol = -1; // Previous Training Protocol
int currentTrainingProtocol = 0;   // Current Training Protocol
int nextTrainingProtocol = -1;     // Next Training Protocol

// Initialize current stage of all training protocols to first stage
int currentStage[numTrainingProtocol] = {0};

// Alarm type <Tag 000> && <Tag 001>
typedef enum
{
  Training,
  Special,
  Utility,
  Disable,
  Void
} alarmType;

// Alarm struct <Tag 002>
struct alarmStruct
{
  AlarmID_t id;           // Alarm id { = 0, 1, 2, 3, ..., }
  alarmType type;         // Alarm type {Training, Special, Utility, Disable, Void}
  int protocol;           // Training protocol number {0, 1, 2, 3, ...}
  stateMachine startSM;   // Starting state machine
  stateMachine endSM;     // Ending state machine
  stateMachine specialSM; // Special state machine
} alarms[maxNumAlarms] = {0, Void, -1, DoNothing, DoNothing, DoNothing};

#define sigH(T1, T2, T) ((T - T1) * (T - T2) < 0 ? true : false)
#define totSec(H, M, S) (H * 3600 + M * 60 + S)

// Alarm struct for house light ON or OFF
struct timeLightStruct
{
  int H1, M1, S1, H2, M2, S2, H3, M3, S3;
  stateMachine E1, E2, E3;
  bool applied;
} ligS = {-1, -1, -1, -1, -1, -1, -1, -1, -1, DoNothing, DoNothing, DoNothing, false};

// Number of allocated alarms
uint8_t numAlarms = 0;
AlarmID_t currentAlarmId;

// State machines [previous, current, next]
stateMachine previousStateMachine; // Previous state machine
stateMachine currentStateMachine;  // Current state machine
stateMachine nextStateMachine;     // Next state machine
bool changeStateMachine;           // Change state machine flag

// Starting and ending state machines of sessions
stateMachine startStateMachine = DoNothing; // Starting state machine
stateMachine endStateMachine = DoNothing;   // Ending state machine

// State machine timing variables
unsigned long stateMachineStartTime = millis(); // Local start time of a state machine [ms]
int entryTime = now();                          // Local start time of a state machine [s]
int stateStop = 0;                              // A boolean to stop a state machine (0: continue, 1: stop)

// Daily and weekly reward variables
int dailyQuota;   // Daily quota for pulses of water (each pulse is 0.01 mL of water)
int weeklyQuota;  // Currently there is no weekly quota
int dailyIntake;  // Daily intake of water
int weeklyIntake; // Weekly intake of water
int rewardTime;   // Standard reward delivery time in milliseconds [ms]

// Teensy hourly update to RPi [initial time log]
unsigned long timeStampTeensy = now();

// Clock based interrupts (parameterless function, time in milliseconds)
IntervalTimer toDoTimer[1];

// Initialize hardware properties
void CreateHDW_DI(DI_HDW &, String, uint8_t, OnInterruptFunc, int);
void CreateHDW_DO(DO_HDW &, String, uint8_t, uint8_t);
void CreateHDW_AI(AI_HDW &, String, uint8_t, double);
void CreateHDW_AO(AO_HDW &, String, uint8_t);

// Daily alarm function (HH, MM, SS, AlarmType, TrainingProtocol, StartStateMachine, EndStateMachine, SpecialStateMachine)
void SetDailyAlarms(int, int, int, alarmType, int, stateMachine, stateMachine, stateMachine);

// Weekly alarm function (Day, HH, MM, SS, AlarmType, TrainingProtocol, StartStateMachine, EndStateMachine, SpecialStateMachine)
void SetWeeklyAlarms(timeDayOfWeek_t DOW, int, int, int, alarmType, int, stateMachine, stateMachine, stateMachine);

// Alarm callback function
void AlarmCallBack();

// Set initial alarms
void SetInitialAlarms();

// Run starting and ending state machines
void RunStartANDEndStateMachine(stateMachine *);

// Advance current stage of current training protocol
void AdvanceCurrentStage(bool);

// End current state machine
void EndCurrentStateMachine();

// End curreny training protocol
void EndCurrentTrainingProtocol();

// Get the upcoming non-session state machine of current stage of upcoming training protocol
void GetUpcomingNonSessionStateMachine();

// Get the current non-session state machine of current stage of current training protocol
void GetCurrentNonSessionStateMachine();

// Function to give reward with number of rewards as input (e.g. number of water pulses)
void GiveReward(int);

// Function to check array size and report error if size exceeds
void CheckArraySize(String, int, int);

// Function to sync initial time of Teensy microcontroller
void SyncInitialTime();

// Function to display clock in serial output
void DigitalClockDisplay();

// Function to print digits of current time [called inside DigitalClockDisplay]
void PrintClockDigits(int);

// Function called at the beginning of each state machine to set up variables
void InitializeStateMachine();

// Function to report data to the Teensy 3.6 serial terminal
void ReportData(int, int, int);

// Function to report a full trial summary on one CSV line:
// eventCode, port1Prob, port2Prob, chosenPort, rewarded(1/0/-1), trialId, blockId, unstructuredProb,
// sessionStartEpochMs(abs,64bit), blockStartRelMs, trialStartRelMs, trialEndRelMs
void ReportTrialSummary(int, int, int, int, int, int, int, int, uint64_t, unsigned long, unsigned long, unsigned long);

// Function called at every state and substate machine loop to check for alarms to allow for termination
void HouseKeeping(unsigned long);

// Function to clear all digital input values
void ClearDigitalInputValues();

// Function to clear all analog input triggers
void ClearAnalogTriggers();

// Clock based interrupt parameterless function
void analogInterruptHandler();

// Set initial variables
void SetInitialVariables();

// Set hardware configuration
void SetHardwareConfig();

// Wait for serial and analog USB connections
void WaitForSerialConnections();

// Send initial information to invertPin
void FinalSetup();

// Modified delay function to push serial queue elements out of Teensy
void delayHK(unsigned long);

// Set sound configuration
void SetSoundConfig();

#endif
