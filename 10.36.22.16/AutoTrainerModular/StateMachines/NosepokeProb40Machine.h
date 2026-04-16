#ifndef _NosepokeProb40Machine_h
#define _NosepokeProb40Machine_h

// State machine variable
struct NosepokeProb40Struct{
	int rewardCounter; // Number of rewards in this 
} NosepokeProb40Var = {0};

void NosepokeProb40Machine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeProb40Var.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeProb40Var.rewardCounter, (millis()-stateMachineStartTime));
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
				SpeakerPwdAO.on(50);							// give shorter/different freq tone,
				// SoundON(1,0,0,0,500);
				delayHK(500);									// delay for moving to reward port,
				bool rewardFlag=false;
				SpeakerPwdAO.off(0);
				delayStart=millis();							// 5 sec timer for lick detection
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26, 1, when);
						LickDI.clear();
						int unsigned randomNumber = random(100);
			        	if (randomNumber>60){ // 40% chance that Lick is detected and cycle continues
			          		//continue; // Goto while((millis()-delayStart)<=5000)
							GiveReward(1);							// give reward
							rewardFlag=true;
							NosepokeProb40Var.rewardCounter++;			// Increase reward counter
						}
						break;
					}
					else{										// If no lick detected,
						continue;								// no reward obtained.
					}
				}
				if (rewardFlag==false){
					ReportData(86, 1,(millis()-stateMachineStartTime));	
				}
				//break;											// update stop signal
			}	
			else{
				if (NosepokeProb40Var.rewardCounter>200){
					ReportData(63, NosepokeProb40Var.rewardCounter, (millis()-stateMachineStartTime));
					AdvanceCurrentStage();
					EndCurrentStateMachine();
					return;
				}
			}
		}
	}
}	

#endif	
