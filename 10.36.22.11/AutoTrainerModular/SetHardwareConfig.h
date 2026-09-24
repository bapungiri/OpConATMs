/*
  This file defines hardware pins on microcontroller
*/

#ifndef _SetHardwareConfig_h
#define _SetHardwareConfig_h

// Declare hardware pins
DI_HDW Nosepoke1DI, Nosepoke2DI, LickDI;
DO_HDW  HouseRedDO, HouseGreenDO, HouseBlueDO, CamLeftDO, CamRightDO, WaterDO, IRLightDO, GPIOOutDO;
//AI_HDW LeverAI;
AO_HDW SpeakerPwdAO, SpeakerDacAO;

// Declare interrupt handlers for digital inputs
void Interrupt_Nosepoke1DI(), Interrupt_Nosepoke2DI(), Interrupt_LickDI();

void SetHardwareConfig(){

  // -------------------------------------- DI
  CreateHDW_DI(Nosepoke1DI, "Nosepoke1DI", 21, Interrupt_Nosepoke1DI, CHANGE);
  CreateHDW_DI(Nosepoke2DI, "Nosepoke2DI", 20, Interrupt_Nosepoke2DI, CHANGE);

  CreateHDW_DI(LickDI,  "LickDI",   25, Interrupt_LickDI,  CHANGE);

  // -------------------------------------- DO
  CreateHDW_DO(HouseRedDO,   "HouseRedDO",    3, invertY);
  CreateHDW_DO(HouseGreenDO, "HouseGreenDO",  4, invertY);
  CreateHDW_DO(HouseBlueDO,  "HouseBlueDO",   5, invertY);

  CreateHDW_DO(CamLeftDO,  "CamLeftDO",  2, invertY);
  CreateHDW_DO(CamRightDO, "CamRightDO", 2, invertY);

  CreateHDW_DO(WaterDO,   "WaterDO",   7, invertY);
  CreateHDW_DO(IRLightDO, "IRLightDO",  6, invertY);
  CreateHDW_DO(GPIOOutDO, "GPIOOutDO", 22, invertN);

  // -------------------------------------- AI
  //CreateHDW_AI(LeverAI, "LeverAI", 18, 0.02);
  //LeverAI.enTrigger(RISING, 0.05, saveY);

  // -------------------------------------- AO
  CreateHDW_AO(SpeakerPwdAO, "SpeakerPwdAO", 23);
  SpeakerPwdAO.anWriteFrq(4000); // Sets tone PWM freq to 4kHz (0%= no tone 50%(128) 4kHz buzz)
  SpeakerPwdAO.off(0);

  //CreateHDW_AO(SpeakerDacAO,"SpeakerDacAO",A22);

  // -------------------------------------- Sound Setting
  SetSoundConfig();
};

// -------------------------------------- Interrupt_Nosepoke1DI()
void Interrupt_Nosepoke1DI(){
  volatile unsigned long when = millis()-stateMachineStartTime;
  Nosepoke1DI.value = !Nosepoke1DI.diRead();
  ReportData(Nosepoke1DI.pinNum, Nosepoke1DI.value, when);
  if (!Nosepoke1DI.isOn()){
    Nosepoke1DI.eventTimes[2] = Nosepoke1DI.eventTimes[1];
    Nosepoke1DI.eventTimes[1] = Nosepoke1DI.eventTimes[0];
    Nosepoke1DI.eventTimes[0] = when;
    GPIOOutDO.on();   // R-Pi GPIO High
  }
  else if( Nosepoke1DI.isOn() ){
    GPIOOutDO.off();  // R-Pi GPIO Low
  }
};

// -------------------------------------- Interrupt_Nosepoke2DI()
void Interrupt_Nosepoke2DI(){
  volatile unsigned long when = millis()-stateMachineStartTime;
  Nosepoke2DI.value = !Nosepoke2DI.diRead();
  ReportData(Nosepoke2DI.pinNum, Nosepoke2DI.value, when);
  if (!Nosepoke2DI.isOn()){
    Nosepoke2DI.eventTimes[2] = Nosepoke2DI.eventTimes[1];
    Nosepoke2DI.eventTimes[1] = Nosepoke2DI.eventTimes[0];
    Nosepoke2DI.eventTimes[0] = when;
    GPIOOutDO.on();   // R-Pi GPIO High
  }
  else if( Nosepoke2DI.isOn() ){
    GPIOOutDO.off();  // R-Pi GPIO Low
  }
};

// -------------------------------------- Interrupt_LickDI()
void Interrupt_LickDI(){
  volatile unsigned long when = millis()-stateMachineStartTime;
  LickDI.value = LickDI.diRead();
  //ReportData(LickDI.pinNum, LickDI.value, when); //stopped reporting through this channel because too many events not created by animal 5-1-2023
  if (LickDI.isOn()){
    LickDI.eventTimes[2] = LickDI.eventTimes[1];
    LickDI.eventTimes[1] = LickDI.eventTimes[0];
    LickDI.eventTimes[0] = when;
    GPIOOutDO.on();	//R-Pi GPIO High
  }
  else if (! LickDI.isOn()){
    GPIOOutDO.off();	//R-Pi GPIO Low
  }
};


#endif
