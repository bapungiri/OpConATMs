
> "An animal's eyes have the power to speak a great language." ~Martin Buber

## System Overview

AutoTrainer Modular coordinates behavioral training runs on each Raspberry Pi (“Pi”) and keeps experiment data synchronized with the lab NAS.

- `MainCode.py` compiles/uploads Teensy firmware, runs the training loop, logs session data, and rotates daily output files when configured.
- `PiCamMain.py` records activity-triggered video and stores footage under each subject’s output directory.
- `RemoteJobSubmission.py` deploys updated code to the Pi, creating a timestamped backup of the current codebase before every upload.
- `convertAndTransfer.py` mounts the NAS, converts video when required, transfers completed session artifacts, offloads older Pi backups, and prunes local files based on retention settings.

### Directory Layout on Pi

- `Output_Dir/<Subject_Name>/` (default `/home/pi/ExpData/<Subject>/`)
  - Session data files (`*.dat`, `.trial.csv`, `.log`, rotation markers).
  - `Video/` — per-session video recordings plus associated `*.events` / `*.frames` folders.
- `/home/pi/ATM_backups/<Subject_Name>/<Project>-<timestamp>/` — code snapshots captured before each remote deployment. `convertAndTransfer.py` archives older backups to the NAS once newer ones exist.

### Directory Layout on NAS (mounted at `Mountpoint`)

- `<Mountpoint>/<Subject_Name>/raw_data/`
  - Non-video session files copied from the Pi.
  - `videos/` — converted `*.mp4` files and any `events` / `frames` subdirectories.
- `<Mountpoint>/<Subject_Name>/ATM_backups/<Project>-<timestamp>/`
  - Long-term copies of the Pi’s code backups. The automation only adds to this tree; nothing is deleted from the NAS automatically.

Table of Contents
=================

