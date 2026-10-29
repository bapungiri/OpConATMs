// New SM - min sess len and random block switching
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

    int unstrprob = 84;
    int strprob = 16;
	int unsigned randomEnvDraw = random(100);

	if (randomEnvDraw < (unsigned)unstrprob){
		int prob1 = (int)(drawProb()*100); 
		ReportData(83, 1, prob1);
		int prob2 = (int)(drawProb()*100); 
		ReportData(83, 2, prob2); 
	}
	else{
		int prob1 = (int)(drawProb()*100);
		int prob2 = 100 - prob1;
		ReportData(83, 1, prob1);
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
							NosepokeProbIndependentVar.rewardCounter++;
						}
					}
						else if(port[1] == 1){
						if (randomNumber<(unsigned)prob2){
							GiveReward(1);
							rewardFlag = true;
							NosepokeProbIndependentVar.rewardCounter++;
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
					

			else{
				if (NosepokeProbIndependentVar.rewardCounter>10000 || restartSession == true){ //remove reward limit?
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