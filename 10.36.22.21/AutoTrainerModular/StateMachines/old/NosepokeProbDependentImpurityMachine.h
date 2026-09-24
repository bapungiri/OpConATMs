// New SM - min sess len and random block switching
#ifndef _NosepokeProbDependentMachine_h
#define _NosepokeProbDependentMachine_h
// #include <stdio.h> *****

// State machine variabe
struct NosepokeProbDependentStruct{
	int rewardCounter; // Number of rewards in this 
} NosepokeProbDependentVar = {0};

float drawProb(){
	float probArray[6] = {0.2, 0.3, 0.4, 0.6, 0.7, 0.8}; 
	int n = random(6);
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
	
    int unstrprob = 16;
    int strprob = 84;
	int unsigned randomEnvDraw = random(100);

	if (randomEnvDraw < (unsigned)strprob){
		int prob1 = (int)(drawProb()*100);
		int prob2 = 100 - prob1;
		ReportData(83, 1, prob1);
		ReportData(83, 2, prob2); 
	}
	else{
		int prob1 = (int)(drawProb()*100); 
		ReportData(83, 1, prob1);
		int prob2 = (int)(drawProb()*100); 
		ReportData(83, 2, prob2); 
	}

	int min_length = 100;
	int switchProb = 2;
	int trialCounter = 0;
	bool restartSession = false;


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
			if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn()){
				int port[2] = {!Nosepoke1DI.diRead(), !Nosepoke2DI.diRead()}; // Use ! for new IR sensosrs
				whenNosepoke = (millis() -  stateMachineStartTime);
				WhichNosepoke(whenNosepoke); // Report which nosepoke and when 
				whenNosepoke = 0;
				SpeakerPwdAO.on(50);
				delayHK(500);
				bool rewardFlag=false; 
				SpeakerPwdAO.off(0);
				delayStart=millis();
				while((millis()-delayStart)<=5000){
					if (LickDI.isOn()){
						trialCounter += 1;
						int unsigned randomDraw = random(100);
						if (trialCounter > min_length){
						if (randomDraw < (unsigned)switchProb){
							restartSession = true; 
						}
					}
						volatile unsigned long when = millis() - stateMachineStartTime;
						ReportData(26,1,when);
						LickDI.clear();
						int unsigned randomNumber = random(100);
						if (port[0] == 1){
						if (randomNumber<(unsigned)prob1){
							GiveReward(1);
							rewardFlag = true;
							NosepokeProbDependentVar.rewardCounter++;
						}
					}
						else if(port[1] == 1){
						if (randomNumber<(unsigned)prob2){
							GiveReward(1);
							rewardFlag = true;
							NosepokeProbDependentVar.rewardCounter++;
						}
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
					


			// else if (Nosepoke2DI.isOn()){
			// 	whenNosepoke = (millis() -  stateMachineStartTime);
			// 	WhichNosepoke(whenNosepoke);
			// 	whenNosepoke = 0;
			// 	SpeakerPwdAO.on(50);
			// 	delayHK(500);
			// 	bool rewardFlag=false;
			// 	SpeakerPwdAO.off(0);
			// 	delayStart=millis();
			// 	while((millis()-delayStart)<=5000){
			// 		if (LickDI.isOn()){
			// 			volatile unsigned long when = millis() - stateMachineStartTime;
			// 			ReportData(26,1,when);
			// 			LickDI.clear();
			// 			int unsigned randomNumber = random(100);
			// 			if (randomNumber<(unsigned)prob2){
			// 				GiveReward(1);
			// 				rewardFlag=true;
			// 				NosepokeProbIndependentVar.rewardCounter++;
			// 			}
			// 			break;
			// 		}
			// 		else{										// If no lick detected,
			// 			continue;								// no reward obtained.
			// 		}
			// 	}
			// 	if (rewardFlag==false){
			// 		ReportData(86, 1,(millis()-stateMachineStartTime));	
			// 	}
			// 	//break;											// update stop signal
			// }	
			else{
				if (NosepokeProbDependentVar.rewardCounter>1000 || restartSession == true){ //remove reward limit?
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

