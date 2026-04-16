
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

	// Initialize counter
	NosepokeRewardNonSessionVar.rewardCounter = 201;
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
			//NosepokeLed1DO.on();
			//NosepokeLed2DO.on();
			//NosepokeLed3DO.on();
			//NosepokeLed4DO.on();
			int unsigned whenNosepoke = 0;
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn()){
				//NosepokeLed1DO.off();
				//NosepokeLed2DO.off();
				//NosepokeLed3DO.off();
				//NosepokeLed4DO.off();
				whenNosepoke = (millis() - stateMachineStartTime);
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
				SpeakerPwdAO.on(50);							// single tone
				delayHK(500);									// delay for moving to reward port,
				SpeakerPwdAO.off(0);
				GiveReward(1);									// initial 7uL reward
				delayStart=millis();							// 5 sec timer for lick detection
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
			if (NosepokeRewardNonSessionVar.rewardCounter>200){
				ReportData(63, NosepokeRewardNonSessionVar.rewardCounter, (millis()-stateMachineStartTime));
				if (currentStage[currentTrainingProtocol] <3){
					currentStage[currentTrainingProtocol]++;
				}
				GetCurrentNonSessionStateMachine();
				EndCurrentStateMachine();						// Advance to stage 5 if reward > 30.
				return;
 			}
		}
	}
}		


#endif
