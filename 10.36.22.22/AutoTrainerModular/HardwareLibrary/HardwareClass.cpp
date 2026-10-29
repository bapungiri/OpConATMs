/*
The hardware library member function definition for Teensy code.
*/

#include "HardwareClass.h"

// -----------------------------------------   DI_HDW class member functions
// DI_HDW class constructor
DI_HDW::DI_HDW()
{
  // Initialize hardware properties
  pinTyp = DIGITAL;
  pinMod = INPUT;
  value = LOW;
}

// DI_HDW class isOn() member function
bool DI_HDW::isOn()
{
  // Return TRUE if the pin is ON
  return (value == HIGH);
}

// DI_HDW class clear() member function
void DI_HDW::clear()
{
  noInterrupts(); // Avoid any interrupts
  value = LOW;    // Reset pin value
  interrupts();   // Re-enable interrupts
}

// DI_HDW class diRead() member function
uint8_t DI_HDW::diRead()
{
  // Read pin digital value
  return digitalRead(pinNum);
}

// DI_HDW class detachInterruptHandler() member function
void DI_HDW::detachInterruptHandler()
{
  detachInterrupt(pinNum);
}

// DI_HDW class attachInterruptHandler() member function
void DI_HDW::attachInterruptHandler(OnInterruptFunc Func)
{
  attachInterrupt(pinNum, Func, interruptMode);
}

// -----------------------------------------   DO_HDW class member functions
// DO_HDW class constructor
DO_HDW::DO_HDW()
{
  // Initialize hardware properties
  pinTyp = DIGITAL;
  pinMod = OUTPUT;
  value = LOW;
}

// DO_HDW class On() member function
void DO_HDW::on()
{
  // Set pin value to high
  diWrite(pinOnValue);
  value = digitalRead(pinNum);

  // Report pin value considering the invert status
  if (pinInvertStatus){
    ReportData(pinNum, invertPin(value), (millis()-stateMachineStartTime));
  }
  else if (! pinInvertStatus){
    ReportData(pinNum, value, (millis()-stateMachineStartTime));
  }

  // Check if imposed value and read value are the same
  if (value != pinOnValue)
  {
    Serial.print("E,Different write and read DO values in on() , pin and now() are: ");
    Serial.print(pinName);
    Serial.print(',');
    Serial.println(now());
  }
}

// DO_HDW class Off() member function
void DO_HDW::off()
{
  // Set pin value to low
  diWrite(pinOffValue);
  value = digitalRead(pinNum);

  // Report pin value considering the invert status
  if (pinInvertStatus){
    ReportData(pinNum, invertPin(value), (millis()-stateMachineStartTime));
  }
  else if (! pinInvertStatus){
    ReportData(pinNum, value, (millis()-stateMachineStartTime));
  }

  // Check if imposed value and read value are the same
  if (value != pinOffValue)
  {
    Serial.print("E,Different write and read DO values in off() , pin and now() are: ");
    Serial.print(pinName);
    Serial.print(',');
    Serial.println(now());
  }
}

// DO_HDW class isOn() member function
bool DO_HDW::isOn()
{
  // Return TRUE if the pin is ON
  return (digitalRead(pinNum) == pinOnValue);
}

// DO_HDW class diWrite() member function
void DO_HDW::diWrite(uint8_t val)
{
  // Read pin digital value
  digitalWrite(pinNum, val);
}

// -----------------------------------------   AI_HDW class member functions
// AI_HDW class constructor
AI_HDW::AI_HDW()
{
  // Initialize hardware properties
  pinTyp = ANALOG;
  pinMod = INPUT;

  // Set noise (voltage and binary values) to 0 (will be overwritten by user)
  noise = 0.0;
  binNoise = 0;

  // Activate saving trigger
  analogSavingActivated = false;
  analogSavingTriggered = false;

  // Reset number of analog rising and falling triggers
  numAnalogTriggers = 0;

  // Reset analog saving flags (these flags are used for loop control logics)
  anSavingFlagON = 0;
  anSavingFlagOFF = 0;
}

