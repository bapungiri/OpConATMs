/*
The hardware library header for Teensy code.
*/

#ifndef _HardwareClass_h
#define _HardwareClass_h

#include "QueueArray.h"

// Define inline function to invert pin status for inverted pins
#define invertPin(a) ((a == HIGH) ? LOW : HIGH)
#define getSign(a) ((a > 0) ? 1 : 0)

// Define additional hardware serial for analog serial
#define anSerial Serial1

// Define constants for analog hardware library
#define analogHDWReadResolution 13
#define analogHDWReadFrequency 1000
#define teensyMaxAnalogVoltage 3.3

// A boolean for status of analog timer interval, ON: True, OFF: False
bool analogIntervalTimerActivated = false;

// Convert analog voltage value to binary and vice versa
#define VoltToBin(x) (int)(x / teensyMaxAnalogVoltage * pow(2, analogHDWReadResolution))
#define BinToVolt(x) (double)(x / pow(2, analogHDWReadResolution) * teensyMaxAnalogVoltage)

// Number of each hardware defined for the box
uint8_t numDigitalInputHDW = 0;  // Number of digital input  devices
uint8_t numDigitalOutputHDW = 0; // Number of digital output devices
uint8_t numAnalogInputHDW = 0;   // Number of analog  input  devices
uint8_t numAnalogOutputHDW = 0;  // Number of analog  output devices

// Hardware type define
typedef enum
{
  DIGITAL,
  ANALOG
} HDWType;

// Hardware interrupt callback function typedef [used only for digital input]
typedef void (*OnInterruptFunc)(void);

// Maximum number of analog hardwares [BE CAREFUL WHEN INCREASING THIS]
#define maxNumDIHDW 20
#define maxNumDOHDW 20
#define maxNumAIHDW 4
#define maxNumAOHDW 20

// Maximum number of analog NON-SAVING triggers per analog channel
#define maxNumAnalogTriggers 16

// Maximum number of analog triggers (RISING or FALLING) for all analog channels
#define maxNumAnalogRisingFallingTriggers (maxNumAnalogTriggers * maxNumAIHDW)

// Total number of enabled analog triggers (RISING or FALLING) for all analog channels
volatile int totalNumEnabledTriggers = 0;

// saveY: Enable saving trigger for this analog channel
// saveN: Do not consider the analog trigger for saving trigger
// FALLING and RISING are defined as 2 and 3 in Teesny library, respectively
#define saveY 4
#define saveN 5

// invertY: Invert digital output pin [High -> Low , Low -> High]
// invertN: Regular digital output pin [High -> High , Low -> Low]
#define invertY 6
#define invertN 7

// Analog output write resolution [Default is 8, from 0 to 255]
uint8_t analogHDWWriteResolution = 8;

// Analog trigger (FALLING or RISING) struct
struct analogTriggerStruct
{
  uint8_t direction;                    // Analog trigger type: FALLING, RISING
  double value;                         // Analog trigger voltage value (0 V - 3.3 V)
  int binValue;                         // Analog trigger binary value
  bool triggered;                       // Analog trigger status: true or false
  bool activated;                       // Analog trigger activation status: true or false
  volatile unsigned long eventTimes[3]; // Buffer array holding trigger times
  volatile int anFlag;                  // Flag for timer interrupt handler
  bool GPIOStatus;                      // GPIO status for analog trigger digitalWrite
  uint8_t GPIOValue;                    // GPIO write value (LOW or HIGH)
};

// Global variables used in analog saving and serial transfer algorithm
volatile uint8_t whoTriggeredSaving = 0; // Indicates which analog channel triggered saving
volatile uint8_t anSavingTriggerON = 0;  // Trigger for saving ON
volatile uint8_t anSavingTriggerOFF = 0; // Trigger for saving OFF
volatile uint8_t anSavingFlag1 = 0;      // Flag for analog saving start and continue
volatile uint8_t anSavingFlag2 = 0;      // Flag for anTimer1
volatile uint8_t anSavingFlag3 = 0;      // Flag for anTimer2
volatile unsigned long anTimer1 = 0;     // Timer 1 : 10 sec
volatile unsigned long anTimer2 = 0;     // Timer 2 :  2 sec

