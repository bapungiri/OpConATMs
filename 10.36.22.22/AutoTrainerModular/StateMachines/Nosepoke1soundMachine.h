
#ifndef _Nosepoke1soundMachine_h
#define _Nosepoke1soundMachine_h

// State machine variable
struct Nosepoke1soundStruct{
	int rewardCounter; // Number of rewards in this 
} Nosepoke1soundVar = {0};

void Nosepoke1soundMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	Nosepoke1soundVar.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();
	//Loop until stateStop = 1
	
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, Nosepoke1soundVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// Training protocol
			int unsigned whenNosepoke = 0;
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn()){
				whenNosepoke = (millis() - stateMachineStartTime);
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
				SpeakerPwdAO.on(50);							// single tone
				delayHK(500);									// delay for moving to reward port,
				SpeakerPwdAO.off(0);
				delayStart=millis();							// 5 sec timer for lick detection
				bool rewardFlag=false;
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						LickDI.clear();								
						GiveReward(1);							// give reward
						rewardFlag=true;
						Nosepoke1soundVar.rewardCounter++;			// Increase reward counter
						break;
					}
					else{										// If no lick detected,
						continue;								// no reward obtained.
					}
				}
				if (rewardFlag==false){
					ReportData(86, 1,(millis()-stateMachineStartTime));	
				}
			}
			else{	
				if (Nosepoke1soundVar.rewardCounter>200){
					ReportData(63, Nosepoke1soundVar.rewardCounter, (millis()-stateMachineStartTime));
					AdvanceCurrentStage();
					EndCurrentStateMachine();						// Advance to stage 5 if reward > 30.
					return;
				}
			}
		}
	}
}		


#endif
