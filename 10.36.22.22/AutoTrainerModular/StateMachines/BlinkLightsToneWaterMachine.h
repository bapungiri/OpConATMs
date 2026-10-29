#ifndef _BlinkLightsToneWaterMachine_h
#define _BlinkLightsToneWaterMachine_h

// -----------------------------------------   BlinkLightsToneWaterMachine
void BlinkLightsToneWaterMachine(){

  InitializeStateMachine();

  for(int i=0; i<5; i++){
    HouseRedDO.on();     // House lights on
    HouseGreenDO.on();
    HouseBlueDO.on();
    SpeakerPwdAO.on(50);    // Tone
    delayHK(250);
    SpeakerPwdAO.off(0);	//Tone off
    delayHK(1000);
    HouseRedDO.off();    // House lights off
    HouseGreenDO.off();
    HouseBlueDO.off();
    delayHK(1000);
  }
  HouseRedDO.on();       // House lights on
  HouseGreenDO.on();
  HouseBlueDO.on();
  CamLeftDO.on();        // Side camera lights on
  CamRightDO.on();
  IRLightDO.off();
  GiveReward(1);

  EndCurrentStateMachine();
}

#endif