// Queue for report data
#define maxTimeSerialOutHK 5

struct reportStruct
{
  reportStruct() : eventType(-1), value(-1), currentSM(-1), currentTP(-1), smTime(0), nowTime(0), dIntake(-1), wIntake(-1) {}
  int eventType;         // e.g., 99
  int value;             // e.g., LeverAI = 18
  int currentSM;         // e.g., TwoTap = 6
  int currentTP;         // e.g., TwoTapTP = 0
  unsigned long smTime;  // e.g., millis() - smStartTime = 500
  unsigned long nowTime; // e.g., now() = 1515510897
  int dIntake;           // e.g., dailyIntake = 12
  int wIntake;           // e.g., weeklyIntake = 14
};

QueueArray<reportStruct> reportQueue;
reportStruct ReportStr, ReportPrintStr;

// Queue for trial summary data (multi-field single-line records)
struct trialSummaryStruct
{
  trialSummaryStruct() : eventCode(-1), port1Prob(-1), port2Prob(-1), chosenPort(-1), rewarded(0), trialId(0), blockId(0), unstructuredProb(0), sessionStartEpochMs(0), blockStartRelMs(0), trialStartRelMs(0), trialEndRelMs(0) {}
  int eventCode;                   // 200 = lick trial summary, 201 = missed trial summary
  int port1Prob;                   // probability assigned to port 1 for that trial/block
  int port2Prob;                   // probability assigned to port 2 for that trial/block
  int chosenPort;                  // port chosen for the trial (0 if missed)
  int rewarded;                    // 1 rewarded, 0 unrewarded lick, -1 missed (no lick)
  int trialId;                     // lick trial counter value (stable across missed since not incremented)
  int blockId;                     // block number
  int unstructuredProb;            // percent chance environment was unstructured for this subject/config
  uint64_t sessionStartEpochMs;    // absolute epoch ms session start
  unsigned long blockStartRelMs;   // block start time relative to session start (ms)
  unsigned long trialStartRelMs;   // trial start time relative to session start (ms)
  unsigned long trialEndRelMs;     // trial end time relative to session start (ms)
};

QueueArray<trialSummaryStruct> trialSummaryQueue;
trialSummaryStruct TrialSummaryStr, TrialSummaryPrintStr;

// Pointer to read analog circular buffer
unsigned long *anBufferCopy; // e.g., anBufferCopy = LeverAI.anBuffer.readBuffer(); anBufferCopy[0] --> anBufferCopy[2047]

// ================================= Digital Input Hardware Class Declaration
class DI_HDW
{
public:
  DI_HDW();                            // Class constructor
  String pinName;                      // Pin name: lever, lick ...
  uint8_t pinNum;                      // Pin number on microcontroller board
  HDWType pinTyp;                      // Hardware type: Digital or Analog
  uint8_t pinMod;                      // Pin mode (INPUT or OUTPUT)
  OnInterruptFunc pinInterruptHandler; // Pin interrupt handler
  int interruptMode;                   // Pin interrupt mode (HIGH,LOW,RISING,FALLING)

  uint8_t pinTag;                       // Pin tag to report over serial
  volatile unsigned long eventTimes[3]; // Buffer array holding event times (e.g., tap times in TwoTap state machine)

  bool isOn(); // Return True if ON, Return False if not ON

  volatile uint32_t value; // Value of pin (e.g., lever value = 1 or 0)
  void clear();            // Clear pin value

  uint8_t diRead(); // Digital read: read the value of digital pin

  void detachInterruptHandler();                // Detach interrupt handler of pin
  void attachInterruptHandler(OnInterruptFunc); // Attach interrupt handler of pin
};

// ================================= Digital Output Hardware Class Declaration
class DO_HDW
{
public:
  DO_HDW();       // Class constructor
  String pinName; // Pin name: lever, lick ...
  uint8_t pinNum; // Pin number on microcontroller board
  HDWType pinTyp; // Hardware type: Digital or Analog
  uint8_t pinMod; // Pin mode (INPUT or OUTPUT)

  uint8_t pinTag; // Pin tag to report over serial

  bool pinInvertStatus; // Pin invert status
  uint8_t pinOnValue;   // Pin ON value [HIGH in regular case or LOW in inverted case]
  uint8_t pinOffValue;  // Pin OFF value [LOW in regular case or LOW in inverted case]

