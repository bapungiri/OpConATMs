#ifndef _LickTrainMachine_h
#define _LickTrainMachine_h

// State machine variable
struct LickTrainStruct{
	int rewardCounter; // Number of rewards in this 
} LickTrainVar = {0};


void LickTrainMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 		

	// Initialize timers/delays
	int unsigned randomDelay = 0;
	int delayStart = 0;

	// Initialize counter
	LickTrainVar.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, LickTrainVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// Training protocol
			randomDelay=random(10000,30000); 					// Random 10-30s delay
			delayStart=millis();
			while ((millis()-delayStart)<=randomDelay){			// During delay,
				if (LickDI.isOn()){								// If lick detected,
					LickDI.clear();
					continue;
				}
				else if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn()){
					Nosepoke1DI.clear();							// If nosepoke detected,
					Nosepoke2DI.clear();							// If nosepoke detected,
					SoundON(0,0,1,0,150);
					break;
				}
				else{
					continue;									// NO nosepoke or lick detected!
				} // checking for nosepoke or lick completed
			} // timer ends			
			LickDI.clear();
			SpeakerPwdAO.on(50);
			delayStart = millis();
			while ((millis()-delayStart)<=5000){
				if (LickDI.isOn()){
					LickDI.clear();
					SpeakerPwdAO.off(0);
					GiveReward(1);
					LickTrainVar.rewardCounter++;
					break;
				}
			}
			ReportData(89, 1, millis());
			SpeakerPwdAO.off(0);
			if (LickTrainVar.rewardCounter>20){
				ReportData(63, LickTrainVar.rewardCounter, (millis()-stateMachineStartTime));
				AdvanceCurrentStage();
				EndCurrentStateMachine();						// Advance to stage 2 if reward > 30.
				return;
			}
		}
	}
}

#endif
