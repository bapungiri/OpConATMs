/*
  This is the main file that initializes serial port, sets initial time,
  updates initial variables, defines hardware configuration, and sets up the
  training schedules. It has a main loop() that runs until the program stops
  and it calls the function for current state machine.
  Version 2.0 , Date: 09/27/2017, Written by Mahmood M. Shad
  Version 1.0: Written by Ed Soucy
*/

#include "HardwareLibrary/AnalogCircularBuffer.cpp" // Define analog circular buffer
#include "HardwareLibrary/HardwareClass.h"          // Declare hardware class
#include "SetStateMachineTP.h"                      // Include SetStateMachineTP file
#include "DeclareVariables.h"                       // Declaration of variables and functions
#include "SetSoundSetting.h"                        // Sound configuration
#include "HardwareLibrary/HardwareClass.cpp"        // Define hardware class
#include "SetHardwareConfig.h"                      // Set hardware configuration
#include "SetInitialVariables.h"                    // Set initial variables
#include "SetInitialAlarms.h"                       // Set initial alarms
#include "GeneralFunctions.h"                       // Define general purpose functions
#include "StateMachines/SpecificFunctions.h"        // Include share function between state machines
#include "StateMachineHeaders.h"                    // Define state machines

// -----------------------------------------   setup()
void setup()
{
  /*
  setup() is run once when the device is powered or rebooted
  */

  randomSeed(analogRead(0)); // Initializes the pseudo-random number generator

  Serial.begin(1000000);   // Initialize main   serial communication
  anSerial.begin(1000000); // Initialize analog serial communication

  WaitForSerialConnections(); // Wait for serial and analog USB serial

  SyncInitialTime();     // Sync time before entering loop()
  SetInitialVariables(); // Set initial variables
  SetHardwareConfig();   // Configure hardware and interrupt handlers
  SetInitialAlarms();    // Set initial alarms
  FinalSetup();          // Send initial information to RPi
}

// -----------------------------------------   loop()
void loop()
{
  /*
  loop() is the main function that keeps repeating until program stops
  */

  HouseKeeping(); // Check alarms by using alarm delay

  stateMachineFunc[currentStateMachine](); // Run the current state machine
}