// AI_HDW class GPIOTrigger() member function
void AI_HDW::GPIOTrigger(uint8_t GPIOP, uint8_t GPIOValue, uint8_t dir, double val)
{
  GPIOPin = GPIOP;

  // First disable GPIO trigger(s) if they have a same GPIOValue
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if ( analogTrigger[i].GPIOValue == GPIOValue )
    analogTrigger[i].GPIOStatus = false;
  }

  // Search for the trigger with the same value and direction
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if ( (analogTrigger[i].value == val) && (analogTrigger[i].direction == dir) )
    {
      analogTrigger[i].GPIOStatus = true;
      analogTrigger[i].GPIOValue = GPIOValue;
      return;
    }
  }
}

// AI_HDW class isOn() member function
bool AI_HDW::isOn(uint8_t dir, double val)
{
  // Seatch for direction and value, and return TRUE if it is triggered
  bool bool_temp = false;
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if (analogTrigger[i].direction == dir){
      if (analogTrigger[i].value == val)
      {
        bool_temp = analogTrigger[i].triggered;
        break;  // goto return bool_temp
      }
    }
  }
  return bool_temp;
}

// AI_HDW class isSaving() member function
bool AI_HDW::isSaving()
{
  // Return TRUE if the saving flag is activated for the pin
  return analogSavingActivated;
}

// AI_HDW class clear() member function
void AI_HDW::clear(uint8_t dir, double val)
{
  // Search in analog triggers to find the right value and direction
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if (analogTrigger[i].direction == dir){
      if (analogTrigger[i].value == val)
      {
        noInterrupts(); // Avoid any interrupts
        analogTrigger[i].triggered = false;
        interrupts();   // Re-enable interrupts
        break;
      }
    }
  }
}

// AI_HDW class enTrigger() member function
void AI_HDW::enTrigger(uint8_t dir, double val, uint8_t saveFlag)
{
  // First check if the trigger value and direction is already added
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if ( (analogTrigger[i].value == val) && (analogTrigger[i].direction == dir) )
    {
      if (! analogTrigger[i].activated)
      {
        analogTrigger[i].activated = true;
        totalNumEnabledTriggers = min(++totalNumEnabledTriggers, maxNumAnalogRisingFallingTriggers);
      }
      // Activate saving trigger ONLY if asked
      if (saveFlag == saveY)
      {
        analogSavingActivated = true;
        analogSavingDirection = dir;
        analogSavingValue = val;
        analogSavingBinValue = VoltToBin(val);
      }
      return;  // it is already added, return
    }
  }

  // Limit number of analog triggers per channel
  if (numAnalogTriggers >= maxNumAnalogTriggers)
  {
    return;  // do not add more than maxNumAnalogTriggers
  }

  // If the trigger does not exist, add it
  analogTrigger[numAnalogTriggers].direction = dir;
  analogTrigger[numAnalogTriggers].value = val;
  analogTrigger[numAnalogTriggers].binValue = VoltToBin(val);
  analogTrigger[numAnalogTriggers].triggered = false;
  analogTrigger[numAnalogTriggers].activated = true;
  analogTrigger[numAnalogTriggers].anFlag = 0;
  analogTrigger[numAnalogTriggers].GPIOStatus = false;
  numAnalogTriggers++;

  // Update total number of enabled triggers
  totalNumEnabledTriggers = min(++totalNumEnabledTriggers, maxNumAnalogRisingFallingTriggers);

  // Activate saving trigger ONLY if asked
  if (saveFlag == saveY)
  {
    analogSavingActivated = true;
    analogSavingDirection = dir;
    analogSavingValue = val;
    analogSavingBinValue = VoltToBin(val);
  }
}

