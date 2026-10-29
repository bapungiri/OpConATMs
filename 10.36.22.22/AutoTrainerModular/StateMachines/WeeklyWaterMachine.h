#ifndef _WeeklyWaterMachine_h
#define _WeeklyWaterMachine_h

// -----------------------------------------   WeeklyWaterMachine
void WeeklyWaterMachine(){

  RunStartANDEndStateMachine(&startStateMachine);

  InitializeStateMachine();

  int randomDelay = 0;    // A Random number
  int delayStart = 0;     // Used in timers inside state machines [ms]

  // Loop forever until stateStop = 1
  while (1){
    HouseKeeping();
    if(stateStop){
      ReportData(63, weeklyQuota, (millis()-stateMachineStartTime));
      weeklyIntake=0; // Reset weekly water
      EndCurrentStateMachine();
      RunStartANDEndStateMachine(&endStateMachine);
      EndCurrentTrainingProtocol();
      return; // Return to loop()
    }
    else {
      randomDelay=random(1000,3000); // Random intertrial delay of 1-3 seconds added to current time
      delayHK(randomDelay);
      SpeakerPwdAO.on(50);
      delayHK(250);
      SpeakerPwdAO.off(0);
      LickDI.clear();
      delayStart=millis();
      while ((millis()-delayStart)<=5000){
        if(LickDI.isOn()){
          LickDI.clear();
          GiveReward(2);
          break; // Goto while(1)
        }
      } // While millis-delayStart
    }
  } // while(1)
}

#endif
