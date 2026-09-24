#ifndef _NosepokeNonSessionMachine_h
#define _NosepokeNonSessionMachine_h

// State machine variable
struct NosepokeNonSessionStruct{
	int rewardCounter; // Number of rewards in this protocol
	int nosepokeCounter;// Number of nosepokes in this protocol
} NosepokeNonSessionVar = {0,0};

void NosepokeNonSessionMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 		

	// Initialize timers and delays
	int unsigned randomDelay = 0;
	int delayStart = 0;
	int lickTimer = 0;

	// Initialize counter
	NosepokeNonSessionVar.rewardCounter = 0;
	NosepokeNonSessionVar.nosepokeCounter = 0;

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeNonSessionVar.nosepokeCounter, (millis()-stateMachineStartTime));
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop()
		}
		else{
			// Training protocol
			//randomSeed(Randomizer.anRead());
			randomDelay=random(10000,30000); 						// Random 10-30s delay
			delayStart=millis();
			int unsigned whenNosepoke = 0;
			while ((millis()-delayStart)<=randomDelay){				// During delay,
				if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn()){
					whenNosepoke = (millis() - stateMachineStartTime);// when nosepoke turned on,
					WhichNosepoke(whenNosepoke);					// record and report which nosepoke turned on,
					SoundON(0,0,1,0,150);							// give shorter/different freq tone,
					NosepokeNonSessionVar.nosepokeCounter++;					// nosepoke counter +1
					delayHK(350);
					SpeakerPwdAO.on(50);				
					whenNosepoke = 0;
					lickTimer = millis();
					while ((millis()-lickTimer)<=5000){
						if (LickDI.isOn()){
							volatile unsigned long when = millis() - stateMachineStartTime;
							ReportData(26, 1, when);
							LickDI.clear();
							SpeakerPwdAO.off(0);
							GiveReward(1);
							NosepokeNonSessionVar.rewardCounter++;
							break;
						}
						else{
							continue;
						}
					}
					break;					
				}										
				else{
					continue;										// NO nosepoke detected!
				} // checking for nosepoke or lick completed
			} // timer ends
			SpeakerPwdAO.off(0);
			ReportData(89, 1, millis());
			if ((NosepokeNonSessionVar.nosepokeCounter>100)){
				ReportData(63, NosepokeNonSessionVar.nosepokeCounter, (millis()-stateMachineStartTime));
				if (currentStage[currentTrainingProtocol] <2){
					currentStage[currentTrainingProtocol]++;
				}
				GetCurrentNonSessionStateMachine();
				EndCurrentStateMachine();
				return;						
			} // report sent
		} 
	} 
} // SM ends

#endif