// AI_HDW class dsTrigger() member function
void AI_HDW::dsTrigger(uint8_t dir, double val)
{
  // Search for the trigger with the same value and direction
  for (int i = 0 ; i<numAnalogTriggers; i++){
    if ( (analogTrigger[i].value == val) && (analogTrigger[i].direction == dir) )
    {
      // Only deactivate if it is already activated
      if (analogTrigger[i].activated)
      {
        analogTrigger[i].activated = false;

        // Update total number of enabled triggers
        totalNumEnabledTriggers = max(0,--totalNumEnabledTriggers);
      }

      // Disable saving if it is attached to this trigger
      if ( analogSavingActivated && (analogTrigger[i].value == analogSavingValue) && (analogTrigger[i].direction == analogSavingDirection) )
      {
        analogSavingActivated = false;
      }
      return; // Do not search all triggers, it is already found
    }
  }
}

// AI_HDW class triggerTimes() member function
unsigned long AI_HDW::triggerTimes(uint8_t indx, uint8_t dir, double val)
{
  unsigned long res = 0;
  if (indx > 2 )
  {
    Serial.print("E,Analog trigger event times is called out of bound.");
  }
  else
  {
    // Find analog trigger first
    for (int i = 0 ; i<numAnalogTriggers; i++){
      if ( (analogTrigger[i].value == val) && (analogTrigger[i].direction == dir) )
      {
        res = analogTrigger[i].eventTimes[indx];
      }
    }
  }

  return res;
}

// AI_HDW class enAllTriggers() member function
void AI_HDW::enAllTriggers()
{
  // Enable all triggers for this hardware
  for (int i = 0; i<numAnalogTriggers; i++){
    if (! analogTrigger[i].activated){
      analogTrigger[i].activated = true;

      // Update total number of enabled triggers
      totalNumEnabledTriggers = min(++totalNumEnabledTriggers, maxNumAnalogRisingFallingTriggers);
    }
  }
}

// AI_HDW class dsAllTriggers() member function
void AI_HDW::dsAllTriggers()
{
  // Disable all triggers for this hardware
  for (int i = 0; i<numAnalogTriggers; i++){
    if (analogTrigger[i].activated){
      analogTrigger[i].activated = false;

      // Update total number of enabled triggers
      totalNumEnabledTriggers = max(0, --totalNumEnabledTriggers);
    }
  }
  // Disable saving as well
  analogSavingActivated = false;
}

// AI_HDW class attachInterruptHandler() member function
void AI_HDW::attachInterruptHandler()
{
  if ( ! analogIntervalTimerActivated)
  {
    analogIntervalTimerActivated = true;
    toDoTimer[0].begin(analogInterruptHandler, analogHDWReadFrequency);
  }
}

// AI_HDW class detachInterruptHandler() member function
void AI_HDW::detachInterruptHandler()
{
  analogIntervalTimerActivated = false;
  toDoTimer[0].end();
}

// AI_HDW class anRead() member function
int AI_HDW::anRead()
{
  // Read analog value of the pin
  return (analogRead(pinNum));
}

// AI_HDW class anReadAvg() member function
void AI_HDW::anReadAvg(unsigned int num)
{
  // Sets analog read average
  analogReadAveraging(num);
}

