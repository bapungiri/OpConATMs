#ifndef _NosepokeUNStrMachine_h
#define _NosepokeUNStrMachine_h
#include <stdio.h>

// State machine variable
struct NosepokeUNStrStruct{
	int rewardCounter; // Number of rewards in this sm
	float probArray[4]; // reward probability array
	int sessionNum; // which session number is this 
	int trialCounter; // which trial are you on?
} NosepokeUNStrVar = {0, {0}, 1};

void updateRewProb(){
	//ReportData(45, 1, 0);
	float mu = SessionMean();
	float ports[] = {1.0, 2.0, 3.0, 4.0};
	int sizer = 4;
	permutePorts(ports, sizer);
	for (int i = 0; i < 4; ++i){
		float prob = GenerateProb(mu, ports[i]);
		NosepokeUNStrVar.probArray[i] = prob;
	}
}

void reportProb(){
	float ports[] = {1.0, 2.0, 3.0, 4.0};
	for (int i =0; i<4; ++i){
		ReportData(83, (int)ports[i], (int)(NosepokeUNStrVar.probArray[i]*100));
	}
}

int checkSMStateStop(){
	if (stateStop){
		// End SM
		ReportData(111, NosepokeUNStrVar.trialCounter, (millis()-stateMachineStartTime));
		ReportData(121, NosepokeUNStrVar.sessionNum, (millis()-stateMachineStartTime));
		ReportData(63, NosepokeUNStrVar.rewardCounter, (millis()-stateMachineStartTime));
		EndCurrentStateMachine();
		RunStartANDEndStateMachine(&endStateMachine);
		EndCurrentTrainingProtocol();
		return 1; // return to loop()
	}
	else {
		return 0;
	}
}

int changeBlock(){
	// Initialize variables for changing block
	int min_length = 150;
	int switchProb = 2;
	int unsigned randomDraw = random(100);

	// if performed more than trial limit
	if (NosepokeUNStrVar.trialCounter >= min_length){

		// check if random draw is less than p(switch)
		if (randomDraw < (unsigned) switchProb){
			ReportData(111, NosepokeUNStrVar.trialCounter, (millis()-stateMachineStartTime));
			ReportData(121, NosepokeUNStrVar.sessionNum, (millis()-stateMachineStartTime));
			return 1;
		}

		// otherwise return 0
		else{
			return 0;
		}
	}
	// if less than trial limit return 0.
	else{
		return 0;
	}
}

void NosepokeUNStrMachine(){
	
	RunStartANDEndStateMachine(&startStateMachine); // Start Training protocol

	// Initialize SM
	InitializeStateMachine(); 		

	// Increase session counter
	NosepokeUNStrVar.sessionNum++;				

	// Initialize timers/delays
	int delayStart = 0;

	// Initialize counter
	NosepokeUNStrVar.rewardCounter = 0;

	// Set probabilities for this block/session
	updateRewProb();
	reportProb();
	int n=0;
	float rewardProb;
	int unsigned rewardPercent;

	// Initialize variables
	bool restartBlock = false;

	// Loop until stateStop = 1
	while (1){
		HouseKeeping();

		// check if stateStop is 1 at every moment, and report end of session
		if (checkSMStateStop()) break; 


		// UNStructured Reward Probablities SM
		// detect which nosepoke triggered
		int unsigned whenNosepoke;
		if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn() || Nosepoke3DI.isOn() || Nosepoke4DI.isOn()){
			whenNosepoke = (millis() - stateMachineStartTime);
			uint8_t recordNosepoke[4] = {Nosepoke1DI.diRead(), Nosepoke2DI.diRead(), Nosepoke3DI.diRead(), Nosepoke4DI.diRead()};
				int whichnosepoke[4] = {1,2,3,4};
				for (int i = 0; i<=3; ++i){
					if ((recordNosepoke[i] ==1)){
						n = whichnosepoke[i];
					}
				}
			WhichNosepoke(whenNosepoke);
			whenNosepoke = 0;

			// assign reward probability
			rewardProb = NosepokeUNStrVar.probArray[n-1];
			rewardPercent = (int unsigned)(rewardProb*100);
			ReportData(88, rewardPercent,(millis() - stateMachineStartTime));

			// if licked, give reward acc to reward prob
			bool rewardFlag = false;

			// delay for tone,
			SpeakerPwdAO.on(50);							
			delayHK(500);									
			SpeakerPwdAO.off(0);

			// 5 sec timer for lick detection
			delayStart = millis();							
			while ((millis()-delayStart)<=5000){

				// If lick detected,
				if (LickDI.isOn()){							
					LickDI.clear();

					// Increase trial counter,
					NosepokeUNStrVar.trialCounter++;
					int unsigned randomNumber = random(100);

					// chance that Lick is rewarded and cycle continues
					if (randomNumber < rewardPercent){

						// give reward and report R trial
						GiveReward(1);							
						rewardFlag = true;

						// Increase reward counter
						NosepokeUNStrVar.rewardCounter++;
					}
					else{

						// Report NR trial
						ReportData(-51, 0, (millis()-stateMachineStartTime));
					}
					// break out of 5s while loop.
					break;
				}
				// No lick detected,
				else{

					// no reward obtained (trial missed).
					ReportData(-52, 0, (millis()-stateMachineStartTime));									
					continue;								
				}

			}

			// Report no reward/ miss trials. 
			if (rewardFlag == false){
				ReportData(86, 1, (millis()-stateMachineStartTime));	
			}

			// change block number if required
			if (changeBlock()){
				restartBlock = true;
				// break out of while (1) loop
				break;
			}
		} // if nosepoked
	} // while (1) loop

	if (restartBlock == true){ // restart the session.
		restartBlock = false;
		NosepokeUNStrMachine();
	}
}	

#endif	
