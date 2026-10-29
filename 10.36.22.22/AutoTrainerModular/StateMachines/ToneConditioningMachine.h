#ifndef _ToneConditioningMachine_h
#define _ToneConditioningMachine_h

// State machine variable
struct ToneConditioningStruct {
  int rewardCounter;           // Number of rewards in this state machine
} ToneConditioningVar = {0};

// -----------------------------------------   ToneConditioningMachine
void ToneConditioningMachine(){

  RunStartANDEndStateMachine(&startStateMachine);

  InitializeStateMachine();   // Initialize state machine (entryTime, stateMachineStartTime ...)

  int delayStart = 0;              // Used in timers inside state machines [ms]
  int unsigned randomTimeout = 0;  // Unsigned random number for random timer
  int rewarNotMet = 0;             // A boolean to control the code sequence

  ToneConditioningVar.rewardCounter = 0;

  // Loop forever until stateStop = 1
  while (1){
    HouseKeeping();
    if(stateStop){
      ReportData(63, ToneConditioningVar.rewardCounter, (millis()-stateMachineStartTime));
      EndCurrentStateMachine();
      RunStartANDEndStateMachine(&endStateMachine);
      EndCurrentTrainingProtocol();
      return; // Return to loop()
    }
    else{      // Run state machine
      randomTimeout=random(10000,30000); // Random intertrial delay of 10-30 seconds added to current time
      delayStart=millis();
      while ((millis()-delayStart)<=randomTimeout){ // Cycle unless time expires
        if (LeverDI.isOn()) {
          LeverDI.clear();
          break; // Exits the while "millis-delayStart" loop
        }
      }
      SpeakerPwdAO.on(50);
      LickDI.clear();
      delayStart=millis();
      while ((millis()-delayStart)<=5000){ // Set a new timer 5 seconds
        if (LickDI.isOn()){
          LickDI.clear();
          SpeakerPwdAO.off(0);
          GiveReward(1);
          ToneConditioningVar.rewardCounter++;
          if (ToneConditioningVar.rewardCounter>50){
            ReportData(63, ToneConditioningVar.rewardCounter, (millis()-stateMachineStartTime));
            AdvanceCurrentStage();
            EndCurrentStateMachine();
            return;  // Return to loop()
          }
          else{
            rewarNotMet = 1;
            break; // Goto while(1)
          }
        }
      } // While millis-delayStart
      if (rewarNotMet){
        rewarNotMet = 0;
        continue; // Goto while(1)
      }
      SpeakerPwdAO.off(0);
    }
  } // While(1)
}

#endif
