#ifndef _NosepokeProbDependentMachine_h
#define _NosepokeProbDependentMachine_h
// #include <stdio.h> *****

// State machine variabe
struct NosepokeProbDependentStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeProbDependentVar = {0};

float drawProb(){
	float probArray[8] = {0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9}; 
	int n = random(8);
	ReportData(999, 1, n);
	ReportData(998, 1, (int)(probArray[n]*100));
	return probArray[n];
	
}

//report probability data? ******

void NosepokeProbDependentMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 						

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeProbDependentVar.rewardCounter = 0; 
	CamLeftDO.on();
	CamRightDO.on();

	int prob = (int)(drawProb()*100); 
	ReportData(83, 1, prob); 
	ReportData(84, 2, (100-prob));

	//Loop until stateStop = 1
	while (1){
		HouseKeeping();
		if(stateStop){
			// End SM
			ReportData(63, NosepokeProbDependentVar.rewardCounter, (millis()-stateMachineStartTime));
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
						if (randomNumber<((unsigned)prob)){
							GiveReward(1);
							rewardFlag = true;
							NosepokeProbDependentVar.rewardCounter++;
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
						if ((signed)randomNumber<(100-prob)){
							GiveReward(1);
							rewardFlag=true;
							NosepokeProbDependentVar.rewardCounter++;
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
				if (NosepokeProbDependentVar.rewardCounter>1000){
					ReportData(63, NosepokeProbDependentVar.rewardCounter, (millis()-stateMachineStartTime));
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
