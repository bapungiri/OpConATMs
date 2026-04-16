/*
This file defines variables and function variables.
*/

#ifndef _SetInitialVariables_h
#define _SetInitialVariables_h

void SetInitialVariables()
{

  // Set current, previous, and next training protocol
  currentTrainingProtocol = 0;
  previousTrainingProtocol = -1; // not useful here
  nextTrainingProtocol = -1;     // alarms will set it

  // Set current stage
  currentStage[currentTrainingProtocol] = 0;

  // Set current state machine to non-session state machine of first stage of first training protocol
  currentStateMachine = trainingProtocol[currentTrainingProtocol][currentStage[currentTrainingProtocol]][1];
  previousStateMachine = DoNothing;
  nextStateMachine = DoNothing;

  // Initialize starting and ending state machine of sessions
  startStateMachine = DoNothing;
  endStateMachine = DoNothing;

  // Initialize entry time (s, ms) to state machines and their stop indicator
  entryTime = 0;
  stateMachineStartTime = 0;
  stateStop = 0;

  // Initialize daily reward, weekly reward, and reward time
  dailyIntake = 0;
  weeklyIntake = 0;
  dailyQuota = 2000; // restricted water=10ml per day
  weeklyQuota = 10500;
  rewardTime = 15; // 0.005 ml per pulse

  // Report The Initial State Machine
  Serial.print("I,The starting state machine is: ");
  Serial.println(stateMachineName[currentStateMachine]);
}

#endif
