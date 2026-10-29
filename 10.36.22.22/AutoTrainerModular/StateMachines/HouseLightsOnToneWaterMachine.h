#ifndef _HouseLightsOnToneWaterMachine_h
#define _HouseLightsOnToneWaterMachine_h

// -----------------------------------------   HouseLightsOnToneWaterMachine
 void HouseLightsOnToneWaterMachine(){

  InitializeStateMachine();

  HouseRedDO.on();          // House lights on
  HouseGreenDO.on();
  HouseBlueDO.on();
  SpeakerPwdAO.on(50);      // Tone on
  GiveReward(2);
  delayHK(170);               // 250ms total (80 ms used to give 2 water pulses) // ## ASK ED
  SpeakerPwdAO.off(0);      // Tone off
  delayHK(1000);

  IRLightDO.off();

  CamLeftDO.off();     // Side camera lights off
  CamRightDO.off();

  EndCurrentStateMachine();
 }

#endif
