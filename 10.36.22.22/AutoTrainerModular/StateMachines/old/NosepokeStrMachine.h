#ifndef _NosepokeStrMachine_h
#define _NosepokeStrMachine_h

// State machine variable
struct NosepokeStrStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeStrVar = {0};

void NosepokeStrMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeStrVar.rewardCounter = 0;
	CamLeftDO.on();
	CamRightDO.on();

	// Set Mean for Probability Dist
	float mu = SessionMean();
	int n=0;
	float rewardProb;
	int unsigned rewardPercent;

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeStrVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// Structured Reward Probablities SM
			// detect which nosepoke triggered
			int unsigned whenNosepoke;
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn() || Nosepoke3DI.isOn() || Nosepoke4DI.isOn() || Nosepoke5DI.isOn() || Nosepoke6DI.isOn() || Nosepoke7DI.isOn() || Nosepoke8DI.isOn()){
				whenNosepoke = (millis() - stateMachineStartTime);
				uint8_t recordNosepoke[8] = {Nosepoke1DI.diRead(), Nosepoke2DI.diRead(), Nosepoke3DI.diRead(), Nosepoke4DI.diRead(), Nosepoke5DI.diRead(), Nosepoke6DI.diRead(), Nosepoke7DI.diRead(), Nosepoke8DI.diRead()};
  				int whichnosepoke[8]  = {1,2,3,4,5,6,7,8};
  				for (int i = 0; i<=7; ++i){
    					if ((recordNosepoke[i] ==1)){
    						n = whichnosepoke[i];
    					}
    				}
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
			// assign reward probability acc to mean of gaussian
				rewardProb = GenerateStrProb(mu, n);
				rewardPercent = (int unsigned)rewardProb*100;
				ReportData(83, rewardPercent,(millis() - stateMachineStartTime));
			// if licked, give reward acc to reward prob
				SoundON(1,0,0,0,500);							// give shorter/different freq tone,
				delayHK(500);									// delay for moving to reward port,
				delayStart=millis();							// 5 sec timer for lick detection
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26, 1, when);
						LickDI.clear();
						int unsigned randomNumber = random(100);
				        	if (randomNumber> rewardPercent){ // chance that Lick is rewarded & cycle continues
				          		continue; // Goto while((millis()-delayStart)<=5000)
							GiveReward(1);							// give reward
							NosepokeStrVar.rewardCounter++;			// Increase reward counter
						}
						break;
					}
					else{										// If no lick detected,
						continue;								// no reward obtained.
					}
				}
			}				
			else{
				if (NosepokeStrVar.rewardCounter>500){
					ReportData(63, NosepokeStrVar.rewardCounter, (millis()-stateMachineStartTime));
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