  void on();   // Turn on digital pin
  void off();  // Turn off digital pin
  bool isOn(); // Return True if ON, Return False if not ON

  volatile uint32_t value; // Value of pin (e.g., lever value = 1 or 0)

  void diWrite(uint8_t); // Digital write: write a value to digital pin (HIGH or LOW)
};

// ================================= Analog Input Hardware Declaration Class
class AI_HDW
{
public:
  AI_HDW();       // Class constructor
  String pinName; // Pin name: lever, lick ...
  uint8_t pinNum; // Pin number on microcontroller board
  HDWType pinTyp; // Hardware type: Digital or Analog
  uint8_t pinMod; // Pin mode (INPUT or OUTPUT)

  uint8_t pinTag; // Pin tag to report over serial

  void GPIOTrigger(uint8_t, uint8_t, uint8_t, double); // GPIO Trigger
  uint8_t GPIOPin;                                     // GPIO pin

  bool isOn(uint8_t, double); // Return True if ON, Return False if not ON
  bool isSaving();            // Return True if SAVING, Return False if not SAVING

  volatile double Value; // Voltage value of analog
  volatile int binValue; // Binary value of analog

  void clear(uint8_t, double); // Clear analog trigger value (direction and voltage value)

  uint8_t numAnalogTriggers; // Number of analog triggers

  analogTriggerStruct analogTrigger[maxNumAnalogTriggers];

  void enTrigger(uint8_t, double, uint8_t); // Enable  RISING or FALLING trigger
  void dsTrigger(uint8_t, double);          // Disable RISING or FALLING trigger

  unsigned long triggerTimes(uint8_t, uint8_t, double); // Trigger times for analog triggers

  void enAllTriggers(); // Enable  all analog FALLING and RISING triggers [and saving]
  void dsAllTriggers(); // Disable all analog FALLING and RISING triggers [and saving]

  void attachInterruptHandler(); // Enable  timer interrupt for analog channels
  void detachInterruptHandler(); // Disable timer interrupt for analog channels

  bool analogSavingActivated;    // Specifies if a saving trigger is activated
  bool analogSavingTriggered;    // Specifies if a saving trigger is triggered
  uint8_t analogSavingDirection; // Specifies saving trigger direction
  double analogSavingValue;      // Specifies saving trigger value
  int analogSavingBinValue;      // Specifies saving trigger binary value

  double noise; // Analog noise voltage
  int binNoise; // Analog noise binary value

  anCircularBuffer anBuffer; // Analog circular buffer

  volatile int anSavingFlagON;  // Flag for saving trigger ON
  volatile int anSavingFlagOFF; // Flag for saving trigger OFF

  int anRead();                 // Read analog value of analog pin
  void anReadAvg(unsigned int); // Average this many readings <Tag 005>
};

// ================================= Analog Output Hardware Declaration Class
class AO_HDW
{
public:
  AO_HDW();       // Class constructor
  String pinName; // Pin name: lever, lick ...
  uint8_t pinNum; // Pin number on microcontroller board
  HDWType pinTyp; // Hardware type: Digital or Analog
  uint8_t pinMod; // Pin mode (INPUT or OUTPUT)

  uint8_t pinTag; // Pin tag to report over serial

  void on(int);  // Write to analog pin in percentage (status: ON)
  void off(int); // Write to analog pin in percentage (status: OFF)
  bool isOn();   // Return True if ON, Return False if not ON

  volatile uint32_t value; // Value of pin (e.g., lever value = 1 or 0)
  void clear();            // Clear pin value

  void anWrite(int);             // Analog write: write a value to analog pin
  uint32_t anWriteRes(uint32_t); // Analog write resolution <Tag 003>
  void anWriteFrq(float);        // Analog write frequency
};

DI_HDW *digitalInHDW[maxNumDIHDW];  // Array of DI_HDW pointers
DO_HDW *digitalOutHDW[maxNumDOHDW]; // Array of DO_HDW pointers
AI_HDW *analogInHDW[maxNumAIHDW];   // Array of AI_HDW pointers
AO_HDW *analogOutHDW[maxNumAOHDW];  // Array of AO_HDW pointers

#endif
