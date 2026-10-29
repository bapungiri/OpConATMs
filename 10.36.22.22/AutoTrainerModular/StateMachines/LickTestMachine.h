#ifndef _LickTestMachine_h
#define _LickTestMachine_h
struct LickTestStruct{
	int rewardCounter;
} LickTestVar = {0};

void LickTestMachine() {

	RunStartANDEndStateMachine(&startStateMachine);
	InitializeStateMachine(); // Initialize state machine

	int unsigned randomDelay = 0;
	int delayStart = 0;
	int unsigned lickTimer=0;

	LickTestVar.rewardCounter = 101;
	CamLeftDO.on();
	CamRightDO.on();
	while(1) {
		HouseKeeping();
		if (stateStop) {
			ReportData(63, LickTestVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return;
		}
		else {
			randomDelay = random(10000,30000);
			delayStart = millis();
			while ((millis()-delayStart)<=randomDelay){
				if (LickDI.isOn()) {
					volatile unsigned long when = millis() - stateMachineStartTime;
					ReportData(26, 1, when);
					LickDI.clear();
					SpeakerPwdAO.on(50);
					delayHK(500);
					SpeakerPwdAO.off(0);
					GiveReward(1);
					LickTestVar.rewardCounter++;
					break;
				}
				else if (Nosepoke1DI.isOn()||Nosepoke2DI.isOn()){
					Nosepoke1DI.clear();
					Nosepoke2DI.clear();
					SpeakerPwdAO.on(50);
					delayHK(500);
					SpeakerPwdAO.off(0);
					break;
				}
				else{
					continue; 
				}
			}
			lickTimer = millis();
			SpeakerPwdAO.on(50);
			while ((millis()-lickTimer)<=5000){
				if (LickDI.isOn()){
					LickDI.clear();
					SpeakerPwdAO.off(0);
					GiveReward(1);
					LickTestVar.rewardCounter++;
					break;
				}
				else{
					continue;
				}
			}
			SpeakerPwdAO.off(0);
			LickDI.clear();
			if (LickTestVar.rewardCounter > 100) {
				ReportData(63, LickTestVar.rewardCounter, (millis() - stateMachineStartTime));
				AdvanceCurrentStage();
				EndCurrentStateMachine();
				return;
			}
		}
	}
}

#endif
