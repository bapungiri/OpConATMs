#ifndef _HouseLightsOnMachine_h
#define _HouseLightsOnMachine_h

// -----------------------------------------   HouseLightsOnMachine
void HouseLightsOnMachine(){

  if (ligS.applied)
  {
    InitializeStateMachine();
  }

  HouseRedDO.on();     // House lights on
  HouseGreenDO.on();
  HouseBlueDO.on();

  IRLightDO.off();

  CamLeftDO.off();     // Side camera lights off
  CamRightDO.off();

  if (ligS.applied)
  {
    EndCurrentStateMachine();
  }
  
  ligS.applied = true;
}

#endif
