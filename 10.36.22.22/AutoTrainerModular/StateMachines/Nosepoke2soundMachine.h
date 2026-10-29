#ifndef _Nosepoke2soundMachine_h
#define _Nosepoke2soundMachine_h

// State machine variable
struct Nosepoke2soundStruct{
	int rewardCounter; // Number of rewards in this protocol
	int nosepokeCounter;// Number of nosepokes in this protocol
} Nosepoke2soundVar = {0,0};

void Nosepoke2soundMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	Nosepoke2soundVar.rewardCounter = 0;
	Nosepoke2soundVar.nosepokeCounter=0;
	CamLeftDO.on();
	CamRightDO.on();

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, Nosepoke2soundVar.nosepokeCounter, (millis()-stateMachineStartTime));
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
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn() || Nosepoke3DI.isOn() || Nosepoke4DI.isOn() || Nosepoke5DI.isOn() || Nosepoke6DI.isOn() || Nosepoke7DI.isOn() || Nosepoke8DI.isOn()){
				whenNosepoke = (millis() - stateMachineStartTime);// when nosepoke turned on,
				WhichNosepoke(whenNosepoke);					// report time and port for nosepoke
				whenNosepoke = 0;
				SoundON(0,0,1,0,150);							//shorter/diff sound
				delayHK(350);
				Nosepoke2soundVar.nosepokeCounter++;
				delayStart=millis();							// 5 sec timer for lick detection
				while ((millis()-delayStart)<=5000){
					if (LickDI.isOn()){							// If lick detected,
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26, 1, when);
						LickDI.clear();
						SoundON(1,0,0,0,500);							
						GiveReward(1);							// give reward
						Nosepoke2soundVar.rewardCounter++;			// Increase reward counter
						break;
					}
					else{										// If no lick detected,
						continue;								// no reward obtained.
					}
				}
			}
			else{	
				if (Nosepoke2soundVar.nosepokeCounter>200){
					ReportData(63, Nosepoke2soundVar.nosepokeCounter, (millis()-stateMachineStartTime));
					AdvanceCurrentStage();
					EndCurrentStateMachine();						// Advance to stage 3 if reward > 30.
					return;
				}
			}
		}
	}
}		


#endif