* [Experiment Setup](#experiment-setup)  
      * [1. Declaration of State Machines and Training   Protocols](#1-declaration-of-state-machines-and-training-protocols)  
      * [2. Set Initial Variables](#2-set-initial-variables)  
      * [3. Set Hardware Configuration](#3-set-hardware-configuration)  
      * [4. Set Initial Alarms](#4-set-initial-alarms)  
      * [5. DI, DO, AI, AO Member Functions and Variables](#5-di-do-ai-ao-member-functions-and-variables)  
         * [5.1. DI Member Functions and Variables (example on LeverDI)](#51-di-member-functions-and-variables-example-on-leverdi)  
         * [5.2. DO Member Functions and Variables (example on WaterDO)](#52-do-member-functions-and-variables-example-on-waterdo)  
         * [5.3. AI Member Functions and Variables (example on LeverAI)](#53-ai-member-functions-and-variables-example-on-leverai)  
         * [5.4. AO Member Functions and Variables (example on SpeakerPwdAO)](#54-ao-member-functions-and-variables-example-on-speakerpwdao)  
      * [6. Writing State Machines](#6-writing-state-machines)  
         * [6.1. BlinkLightsToneWaterMachine State Machine in TwoTap Experiment](#61-blinklightstonewatermachine-state-machine-in-twotap-experiment)  
         * [6.2. NosePokeMachine State Machine in TwoTap Experiment](#62-nosepokemachine-state-machine-in-twotap-experiment)  
      * [7. Submit OpCon Experiments Remotely](#7-submit-opcon-experiments-remotely)  
         * [7.1. Install Python and required libraries](#71-install-python-and-required-libraries)  
         * [7.2. Define experiment settings](#72-define-experiment-settings)  
         * [7.3. Submit OpCon job remotely](#73-submit-opcon-job-remotely)  
         * [7.4. Get job results remotely](#74-get-job-results-remotely)  
* [Tags](#tags)  
* [Storage Monitoring (RPi)](#storage-monitoring-rpi)  

## Experiment Setup

#### 1. Declaration of State Machines and Training Protocols

In `SetStateMachineTP.h` file, specify the following parameters,

```c++
#define numStates           15            // Number of state machines
#define numTrainingProtocol  1            // Number of training protocols
#define maxNumStage          7            // Maximum number of stages in training protocols
```

The description of parameters is written in front of them.
Next, specify name of state machines (SM) as the following,

```c++
#define FOREACH_STATEMACHINE(SM)             \
        SM(NosePoke)                         \
        SM(ToneConditioning)                 \
        SM(ToneTapTraining)                  \
        SM(TapTraining)                      \
        SM(TapProb60)                        \
        SM(TapProb30)                        \
        SM(TwoTap)                           \
        SM(TapNonSession)                    \
        SM(DailyWater)                       \
        SM(WeeklyWater)                      \
        SM(HouseLightsOn)                    \
        SM(HouseLightsOff)                   \
        SM(HouseLightsOnToneWater)           \
        SM(BlinkLightsToneWater)             \
        SM(DoNothing)                        \
```

In the above code snippet, the first SM is `NosePoke` and the last one is `DoNothing`.
The state machine `DoNothing` should always be listed as one of the state machines.

Next, specify the training protocols (TP) with the defined SMs as the following,

```c++
stateMachine trainingProtocol [numTrainingProtocol][maxNumStage][2] =  {
// Training protocol #1, id = 0
{
{NosePoke,               TapNonSession},
{ToneConditioning,       TapNonSession},
{ToneTapTraining,        TapNonSession},
{TapTraining,            DoNothing},
{TapProb60,              DoNothing},
{TapProb30,              DoNothing},
{TwoTap,                 DoNothing}
},
// Training protocol #2, id = 1
/*{
{NosePoke,               TapNonSession},
{ToneConditioning,       TapNonSession},
{ToneTapTraining,        TapNonSession},
{TapTraining,            DoNothing},
{TapProb60,              DoNothing},
{TapProb30,              DoNothing},
{TwoTap,                 DoNothing}
},*/
};
```

In the above code snippet, there are two TPs with `id=0` and `id=1`.
Each TP has two columns,

- The first column is the list of stages
(e.g. the first stage in the first TP is `NosePoke` and the last stage is `TwoTap`).
- The second column is the list of non-session SMs associated with each stage.
For example, the subject will enter the `TapNonSession` SM at the end of training session in
`NosePoke` stage. If a stage does not have any non-session SM, simply put `DoNothing` SM.

The second TP is commented out and can be defined based on user specified SMs.

**Note** Since a 3D array is used for definition of TP, the
length of each TP should be the same. If number of stages are not the same, scale all TPs
with the one with most SMs, and use `DoNothing` to match other TP length.

In the `StateMachineHeaders.h` file, the header file for each SM in
`StateMachines` folder will be included automatically upon experiment submission.

The definition of each state machine is explained in the next sections.


#### 2. Set Initial Variables

In `SetInitialVariables.h` file, specify the following,


```c++
// Current training protocol [index=0,1,2,...]
currentTrainingProtocol  =  0;

// Current stage of current training protocol [index=0,1,2,...]
currentStage[currentTrainingProtocol] = 0;

// Current state machine of current stage of current training protocol
currentStateMachine  = trainingProtocol[currentTrainingProtocol][currentStage[currentTrainingProtocol]][1];

dailyQuota   =  1500;   // Daily quota
weeklyQuota  = 10500;   // Weekly quota
rewardTime   =    60;   // Reward time in microsecond
```

Note the following,
- The default current TP (`currentTrainingProtocol`) is 0.
- The default current stage (`currentStage`) of current TP is 0.
- The default current SM (`currentStateMachine`) of current stage of current TP is the associated non-session SM.
- The `dailyQuota` is the quota for the number of reward pulses per day.
- The `weeklyQuota` is the weekly reward quota (in number of pulses).
- The `rewardTime` is the reward delivery time in microsecond (ms). Use calibration to find the accurate timing.

#### 3. Set Hardware Configuration

In `SetHardwareConfig.h` file, specify hardware configurations. There are four
different hardware types,
- Digital Input (DI)
- Digital Output (DO)
- Analog Input (AI)
- Analog Output (AO)

**Digital Input (DI)**:

For a DI hardware (e.g. `LeverDI`), first declare it at the top of
 `SetHardwareConfig.h` file as,

```c++
DI_HDW LeverDI;
```

Then use the following function to define its details,

```c++
CreateHDW_DI(LeverDI, "LeverDI", 19, Interrupt_LeverDI, CHANGE);
```

where,

- `LeverDI` is the variable name of the DI hardware.
- `"LeverDI"` is the name (string) of the DI hardware.
- `19` is the pin number of the DI hardware on the Teensy board.
- `Interrupt_LeverDI` is the interrupt handler for the DI hardware.
- `CHANGE` is the interrupt mode for the DI hardware (other cases: `RISING`, `FALLING`).

The interrupt handler should be declared at the top of
 `SetHardwareConfig.h` file as,

```c++
void Interrupt_LeverDI();
```

and define it at the end of `SetHardwareConfig.h` file as,

```c++
 void Interrupt_LeverDI(){
   volatile unsigned long when = millis()-stateMachineStartTime;
   LeverDI.value = LeverDI.diRead();
   ReportData(LeverDI.pinNum, LeverDI.value, when);
   if (LeverDI.isOn()){
     LeverDI.eventTimes[2] = LeverDI.eventTimes[1];
     LeverDI.eventTimes[1] = LeverDI.eventTimes[0];
     LeverDI.eventTimes[0] = when;
   }
 };
```

In the above interrupt handler,
- First the time of the hardware interrupt is logged.
- The value of the DI hardware is read.
- The value of the DI hardware is reported to serial output.
- The last three values of the DI hardware are logged.


**Digital Output (DO)**:

For a DO hardware (e.g. `HouseRedDO`), first declare it at the top of
  `SetHardwareConfig.h` file as,

```c++
DO_HDW HouseRedDO;
```

Then use the following function to define its details,

```c++
CreateHDW_DO(HouseRedDO, "HouseRedDO", 5, invertY);
```

where,

- `HouseRedDO` is the variable name of the DO hardware.
- `"HouseRedDO"` is the name (string) of the DO hardware.
- `5` is the pin number of the DO hardware on the Teensy board.
- `invertY` indicates whether the DO hardware is inverted or not.

**Analog Input (AI)**:

For a AI hardware (e.g. `LeverAI`), first declare it at the top of
  `SetHardwareConfig.h` file as,

```c++
AI_HDW LeverAI;
```

Then use the following function to define its details,

```c++
CreateHDW_AI(LeverAI, "LeverAI", 18, 0.02);
```

where,

- `LeverAI` is the variable name of the AI hardware.
- `"LeverAI"` is the name (string) of the AI hardware.
- `18` is the pin number of the AI hardware on the Teensy board.
- `0.02` is the noise level of the AI hardware in volt.

To define AI triggers, use the following function,

```c++
LeverAI.enTrigger(RISING, 0.05, saveY);
```

where the AI trigger is set to `RISING` mode (or `FALLING`) and the trigger base
is `0.05` volt. The `saveY` flag enables analog file saving with this trigger.

**Analog Output (AO)**:

For a AO hardware (e.g. `SpeakerPwdAO`), first declare it at the top of
  `SetHardwareConfig.h` file as,

```c++
AO_HDW SpeakerPwdAO;
```

Then use the following function to define its details,

```c++
CreateHDW_AO(SpeakerPwdAO, "SpeakerPwdAO", 20);
```

where,

- `SpeakerPwdAO` is the variable name of the AO hardware.
- `"SpeakerPwdAO"` is the name (string) of the AO hardware.
- `20` is the pin number of the AO hardware on the Teensy board.

#### 4. Set Initial Alarms

In `SetInitialAlarms.h` file, specify initial alarms. Alarms define schedule for
training and other user-defined activities. There are four type of alrams,

1. `Training`: regular training session.
2. `Special`: special session (e.g., daily water or weekly water)
3. `Utility`: service state machines (e.g., HouseLightsOn, HouseLightsOff, ...)
4. `Disable`: disable current active alarm

The format of the daily alarms is,

```c++
SetDailyAlarms(HH, MM, SS, AlarmType, TP, starting_SM,  ending_SM, special_SM);
```

where,
- `HH`, `MM`, and `SS` are the hour (24 HR format) , minute, and second for alarm time.
- `AlarmType` is the type of alarm: `Training`, `Special`, `Utility`, `Disable`
- `TP` is the index of training protocol (0,1,2, ...).
- `starting_SM` is the starting state machine in the session.
- `ending_SM` is the ending state machine in the session.
- `special_SM` is the special state machine in the session.

In the following example for `Training` alarm,

```c++
SetDailyAlarms( 2, 30,  0, Training, 0, BlinkLightsToneWater, HouseLightsOff, DoNothing);
SetDailyAlarms( 3, 10,  0, Disable, -1, DoNothing, DoNothing, DoNothing);
```

The first line defines a `Training` alarm at `02:30:00 AM` that starts with
`BlinkLightsToneWater` SM and ends with `HouseLightsOff` SM. The training protocol
is `0` and the code will run the SM of the current stage of the TP=`0`.
The alarm ends on `03:10:00 AM` with `Disable` alarm. Since the TP for `Disable`
alarm is set to `-1`, it does not change the current TP. Therefore, after the
`Disable` alarm, the code will run the non-session SM of the current stage of
the current TP.

In the following example for `Special` alarm,

```c++
SetDailyAlarms( 5,  0,  0, Special, -1, HouseLightsOnToneWater, HouseLightsOff, DailyWater);
SetDailyAlarms( 5, 30,  0, Disable, -1, DoNothing, DoNothing, DoNothing);
```

The TP for the start and end of alarm is `-1`. It means that the `Special` alarm
does not change the current TP. The special SM in this example is `DailyWater`.

In the following example for `Utility` alarm,

```c++
SetDailyAlarms( 6,  0,  0, Utility, -1, HouseLightsOn,  DoNothing, DoNothing);
```

There is not `Disable` alarm since it is designed to run quickly without changing the
current stage or current TP.

Another type of alarm is a weekly alarm. For example in the following example,

```c++
SetWeeklyAlarms(dowMonday, 4,  0,  0, Special, -1, HouseLightsOnToneWater, HouseLightsOff, WeeklyWater);
SetWeeklyAlarms(dowMonday, 5,  0,  0, Disable, -1, DoNothing, DoNothing, DoNothing);
```

A weekly alarm is set at `04:00:00 AM` on `Monday`. It will stop at `05:00:00 AM`. Since the TP
is `-1`, this alarm does not change the current TP.

**Note**: More alarm types will be added in the next software releases.


#### 5. DI, DO, AI, AO Member Functions and Variables

There are several variables and functions for each hardware class that makes the hardware library very flexible and custom-designed to our needs. The following lists variables/functions for each hardware class.

##### 5.1. DI Member Functions and Variables (example on LeverDI)

**Important Members**

- `LeverDI.isOn()`                    | Return True if ON, Return False if OFF
- `LeverDI.clear()`                   | Clear pin value (value = LOW)
- `LeverDI.eventTimes[3]`             | Buffer array holding the last three ON event times
- `LeverDI.detachInterruptHandler()`  | Detach interrupt handler of pin
- `LeverDI.attachInterruptHandler(LeverDI.pinInterruptHandler)` | Attach interrupt handler of pin

**Other Members**

- `LeverDI.pinName`                   | Pin name (e.g., LeverDI, LickDI)
- `LeverDI.pinNum`                    | Pin number on Teensy board
- `LeverDI.pinTyp`                    | Hardware type (Digital or Analog)
- `LeverDI.pinMod`                    | Pin mode (INPUT or OUTPUT)
- `LeverDI.pinInterruptHandler`       | Pin interrupt handler
- `LeverDI.interruptMode`             | Pin interrupt mode (HIGH, LOW, RISING, FALLING)
- `LeverDI.pinTag`                    | Pin tag (for future consideration)
- `LeverDI.diRead()`                  | Read the value of digital pin
- `LeverDI.value`                     | Value of pin (1: HIGH, 0: LOW)

##### 5.2. DO Member Functions and Variables (example on WaterDO)

**Important Members**

- `WaterDO.on()`                 | Turn on digital pin
- `WaterDO.off()`                | Turn off digital pin
- `WaterDO.isOn()`               | Return True if ON, Return False if OFF
- `WaterDO.clear()`              | Clear pin value (LOW in regular pin or HIGH in inverted pin)

**Other Members**

- `WaterDO.pinName`              | Pin name (e.g., WaterDO)
- `WaterDO.pinNum`               | Pin number on Teensy board
- `WaterDO.pinTyp`               | Hardware type (Digital or Analog)
- `WaterDO.pinMod`               | Pin mode (INPUT or OUTPUT)
- `WaterDO.pinTag`               | Pin tag (for future consideration)
- `WaterDO.pinInvertStatus`      | Pin invert status [True: Inverted, False: Not Inverted]
- `WaterDO.pinOnValue`           | Pin ON value [HIGH in regular pin or LOW in inverted pin]
- `WaterDO.pinOffValue`          | Pin OFF value [LOW in regular pin or LOW in inverted pin]
- `WaterDO.value`                | Value of pin (1: HIGH, 0: LOW)
- `WaterDO.diWrite()`            | Write a value to digital pin (HIGH or LOW)

##### 5.3. AI Member Functions and Variables (example on LeverAI)

**Important Members**

- `LeverAI.isOn(TriggerDir, TriggerValue)`                            | Return True if AI trigger ON, Return False if OFF
- `LeverAI.clear(TriggerDir, TriggerValue)`                           | Clear AI trigger value given direction and voltage value
- `LeverAI.enTrigger(TriggerDir, TriggerValue, SaveFlag)`             | Enable  RISING or FALLING AI trigger with voltage value (SaveFlag:True activates AI saving for this AI pin)
- `LeverAI.dsTrigger(TriggerDir, TriggerValue)`                       | Disable RISING or FALLING AI trigger
- `LeverAI.triggerTimes(Index, TriggerDir, TriggerValue)`             | Last three trigger ON times for analog triggers (Index=0,1,2)
- `LeverAI.GPIOTrigger(GPIOPin, GPIOValue, TriggerDir, TriggerValue)` | GPIO Trigger (Write to RPi GPIO once AI trigger is activated)
- `LeverAI.anBuffer.readBuffer()`;                                    | Read analog buffer
- `LeverAI.anBuffer.getNumNewItems()`;                                | Report number of new elements since previous reading

**Other Members**

- `LeverAI.pinName`                                                   | Pin name (e.g., LeverAI)
- `LeverAI.pinNum`                                                    | Pin number on Teensy board
- `LeverAI.pinTyp`                                                    | Hardware type (Digital or Analog)
- `LeverAI.pinMod`                                                    | Pin mode (INPUT or OUTPUT)
- `LeverAI.pinTag`                                                    | Pin tag (for future consideration)
- `LeverAI.GPIOPin`                                                   | GPIO pin number
- `LeverAI.isSaving()`                                                | Return True if the AI saving is activated for this AI pin
- `LeverAI.Value`                                                     | Voltage value of this AI pin
- `LeverAI.binValue`                                                  | Binary value of this AI pin (add noInterrupts before reading)
- `LeverAI.numAnalogTriggers`                                         | Number of AI triggers for this AI pin
- `LeverAI.enAllTriggers()`                                           | Enable  all AI FALLING and RISING triggers [and saving] for this AI pin
- `LeverAI.dsAllTriggers()`                                           | Disable all analog FALLING and RISING triggers [and saving] for this AI pin
- `LeverAI.attachInterruptHandler()`                                  | Enable  timer interrupt for all AI channels
- `LeverAI.detachInterruptHandler()`                                  | Disable timer interrupt for all AI channels
- `LeverAI.analogSavingActivated`                                     | True: A saving trigger is activated for this AI pin
- `LeverAI.analogSavingTriggered`                                     | True: A saving trigger is triggered for this AI pin
- `LeverAI.analogSavingDirection`                                     | Specifies saving trigger direction (FALLING, RISING)
- `LeverAI.analogSavingValue`                                         | Specifies saving trigger voltage value
- `LeverAI.analogSavingBinValue`                                      | Specifies saving trigger binary value
- `LeverAI.noise`                                                     | Analog noise voltage for this AI pin
- `LeverAI.binNoise`                                                  | Analog noise binary value for this AI pin
- `LeverAI.anBuffer`                                                  | Analog circular buffer [size: 2048]
- `LeverAI.anRead()`                                                  | Read analog value of this AI analog pin
- `LeverAI.anReadAvg()`                                               | Average this many readings <Tag 005>

**AI Usage Example**

The most important part in AI channel is to define AI triggers with direction (`FALLING` or `RISING`) and voltage value (between 0-3.3 V) and to use the AI values in the circular buffer. Few examples,

- Define an AI trigger with `RISING` direction and voltage value of `1.2`,

  ```c++
  LeverAI.enTrigger(RISING, 1.2, saveN);
  ```

- Disable the above AI trigger,
  ```c++
  LeverAI.dsTrigger(RISING, 1.2);
  ```

- Define an AI trigger with `RISING` direction and voltage value of `1.2`. Also activate saving on this AI trigger,

  ```c++
  LeverAI.enTrigger(RISING, 1.2, saveY);
  ```

- Check if an AI trigger is triggered (do not forget to clear it),

  ```c++
  if ( LeverAI.isOn(RISING, 1.2) ){
    LeverAI.clear(RISING, 1.2);
    // statements
  }
  ```

- Access the last three times that an AI trigger was triggered,

  ```c++
  LeverAI.triggerTimes(0, RISING, 1.2);  // Latest trigger time [t1]
  LeverAI.triggerTimes(1, RISING, 1.2);  // Trigger at t1 < t1
  LeverAI.triggerTimes(2, RISING, 1.2);  // Trigger at t3 < t2
  ```

- Attach an RPi GPIO to an existing AI trigger. A `HIGH` value will be written to RPi GPIO whenever the AI trigger is triggered. This is used for Pi Camera to record video files. In the following code, the first argument is the GPIO hardware variable, the second argument is the digital write value (`HIGH`) to be written to RPi GPIO once the AI trigger is triggered. The last two arguments are the AI trigger direction and value, respectively.

  ```c++
  LeverAI.GPIOTrigger(GPIOOutDO, HIGH, RISING, 1.2);
  ```

- The analog values are written in a circular buffer (default size: 2048). To access the buffer, we can read the whole buffer. If user is interested in number of new writes to analog buffer, the `getNumNewItems` function can be called as following. The `anBufferCopy` variable is pre-defined and can be used throughout the code.

  ```c++
  anBufferCopy = LeverAI.anBuffer.readBuffer();
  int n;
  n = LeverAI.anBuffer.getNumNewItems();
  ```


##### 5.4. AO Member Functions and Variables (example on SpeakerPwdAO)

**Important Members**

- `SpeakerPwdAO.on(P)`             | Set pin value to HIGH and write percentage of analog hardware resolution
- `SpeakerPwdAO.off(P)`            | Set pin value to LOW and write percentage of analog hardware resolution
- `SpeakerPwdAO.isOn()`            | Return True if ON, Return False if not
- `SpeakerPwdAO.clear()`           | Clear pin value (set it to LOW)

**Other Members**

- `SpeakerPwdAO.pinName`      | Pin name (e.g., SpeakerPwdAO)
- `SpeakerPwdAO.pinNum`       | Pin number on Teensy board
- `SpeakerPwdAO.pinTyp`       | Hardware type (Digital or Analog)
- `SpeakerPwdAO.pinMod`       | Pin mode (INPUT or OUTPUT)
- `SpeakerPwdAO.pinTag`       | Pin tag (for future consideration)
- `SpeakerPwdAO.value`             | Value of pin (HIGH:ON, LOW:OFF)
- `SpeakerPwdAO.anWrite(V)`        | Write the analog binary value (based on analog write resolution) to the pin [Default: 0-255]
- `SpeakerPwdAO.anWriteRes(R)`     | Change analog write resolution [Default = 8, from 0 to 255] <Tag 003>
- `SpeakerPwdAO.anWriteFrq(F)`     | Change analog write frequency



#### 6. Writing State Machines

In this section we review few different state machines (SM) and discuss the general format of state machines.
The smallest unit in the code is a state machine. The Arduino main loop repeats forever and runs the current state machine. Based on the
alarm and subject activity, the program changes the current state machine. It is very important to distinguish different concepts in the code:

- `currentStateMachine`: Is the current state machine in the program. The Arduino main loop runs the function associated with this SM.
- `currentTrainingProtocol`: Is the current training protocol (TP). The training alarm will pick the current stage of the current TP.
- `currentStage[currentTrainingProtocol]`: Is the current stage of the current TP.
- The non-session SM associated with the current stage is: `trainingProtocol[currentTrainingProtocol][currentStage[currentTrainingProtocol]][1]`

The following functions are utilized to transition stages and state machines,

- `EndCurrentStateMachine()`: Ends current state machine and sets it to next SM. Alarms and several functions can change next SM.

- `EndCurrentTrainingProtocol()`: Ends current training protocol and sets it to next TP. Alarms and several functions can change next TP.

- `AdvanceCurrentStage()`: Advance current stage of current TP. This function changes the current SM to next SM by default. Call `AdvanceCurrentStage(changeSMFlag=false)` with `changeSMFlag` set to `false` if you wish to just advance the stage without affecting the next SM. This situation can happen if you call this function at the end of SM.

- `GetUpcomingNonSessionStateMachine()`: Gets the upcoming non-session SM and sets it as next SM. This happens in `DailyWater` SM where the session may end before the `disable` alarm is called. This function gets the TP in the upcoming `disable` alarm and finds the associated non-session SM of the current stage of this TP.

- `GetCurrentNonSessionStateMachine()`: Sets the next SM to the current non-session SM of the current stage of the current TP. For example in TwoTap experiment, this function is called at the end of `TapNonSessionMachine` SM to get the next SM.

The following functions are called in most state machines:

- `InitializeStateMachine()`: This function clears all DI values, clears all AI triggers, resets SM state time in milliseconds by using `stateMachineStartTime` variable, resets SM entry time in seconds (time from start of experiment), and reports to serial the start of SM.

- `RunStartANDEndStateMachine(SM)`: The alarms may start with a starting or an ending SM. This function is called at the beginning and the end of SM to check if there is any starting or ending SM is available to run. For example, for regular training session in TwoTap experiment, `BlinkLightsToneWater` and `HouseLightsOff` state machines are called at the beginning and end of session, respectively.

- `GiveReward(1)`: Gives 1 pulse of reward (e.g., water in TwoTap).

- `HouseKeeping()`: This function is called at every trial in each SM. It is essential part of the program since it checks the alarms, sends report data to RPi over USB serial, checks for any written data in USB serial by RPi (e.g., time sync value), and sends health message to RPi every 60 minutes (can be changed by user).

- `delayHK(210)`: This is a custom-designed delay function where during the delay time, the program sends the report data to RPi over USB serial and checks for any written data in USB serial by RPi (e.g., time sync value)

- `ReportData(TYPE, VALUE, (millis()-stateMachineStartTime))`: This function reports an event to RPi. It adds the report to a queue, and the queue is emptied at different places in the program. For hardware related events, the `TYPE` is pin number, `VALUE` is the value associated with the hardware (e.g., 1:HIGH, 0:LOW). Other codes for different event types are explained in a separate Excel file. Users should use this function to report different data to RPi and use of `Serial.print()` or `Serial.println()` functions should be **avoided**.

Now let's review few state machines,

##### 6.1. BlinkLightsToneWaterMachine State Machine in TwoTap Experiment

The `BlinkLightsToneWaterMachine` SM is called as the starting SM in the regular training sessions in the TwoTap experiment. The body of SM is listed below,

```c++
void BlinkLightsToneWaterMachine(){

  InitializeStateMachine();

  for(int i=0; i<5; i++){
    HouseRedDO.on();        // Red house lights on
    HouseGreenDO.on();      // Green house lights on
    HouseBlueDO.on();       // Blue house lights on
    SpeakerPwdAO.on(50);    // Tone on
    delayHK(250);           // Delay for 250 milliseconds
    SpeakerPwdAO.off(0);    // Tone off
    delayHK(1000);          // Delay for 1000 milliseconds
    HouseRedDO.off();       // Red house lights off
    HouseGreenDO.off();     // Green house lights off
    HouseBlueDO.off();      // Blue house lights off
    delayHK(1000);
  }
  HouseRedDO.on();          // Red house lights on
  HouseGreenDO.on();        // Green house lights on
  HouseBlueDO.on();         // Blue house lights on
  CamLeftDO.on();           // Left side camera lights on
  CamRightDO.on();          // Right side camera lights on
  IRLightDO.off();          // IR lights off
  GiveReward(1);            // Give 1 pulse of reward (water here)

  EndCurrentStateMachine(); // End the current SM and get the next SM
}
```

As the comments in the code snippet explain the SM, for 5 times, we turn ON house lights, turn ON speaker for 250 ms, wait for 1 sec and turn OFF lights, and wait for 1 sec before next iteration in the FOR loop. At the end, the house lights and side camera lights are set to ON, IR light is set to OFF, and 1 pulse of reward (water here) is given.

##### 6.2. NosePokeMachine State Machine in TwoTap Experiment

```c++
void NosePokeMachine(){

  RunStartANDEndStateMachine(&startStateMachine);

  InitializeStateMachine();   // Initialize state machine (entryTime, stateMachineStartTime ...)

  NosePokeVar.rewardCounter = 0;

  // Loop forever until stateStop = 1
  while (1){
    HouseKeeping();
    if(stateStop){
      ReportData(63, NosePokeVar.rewardCounter, (millis()-stateMachineStartTime));
      EndCurrentStateMachine();
      RunStartANDEndStateMachine(&endStateMachine);
      EndCurrentTrainingProtocol();
      return; // Return to loop()
    }
    else{     // Run state machine
      if (LickDI.isOn()){
        LickDI.clear();
        SpeakerPwdAO.on(50);
        GiveReward(1);
        delayHK(210);     // 40 ms used to give 2 water pulses (250-40 = 210)
        SpeakerPwdAO.off(0);
        NosePokeVar.rewardCounter++;
        if (NosePokeVar.rewardCounter>30){
          ReportData(63, NosePokeVar.rewardCounter, (millis()-stateMachineStartTime));
          AdvanceCurrentStage();
          EndCurrentStateMachine();
          return;  // Return to loop()
        }
      }
    }
  } //  End of while(1)
}
```

As the above code snippet explains the flow of state machine, these are the steps in this SM,

1. Check for any starting state machine to run at the beginning.  
2. Initialize state machine by calling `InitializeStateMachine()` function.  
3. Set initial values of global and local variables.  
4. Repeat the following loop forever,    
   4.1. Call `HouseKeeping()` function (its role is explained above)  
   4.2. If `stateStop` is set to `true` by alarms, then,      
        4.2.1. Report ending of state machine along with number of rewards in this SM  
        4.2.2. End current state machine and set the `currentStateMachine` to `nextStateMachine`  
        4.2.3. Check for any ending state machine to run  
        4.2.4. End current training protocol  
        4.2.5. Return to Arduino main loop  
   4.3. If `LickDI` is pressed    
        4.3.1. Clear `LickDI` value  
        4.3.2. Turn on speaker `SpeakerPwdAO` with 50% load  
        4.3.3. Give 1 pulse of reward  
        4.3.4. Delay for 210 ms  
        4.3.5. Turn off speaker `SpeakerPwdAO` with 0% load  
        4.3.6. Increment the reward  
        4.3.7. If number of reward is greater than 30, then,  
               4.3.7.1. Report ending of state machine along with number of rewards in this SM  
               4.3.7.2. Advance the stage to next stage in the current training protocol  
               4.3.7.3. End current state machine and set the `currentStateMachine` to `nextStateMachine`  
               4.3.7.4. Return to Arduino main loop  


While it is not required to follow the structure for writing state machines, the following are A MUST,

- The `HouseKeeping()` function should be called in each trial.
- The value of `stateStop` variable should be checked in each trial to check for any activated alarm.

Other state machines follow similar procedure.


#### 7. Submit OpCon Experiments Remotely

##### 7.1. Install Python and required libraries

The `RemoteJobSubmission.py` file can be utilized to submit the OpCon job remotely. The `GetJobResult.py` code can be used to download experiment events, watchdog reports, and analog output files.

First user needs to install following programs and libraries,

- Install Python 3 from [Python website](https://www.python.org/downloads/) or use [Anaconda](https://www.anaconda.com/download).
- Install `paramiko` module for Python. Use `pip install paramiko` or `conda install paramiko`.

##### 7.2. Define experiment settings

Before submitting the job or downloading the result, user should modify `userInfo.in` and customize it for his/her experiment. The `userInfo.in` file contains the following settings,

```
# ---- Box & Experiment Information
RPi_IP               = 140.247.178.XXX
Box_Name             = TestBox
Subject_Name         = MegaR
Daily_Water          = 1500
Water_Minimum        = 75%
TimeSyncFreq         = 24HR

# ---- Result File(s) Settings
Result_Path          = D:\Results\
Remote_File_Exts     = *.dat, *.log
Get_Analog_Results           = True
Delete_Old_Results       = False
Output_Name_Freq     = 24HR

# ---- Arduino Build Settings
Reset_Teensy_Build   = False
Delete_Kill_All      = False

# ---- Analog Settings
Analog               = True
Analog_Buffer        = 2000

# ---- Serial Settings
Serial_TimeOut       = 3900

# ---- User Information
Name                 = UserA
Email                = email@gmail.com
Enable_Email         = False

# ---- Teensy Program and Reset Settings
Reset_Pin            = 13
Program_Pin          = 19
GPIO_Pin_Type        = BCM
```

The definition of each setting is list below,

**Box & Experiment Information**

- `RPi_IP = 140.247.178.XXX` | The master Raspberry Pi (RPi) IP address.
- `Box_Name = TestBox` | Box name specific to experiment or rack/box number.
- `Subject_Name = MegaR` | Subject name to be used in the experiment.
- `Daily_Water = 1500` and `Water_Minimum = 75%` | Program sends an email to user if the subjects consumes less than `1500*0.75=1125` pulses of water daily.
- `TimeSyncFreq = 24HR` | The program syncs Teensy time with NTP server every 24 hour.

**Result File(s) Settings**

- `Result_Path = D:\Results\` | The local path in user's PC to save experiment information when running `GetJobResult.py` code.
- `Remote_File_Exts = *.dat, *.log` | The extension of remote files to download (experiment events: \*.dat, watchdog: \*.log) when running `GetJobResult.py` code.
- `Get_Analog_Results = True` | If True, the `GetJobResult.py` code will download analog files as well.
- `Delete_Old_Results = False` | If True, the `GetJobResult.py` code deletes old result files except the most recent ones.
- `Output_Name_Freq = 24HR` | The filename for experiment events changes every 24 hour. To disable this option, set the value to False.

**Arduino Build Settings**

- `Reset_Teensy_Build = False` | The main code in RPi makes a build folder in the home directory to expedite the Arduino code compilation process for subsequent runs. If set to True, the program deletes the folder before compiling the Arduino code.
- `Delete_Kill_All = False` | If set to True, the `GetJobResult.py` code kills the program on RPi and deletes the code directory as well (`e.g., /home/pi/AutoTrainerModular`).

**Analog Settings**

- `Analog = True` | If there is an analog input device in the code, this option should be True.
- `Analog_Buffer = 2000` | The size of analog buffer saved in analog output files. The Teensy code has a fixed buffer size of 2048. However, since RPi is keeping analog values in a separate circular buffer, it can have a different size. The standard size for lab experiments is 2000.

**Serial Settings**

- `Serial_TimeOut = 3900` | If the main code on RPi does not receive any inputs from the Teensy in 3900 sec interval, it considers Teensy as `Idle` and notifies the user by email.

**User Information**

- `Name = UserA` | Name of user. It is used in emails and other places in the code.
- `Email = email@gmail.com` | The user email is used for communication. Don't worry, we do not use it for marketing purposes :smiley:.
- `Enable_Email = False` | If set to False, the program does not send email to user.

**Teensy Program and Reset Settings**

- `Reset_Pin = 13` | The reset pin on Teensy is connected to GPIO pin `13` on RPi.
- `Program_Pin = 19` | The program pin on Teensy is connected to GPIO pin `19` on RPi.
- `GPIO_Pin_Type     = BCM` | The GPIO pin numbering format on RPi (BCM or BOARD).


##### 7.3. Submit OpCon job remotely

Once the above settings are finalized, the user can submit experiment remotely by,

```sh
python RemoteJobSubmission.py
```

or just double-click on `RemoteJobSubmission.py` code.

##### 7.4. Get job results remotely

To get experiment results (events, watchdog reports, analog output files), the `GetJobResult.py` can be used,

```sh
python GetJobResult.py
```

or just double-click on `GetJobResult.py` code.

## Tags

**Tag 000** Timing and Alarms  
Timing issues are addressed in four ways:
1. `Hardware Interrupts`: With event driven hardware interrupts (detecting LeverDI presses in the following code). Regardless of where the software execution is, it will be halted and the attached function will execute immediately. Functions should be designed to return without delay.
2. `Clock Based Interrupts`: Using a regularly scheduled interrupt loop (left empty here).
3. `Alarm Scheduler`: Using a "Alarm Scheduler" which must be "serviced" or checked by the running code loop. Alarms are not true interrupts, they check the time and are "serviced" when Alarm.delay() is called. For this reason, Alarm.delay() is put into the HouseKeeping function which should be called periodically in any function that does not return immediately (i.e. most state machines). The alarms repeat every day.
4. `Natural Code Sequence`:  By the natural sequence of code execution.
Note: Hardware interrupts are processed immediately. Interrupt loops run faithfully. Everything else depends on the code context.

**Tag 001** Alarm Types
1. `Training`: regular training session (required: training protocol)
2. `Special`: special session (daily water or weekly water)
3. `Utility`: service state machines: HouseLightsOn, HouseLightsOff, ...
4. `Disable`: disable current active alarm
5. `Void`: Void alarm type (set as default value)

**Tag 002** Maximum Number of Alarms  
Maximum number of alarms

**Tag 003** Analog Write Resolution  
`analogWriteResolution()` function sets the resolution of the `analogWrite()` function. It defaults to 8 bits (values between 0-255) for backward compatibility with AVR based boards. Refer this [Arduino page](https://www.arduino.cc/reference/en/language/functions/zero-due-mkr-family/analogwriteresolution/) for more information.

**Tag 004**  A-to-D-Converter Resolution  
Set A-to-D-Converter resolution to this many bits. It defaults to 10 bits (returns values between 0-1023)

**Tag 005**  
Refer this [Arduino page](https://www.arduino.cc/en/Tutorial/Smoothing) for manual averaging.

## Storage Monitoring (RPi)

The codebase includes a lightweight storage monitor that periodically checks the Raspberry Pi's disk usage and sends an email alert when usage exceeds a configurable threshold (default: 85%). This runs in the background within both `MainCode.py` and `PiCamMain.py` when those scripts are started.

Configuration (optional) keys in `userInfo.in`:

- `Storage_Fill_Threshold` — percentage used at which to alert (default `85`)
- `Storage_Check_Path` — filesystem path to check; use `/` to monitor the SD card (default `/`)
- `Storage_Check_Interval_Sec` — how often to check, in seconds (default `600` = 10 minutes)
- `Storage_Notify_Cooldown_Sec` — minimum seconds between emails while still above threshold (default `86400` = 24 hours)

Notes:
- Email delivery uses the same fields already present in `userInfo.in` (`Enable_Email`, `WD_Email`, `WD_Pass`, `WD_SMTP`, `WD_SMTP_Port`, `WD_SSL`, `Email`, `Name`).
- Alerts are rate-limited and also persisted in `/tmp/atmod_storage_alert*.json` to avoid spamming across restarts.
- `PiCamMain.py` prefers checking the camera storage path (`RPi_Video_Dir` from its config) if provided; otherwise it falls back to `/`.
