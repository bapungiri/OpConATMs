#ifndef _NosepokeProb70Machine_h
#define _NosepokeProb70Machine_h

// State machine variable
struct NosepokeProb70Struct{
	int rewardCounter; // Number of rewards in this 
} NosepokeProb70Var = {0};

void NosepokeProb70Machine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeProb70Var.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeProb70Var.rewardCounter, (millis()-stateMachineStartTime));
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
				SpeakerPwdAO.on(50);							// give tone,
				//SoundON(1,0,0,0,500);
				delayHK(500);									// delay for moving to reward port,
				SpeakerPwdAO.off(0);
				bool rewardFlag=false;
				delayStart=millis();							// 5 sec timer for lick detection
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						LickDI.clear();
						int unsigned randomNumber = random(100);
			        	if (randomNumber>30){ // 70% chance that Lick is detected and cycle continues
			          		//continue; // Goto while((millis()-delayStart)<=5000)
							GiveReward(1);							// give reward
							rewardFlag=true;
							NosepokeProb70Var.rewardCounter++;			// Increase reward counter
						}
						break;
					}
					else{										// If no lick detected,
						//ReportData(86, 1, (millis()-stateMachineStartTime));
						continue;								// no reward obtained.
					}
				}
				if (rewardFlag==false){
					ReportData(86, 1,(millis()-stateMachineStartTime));	
				}
				//break;											// update stop signal
			}	
			else{
				if (NosepokeProb70Var.rewardCounter>200){
					ReportData(63, NosepokeProb70Var.rewardCounter, (millis()-stateMachineStartTime));
					AdvanceCurrentStage();
					EndCurrentStateMachine();
					return;
				}
			}
		}
	}
}	

#endif	
