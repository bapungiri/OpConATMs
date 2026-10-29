#ifndef _DoNothingMachine_h
#define _DoNothingMachine_h

// -----------------------------------------   DoNothingMachine
void DoNothingMachine(){

  InitializeStateMachine();

  while (1){
    HouseKeeping();
    if (stateStop){
      EndCurrentStateMachine();
      EndCurrentTrainingProtocol();
      return; // Return to loop()
    }
  } // End of while(1)
}

#endif