// -----------------------------------------   RepeatRegularly() for AI_HDW
void analogInterruptHandler(){

  elapsedMicros t44;

  // First read analog and write to buffer for all analog channels
  unsigned long millisValue = millis();
  for (int i = 0; i<numAnalogInputHDW; i++){
    analogInHDW[i]->binValue = analogInHDW[i]->anRead();
    analogInHDW[i]->anBuffer.writeBuffer(analogInHDW[i]->binValue);
  }

  // Write analog values every 1 ms to RPi
  anSerial.print('A');
  anSerial.print(',');
  anSerial.print(millisValue-stateMachineStartTime);
  for (int i = 0; i<numAnalogInputHDW; i++){
    anSerial.print(',');
    anSerial.print(analogInHDW[i]->binValue);
  }
  anSerial.println();

  // Check RISING and FALLING triggers
  if (totalNumEnabledTriggers > 0){

    for (int i = 0; i<numAnalogInputHDW; i++){

      // Check RISING and FALLING triggers if any activated
      for (int j = 0; j<analogInHDW[i]->numAnalogTriggers; j++){

        if (analogInHDW[i]->analogTrigger[j].activated){

          if ( analogInHDW[i]->analogTrigger[j].direction == RISING )
          {
            if (analogInHDW[i]->analogTrigger[j].anFlag == 1)
            {
              if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogTrigger[j].binValue + analogInHDW[i]->binNoise) )
              {
                analogInHDW[i]->analogTrigger[j].triggered = true;
                analogInHDW[i]->analogTrigger[j].anFlag = 0;

                // Updating trigger event times
                analogInHDW[i]->analogTrigger[j].eventTimes[2] = analogInHDW[i]->analogTrigger[j].eventTimes[1];
                analogInHDW[i]->analogTrigger[j].eventTimes[1] = analogInHDW[i]->analogTrigger[j].eventTimes[0];
                analogInHDW[i]->analogTrigger[j].eventTimes[0] = millisValue-stateMachineStartTime;

                // Report analog trigger
                ReportData(analogInHDW[i]->pinNum, analogInHDW[i]->analogTrigger[j].binValue, millisValue-stateMachineStartTime);

                // Digital write GPIO if asked
                if (analogInHDW[i]->analogTrigger[j].GPIOStatus)
                {
                  ReportData(analogInHDW[i]->GPIOPin, analogInHDW[i]->analogTrigger[j].GPIOValue, millisValue-stateMachineStartTime);
                  digitalWrite(analogInHDW[i]->GPIOPin, analogInHDW[i]->analogTrigger[j].GPIOValue);
                }
              }
            }
            else if (analogInHDW[i]->analogTrigger[j].anFlag == 0)
            {
              if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogTrigger[j].binValue - analogInHDW[i]->binNoise) )
              {
                analogInHDW[i]->analogTrigger[j].anFlag = 1;
              }
            }
          }
          else if ( analogInHDW[i]->analogTrigger[j].direction == FALLING )
          {
            if (analogInHDW[i]->analogTrigger[j].anFlag == 1)
            {
              if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogTrigger[j].binValue - analogInHDW[i]->binNoise) )
              {
                analogInHDW[i]->analogTrigger[j].triggered = true;
                analogInHDW[i]->analogTrigger[j].anFlag = 0;

                // Updating trigger event times
                analogInHDW[i]->analogTrigger[j].eventTimes[2] = analogInHDW[i]->analogTrigger[j].eventTimes[1];
                analogInHDW[i]->analogTrigger[j].eventTimes[1] = analogInHDW[i]->analogTrigger[j].eventTimes[0];
                analogInHDW[i]->analogTrigger[j].eventTimes[0] = millisValue-stateMachineStartTime;

                // Report analog trigger
                ReportData(analogInHDW[i]->pinNum, -analogInHDW[i]->analogTrigger[j].binValue, millisValue-stateMachineStartTime);

                // Digital write GPIO if asked
                if (analogInHDW[i]->analogTrigger[j].GPIOStatus)
                {
                  ReportData(analogInHDW[i]->GPIOPin, analogInHDW[i]->analogTrigger[j].GPIOValue, millisValue-stateMachineStartTime);
                  digitalWrite(analogInHDW[i]->GPIOPin, analogInHDW[i]->analogTrigger[j].GPIOValue);
                }
              }
            }
            else if (analogInHDW[i]->analogTrigger[j].anFlag == 0)
            {
              if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogTrigger[j].binValue + analogInHDW[i]->binNoise) )
              {
                analogInHDW[i]->analogTrigger[j].anFlag = 1;
              }
            }
          } // if RISING else FALLING

        } // if activated
      } // for j
    } // for i
  } // if totalNumEnabledTriggers

  // ------ Saving Triggers ------
  // Trigger for saving ON
  for (int i = 0; i<numAnalogInputHDW; i++){
    if (analogInHDW[i]->analogSavingActivated)
    {
      if (analogInHDW[i]->analogSavingDirection == RISING)
      {
        // Trigger for saving ON
        if (analogInHDW[i]->anSavingFlagON == 1)
        {
          if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogSavingBinValue + analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagON = 0;

            anSavingTriggerON = 1;
            anSavingTriggerOFF = 0;
            analogInHDW[i]->analogSavingTriggered = true;
            whoTriggeredSaving = analogInHDW[i]->pinNum;

            break; // As soon as one saving event triggered, exit the FOR loop
          }
        }
        else if (analogInHDW[i]->anSavingFlagON == 0)
        {
          if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogSavingBinValue - analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagON = 1;
          }
        }

        // Trigger for saving OFF
        if (analogInHDW[i]->anSavingFlagOFF == 1)
        {
          if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogSavingBinValue - analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagOFF = 0;

            anSavingTriggerOFF = 1;
            anSavingTriggerON = 0;
            analogInHDW[i]->analogSavingTriggered = false;
          }
        }
        else if (analogInHDW[i]->anSavingFlagOFF == 0)
        {
          if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogSavingBinValue + analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagOFF = 1;
          }
        }
      }
      else if (analogInHDW[i]->analogSavingDirection == FALLING)
      {
        // Trigger for saving ON
        if (analogInHDW[i]->anSavingFlagON == 1)
        {
          if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogSavingBinValue - analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagON = 0;

            anSavingTriggerON = 1;
            anSavingTriggerOFF = 0;
            analogInHDW[i]->analogSavingTriggered = true;
            whoTriggeredSaving = analogInHDW[i]->pinNum;

            break; // As soon as one saving event triggered, exit the FOR loop
          }
        }
        else if (analogInHDW[i]->anSavingFlagON == 0)
        {
          if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogSavingBinValue + analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagON = 1;
          }
        }

        // Trigger for saving OFF
        if (analogInHDW[i]->anSavingFlagOFF == 1)
        {
          if ( analogInHDW[i]->binValue > (analogInHDW[i]->analogSavingBinValue + analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagOFF = 0;

            anSavingTriggerOFF = 1;
            anSavingTriggerON = 0;
            analogInHDW[i]->analogSavingTriggered = false;
          }
        }
        else if (analogInHDW[i]->anSavingFlagOFF == 0)
        {
          if ( analogInHDW[i]->binValue < (analogInHDW[i]->analogSavingBinValue - analogInHDW[i]->binNoise) )
          {
            analogInHDW[i]->anSavingFlagOFF = 1;
          }
        }
      }

    } // if analogSavingActivated
  } // for numAnalogInputHDW

  // First Time Saving Trigger ON
  if (anSavingTriggerON && (! anSavingFlag1) ){
    anSerial.print('V');
    anSerial.println(',');
    ReportData(99, whoTriggeredSaving, millisValue-stateMachineStartTime);

    anSavingTriggerON = 0;
    anSavingFlag1 = 1;
    anSavingFlag2 = 0;
    anSavingFlag3 = 0;
    anTimer1 = 0;
    anTimer2 = 0;

    // Sending analong pin numbers [moved to SendInitialInformation]

  }

  // Continue saving in the same file if (anSavingFlag1 = TRUE)
  if (anSavingFlag1) {

    // Reset timer 1: 10 Sec
    if (! anSavingFlag2){
      anSavingFlag2 = 1;
      anTimer1 = millisValue;
    }

    // Check timer 1 time out
    if ( ((millisValue-anTimer1) > 10000) && (! anSavingTriggerOFF) ){
      anSerial.print('W');
      anSerial.println(',');
      ReportData(98, whoTriggeredSaving, millisValue-stateMachineStartTime);

      anSavingFlag1 = 0;
      anSavingTriggerON = 0;
      anSavingTriggerOFF = 0;
      return;
    }
    else{

      // Reset timer 2: 2 Sec
      if (anSavingTriggerOFF && (! anSavingFlag3) ){
        anSavingFlag3 = 1;
        anTimer2 = millisValue;
      }

      if ( anSavingFlag3 && ((millisValue-anTimer2) > 2000) ){
        anSerial.print('W');
        anSerial.println(',');
        ReportData(98, whoTriggeredSaving, millisValue-stateMachineStartTime);

        anSavingFlag1 = 0;
        anSavingTriggerON = 0;
        anSavingTriggerOFF = 0;
        return;
      }
      else if ( anSavingTriggerON && ((millisValue-anTimer2) <= 2000) ){
        anSavingTriggerON = 0;
        anSavingTriggerOFF = 0;
        anSavingFlag2 = 0;
        anSavingFlag3 = 0;
        if (t44 >= 1000){
          anSerial.print("E,Analog Error > 1ms: ");
          anSerial.print(t44);
          anSerial.println();
        }
        return; // return the function
      }

    }

  } // if (anSavingFlag1)

} // end of analogInterruptHandler

