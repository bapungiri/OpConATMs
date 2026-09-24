
#ifndef _NosepokeRewardNonSessionMachine_h
#define _NosepokeRewardNonSessionMachine_h

// State machine variable
struct NosepokeRewardNonSessionStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeRewardNonSessionVar = {0};

void NosepokeRewardNonSessionMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;
	bool rewardFlag = false

	// Initialize counter
	NosepokeRewardNonSessionVar.rewardCounter = 0;
	CamLeftDO.off();
	CamRightDO.off();

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeRewardNonSessionVar.rewardCounter, (millis()-stateMachineStartTime));
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// Training protocol
			int unsigned whenNosepoke = 0;
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn() || Nosepoke3DI.isOn() || Nosepoke4DI.isOn() || Nosepoke5DI.isOn() || Nosepoke6DI.isOn() || Nosepoke7DI.isOn() || Nosepoke8DI.isOn()){
				whenNosepoke = (millis() - stateMachineStartTime);
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
				SoundON(1,0,0,0,500);							// single tone
				delayHK(500);									// delay for moving to reward port,
				GiveReward(1);									// initial 7uL reward
				delayStart=millis();							// 5 sec timer for lick detection
				CamLeftDO.off();
				bool rewardFlag=false;
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						LickDI.clear();								
						GiveReward(1);							// give reward, 21uL
						rewardFlag=true;
						NosepokeRewardNonSessionVar.rewardCounter++;			// Increase reward counter
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
				continue;
			}
		}
		if ((NosepokeRewardNonSessionVar.rewardCounter>100)){
			ReportData(63, NosepokeRewardNonSessionVar.rewardCounter, (millis()-stateMachineStartTime));
			if (currentStage[currentTrainingProtocol] <1){
					currentStage[currentTrainingProtocol]++;
				}
			}
			GetCurrentNonSessionStateMachine();
			EndCurrentStateMachine();
			return;
		}
	}
}		


#endif
