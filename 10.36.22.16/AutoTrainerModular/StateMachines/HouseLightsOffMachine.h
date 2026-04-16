#ifndef _HouseLightsOffMachine_h
#define _HouseLightsOffMachine_h

// -----------------------------------------   HouseLightsOffMachine
void HouseLightsOffMachine(){

  if (ligS.applied)
  {
    InitializeStateMachine();
  }

  HouseRedDO.off();     // House lights off
  HouseGreenDO.off();
  HouseBlueDO.off();

  IRLightDO.on();

  CamLeftDO.off();     // Side camera lights off
  CamRightDO.off();

  if (ligS.applied)
  {
    EndCurrentStateMachine();
  }
  
  ligS.applied = true;
}

#endif