// -----------------------------------------   AO_HDW class member functions
// AO_HDW class constructor
AO_HDW::AO_HDW()
{
  // Initialize hardware properties
  pinTyp = ANALOG;
  pinMod = OUTPUT;
}

// AO_HDW class On(int) member function
void AO_HDW::on(int p)
{
  // Set pin value to HIGH and write percentage of analog hardware resolution
  value = HIGH;
  ReportData(pinNum, value, (millis()-stateMachineStartTime));
  anWrite(round((double)p/100*pow(2,analogHDWWriteResolution)));
}

// AO_HDW class Off(int) member function
void AO_HDW::off(int p)
{
  // Set pin value to LOW and write the analog value based on the percentage
  value = LOW;
  ReportData(pinNum, value, (millis()-stateMachineStartTime));
  anWrite(round((double)p/100*pow(2,analogHDWWriteResolution)));
}

// AO_HDW class isOn() member function
bool AO_HDW::isOn()
{
  // Return TRUE if the pin value is HIGH
  return (value == HIGH);
}

// AO_HDW class clear() member function
void AO_HDW::clear()
{
  noInterrupts(); // Avoid any interrupts
  value = LOW;
  interrupts();   // Re-enable interrupts
}

// AO_HDW class anWrite(int) member function
void AO_HDW::anWrite(int val)
{
  // Write the analog binary value (based on analog write resolution) to the pin
  analogWrite(pinNum, val);
}

// AO_HDW class anWriteRes(uint32_t) member function
uint32_t AO_HDW::anWriteRes(uint32_t bits)
{
  // Change analog write resolution
  return analogWriteRes(bits); // returns prior_resolution
}

// AO_HDW class anWriteFrq(float) member function
void AO_HDW::anWriteFrq(float frequency)
{
  // Change analog write frequency [e.g., SpeakerPwdAO]
  analogWriteFrequency(pinNum, frequency);
}

// -------------------------------------- ClearDigitalInputValues
void ClearDigitalInputValues(){
  for (int i = 0; i<numDigitalInputHDW; i++){
    digitalInHDW[i]->clear();
  }
};

// -------------------------------------- ClearAnalogTriggers
void ClearAnalogTriggers(){
  for (int i = 0; i<numAnalogInputHDW; i++){
    for (int j = 0; j< (analogInHDW[i]->numAnalogTriggers); j++){
      analogInHDW[i]->clear(analogInHDW[i]->analogTrigger[j].direction, analogInHDW[i]->analogTrigger[j].value);
    }
  }
};
