#ifndef _NosepokeUNStrMachine_h
#define _NosepokeUNStrMachine_h

// State machine variable
struct NosepokeUNStrStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeUNStrVar = {0};

void NosepokeUNStrMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeUNStrVar.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();

	// Set Mean for Probability Dist
	// float mu = 4.0;
	float mu = SessionMean(); 
	float rewardProb;

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeUNStrVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// UNstructured Reward Probablities SM
			int unsigned whenNosepoke = 0;
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn() || Nosepoke3DI.isOn() || Nosepoke4DI.isOn() || Nosepoke5DI.isOn() || Nosepoke6DI.isOn() || Nosepoke7DI.isOn() || Nosepoke8DI.isOn()){
				whenNosepoke = (millis() - stateMachineStartTime);
				WhichNosepoke(whenNosepoke);					// Report port# and time
				whenNosepoke = 0;		
				// use randomized port number to generate reward prob - then assign reward prob 
				rewardProb = GenerateUnstrProb(mu);
				SoundON(1,0,0,0,500);							// give shorter/different freq tone,
				delayHK(500);									// delay for moving to reward port,
				delayStart=millis();							// 5 sec timer for lick detection
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26, 1, when);
						LickDI.clear();
						int randomNumber = random(100);
				        	if (randomNumber>int(rewardProb*100)){ // chance that Lick is detected and cycle continues
				          		continue; // Goto while((millis()-delayStart)<=5000)
							GiveReward(1);							// give reward
							NosepokeUNStrVar.rewardCounter++;			// Increase reward counter
						}
						break;
					}
					else{										// If no lick detected,
						continue;								// no reward obtained.
					}
				}
				//break;											// update stop signal
			}					
			else{
				if (NosepokeUNStrVar.rewardCounter>500){
					ReportData(63, NosepokeUNStrVar.rewardCounter, (millis()-stateMachineStartTime));
					EndCurrentStateMachine();						// End TP if reward > 30.
					RunStartANDEndStateMachine(&endStateMachine);
					EndCurrentTrainingProtocol();
					return;
				}
			}
		}
	}
}	

#endif	
