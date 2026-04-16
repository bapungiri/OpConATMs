#ifndef _NosepokeProbIndependentMachine_h
#define _NosepokeProbIndependentMachine_h
// #include <stdio.h> *****

// State machine variabe
struct NosepokeProbIndependentStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeProbIndependentVar = {0};


//report probability data? ******

void NosepokeProbIndependentMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeProbIndependentVar.rewardCounter = 0; 
	CamLeftDO.on();
	CamRightDO.on();

	
	int prob1 = (int)(drawProb()*100); 
	ReportData(83, 1, prob1);
	int prob2 = (int)(drawProb()*100); 
	ReportData(83, 2, prob2); 
	
	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeProbIndependentVar.rewardCounter, (millis()-stateMachineStartTime));
			//NosepokeStrVar.sessionNum++; *****
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; //return to loop() 
		}
		else{
			int unsigned whenNosepoke = 0;
			if (Nosepoke1DI.isOn()){
				whenNosepoke = (millis() -  stateMachineStartTime);
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
				SpeakerPwdAO.on(50);
				delayHK(500);
				bool rewardFlag=false; //what does this do? ****
				SpeakerPwdAO.off(0);
				delayStart=millis();
				while((millis()-delayStart)<=5000){
					if (LickDI.isOn()){
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26,1,when);
						LickDI.clear();
						int unsigned randomNumber = random(100);
						if (randomNumber<(unsigned)prob1){
							GiveReward(1);
							rewardFlag = true;
							NosepokeProbIndependentVar.rewardCounter++;
						}
						break;
					}
					else{
						continue;
					}
				}
				if (rewardFlag==false){
					ReportData(86, 1,(millis()-stateMachineStartTime));	
				}				

						}
			else if (Nosepoke2DI.isOn()){
				whenNosepoke = (millis() -  stateMachineStartTime);
				WhichNosepoke(whenNosepoke);
				whenNosepoke = 0;
				SpeakerPwdAO.on(50);
				delayHK(500);
				bool rewardFlag=false;
				SpeakerPwdAO.off(0);
				delayStart=millis();
				while((millis()-delayStart)<=5000){
					if (LickDI.isOn()){
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26,1,when);
						LickDI.clear();
						int unsigned randomNumber = random(100);
						if (randomNumber<(unsigned)prob2){
							GiveReward(1);
							rewardFlag=true;
							NosepokeProbIndependentVar.rewardCounter++;
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
				if (NosepokeProbIndependentVar.rewardCounter>200){
					ReportData(63, NosepokeProbIndependentVar.rewardCounter, (millis()-stateMachineStartTime));
					EndCurrentStateMachine();						
					RunStartANDEndStateMachine(&endStateMachine);
					EndCurrentTrainingProtocol();
					return;
				}
			}
		}
	}
}	

#endif	
