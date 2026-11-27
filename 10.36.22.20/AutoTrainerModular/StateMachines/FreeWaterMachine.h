#ifndef _FreeWaterMachine_h
#define _FreeWaterMachine_h

/*
  Free water: every lick gives one reward pulse, with no task logic (no
  nosepoke, no cue, no trials) and no cap on the session total. A lick less
  than FREE_WATER_GAP_MS after the last reward is ignored, so the lick
  sensor's contact chatter (~16 edges per real lick on some boxes) cannot
  turn one lick into several pulses: at most one pulse per second.

  Run from Special alarms (SetInitialAlarms.h), not as a training stage, so
  the animal's saved stage is untouched and the task resumes as soon as the
  Training alarms are put back.
*/

#define FREE_WATER_GAP_MS 1000

struct FreeWaterStruct{
	int rewardCounter; // Rewards given this session
} FreeWaterVar = {0};

void FreeWaterMachine(){

	RunStartANDEndStateMachine(&startStateMachine); // Session start (light blinks + 1 reward)

	InitializeStateMachine();

	FreeWaterVar.rewardCounter = 0;
	unsigned long lastReward = 0;
	CamLeftDO.on();
	CamRightDO.on();
	LickDI.clear();

	while (1){
		HouseKeeping();
		if (stateStop){
			ReportData(63, FreeWaterVar.rewardCounter, (millis()-stateMachineStartTime));
			CamLeftDO.off();
			CamRightDO.off();
			EndCurrentStateMachine();
			RunStartANDEndStateMachine(&endStateMachine);
			EndCurrentTrainingProtocol();
			return; // return to loop()
		}
		if (LickDI.isOn()){
			LickDI.clear();
			if (FreeWaterVar.rewardCounter == 0 || (millis()-lastReward) >= FREE_WATER_GAP_MS){
				GiveReward(1);
				lastReward = millis();
				FreeWaterVar.rewardCounter++;
			}
		}
	}
}

#endif
