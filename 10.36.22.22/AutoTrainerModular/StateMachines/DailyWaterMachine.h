#ifndef _DailyWaterMachine_h
#define _DailyWaterMachine_h

// -----------------------------------------   DailyWaterMachine
void DailyWaterMachine(){

  RunStartANDEndStateMachine(&startStateMachine);

  InitializeStateMachine();

  int randomDelay = 0;     // A Random number
  int delayStart = 0;      // Used in timers inside state machines [ms]

  // Loop forever until stateStop = 1
  while (1){
    HouseKeeping();
    if(stateStop){
      Serial.print("D,");
      Serial.println(dailyIntake);
      dailyIntake=0; // Reset daily water
      ReportData(63, dailyQuota, (millis()-stateMachineStartTime));
      EndCurrentStateMachine();
      RunStartANDEndStateMachine(&endStateMachine);
      EndCurrentTrainingProtocol();
      return; // Return to loop()
    }
    else{  // Check if enough water has been given
      if(dailyIntake>=dailyQuota){ // Exit the state machine, daily quota met
        Serial.print("D,");
        Serial.println(dailyIntake);
        dailyIntake=0; // Reset daily water
        ReportData(63, dailyQuota, (millis()-stateMachineStartTime));
        GetUpcomingNonSessionStateMachine();
        EndCurrentStateMachine();
        RunStartANDEndStateMachine(&endStateMachine);
        EndCurrentTrainingProtocol();
        return; // Return to loop()
      }
      else { // If duration has not expired and Quota is not reached, run state machine
        randomDelay = random(1000,3000); // Random intertrial delay of 1-3 seconds added to current time
        delayHK(randomDelay);
        SpeakerPwdAO.on(50);  // Tone on
        delayHK(250);
        SpeakerPwdAO.off(0);  // Tone off
        LickDI.clear();
        delayStart = millis();
        while ((millis()-delayStart) <= 5000){
          if(LickDI.isOn()){
            LickDI.clear();
            GiveReward(2);
            break; // Goto while(1)
          }
        }
      }
    }
  } // End of while(1)
}

#endif
