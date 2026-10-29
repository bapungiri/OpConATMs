/*
   The sound declaration and configuration header file. SNDLIB
*/

#ifndef _SetSoundSetting_h
#define _SetSoundSetting_h

// Uncomment To Use

#include <Audio.h>
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <SerialFlash.h>

void soundInterruptFunc(int, int, int, int, int); // Sound interrupt function that turns off sound after specified time interval
IntervalTimer soundTimer[3];                      // Interval timer turns off sound after specified time in sec
int currentSoundTimer = -1;                       // Index of current activated sound timer
int sCh0, sCh1, sCh2, sCh3;                       // Global variable for each sound mixer channel

void SoundON(float, float, float, float, int);
void SoundOFF(int, int, int, int);

// -----------------------------------------   User-specific sound setting

// Audio Output via DACS
AudioOutputAnalogStereo  soundOutPut;

// Mixer allows for four possible sounds, output to DACS
AudioMixer4                      soundMixer;
AudioConnection                  audioCon1(soundMixer, 0, soundOutPut, 1);

// Sound 0: sine wave
AudioSynthWaveformSine           sound0;
AudioConnection                  audioCon2(sound0, 0, soundMixer, 0);

// Sound 1: white noise
AudioSynthNoiseWhite             sound1;
AudioConnection                  audioCon3(sound1, 0, soundMixer, 1);

// Sound 2: higher freq sine wave
AudioSynthWaveformSine		sound2;
AudioConnection                  audioCon4(sound2, 0, soundMixer, 2);

// Sound 3: tone sweep (triangle wave --> frequency modulated sinewave)
AudioSynthWaveform               sound3a;
AudioSynthWaveformSineModulated  sound3b;
AudioConnection                  audioCon5(sound3a, sound3b);
AudioConnection                  audioCon6(sound3b, 0, soundMixer, 3);


// -----------------------------------------   SetSoundConfig [User-specific sound setting]
void SetSoundConfig(){

  // Allocate sound memory
  AudioMemory(100);

  // Initialize all channels OFF
  soundMixer.gain(0, 0);
  soundMixer.gain(1, 0);
  soundMixer.gain(2, 0);
  soundMixer.gain(3, 0);

  // Sine wave parameters
  sound0.frequency(4000);
  sound0.amplitude(200);

  // White noise parameters
  sound1.amplitude(0.75);

  // Square wave parameters - now higher freq sine wave
 // sound2.begin(WAVEFORM_SQUARE);
  sound2.amplitude(200);
  sound2.frequency(7000);
  //sound2.pulseWidth(0.5);

  // Freq-modulated sine wave parameters
  sound3a.begin(WAVEFORM_TRIANGLE);
  sound3a.amplitude(1);
  sound3a.frequency(0.5);
  sound3a.pulseWidth(0.5);
  sound3b.frequency(1000);
  sound3b.amplitude(0.75);
}

// -----------------------------------------   SoundON
void SoundON(float g0=0, float g1=0, float g2=0, float g3=0, int T=-1){

  // Turn ON sound (gain channel 0, gain channel 1, gain channel 2, gain channel 3, timer values in seconds)

  sCh0 = -1;
  sCh1 = -1;
  sCh2 = -1;
  sCh3 = -1;

  if (g0 != 0) {
    sCh0 = 0;
    ReportData(120+sCh0, 1, (millis()-stateMachineStartTime));
    soundMixer.gain(sCh0, g0);
  }

  if (g1 != 0) {
    sCh1 = 1;
    ReportData(120+sCh1, 1, (millis()-stateMachineStartTime));
    soundMixer.gain(sCh1, g1);
  }

  if (g2 != 0) {
    sCh2 = 2;
    ReportData(120+sCh2, 1, (millis()-stateMachineStartTime));
    soundMixer.gain(sCh2, g2);
  }

  if (g3 != 0) {
    sCh3 = 3;
    ReportData(120+sCh3, 1, (millis()-stateMachineStartTime));
    soundMixer.gain(sCh3, g3);
  }


  // Activate a timer to automatically turn off activated mixer channels
  if (T > 0){

    // Reset sound timer index if reached 3 [Refer to Teensy Interval Timer help]
    if (currentSoundTimer == 2){
      currentSoundTimer = -1;
    }

    currentSoundTimer++;

    if (currentSoundTimer==0){
      for (int i=0; i<16; i++){

        // 0-3
        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, 3, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, 3, 0);}, int(T*1000));
          break;
        }

        // 4-7
        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, 3, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, 3, 0);}, int(T*1000));
          break;
        }

        // 8-11
        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, 3, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, 3, 0);}, int(T*1000));
          break;
        }

        // 12-15
        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, -1, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, 3, 0);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, 3, 0);}, int(T*1000));
          break;
        }

      }
    }

    if (currentSoundTimer==1){
      for (int i=0; i<16; i++){

        // 0-3
        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, 3, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, 3, 1);}, int(T*1000));
          break;
        }

        // 4-7
        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, 3, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, 3, 1);}, int(T*1000));
          break;
        }

        // 8-11
        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, 3, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, 3, 1);}, int(T*1000));
          break;
        }

        // 12-15
        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, -1, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, 3, 1);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, 3, 1);}, int(T*1000));
          break;
        }

      }
    }

    if (currentSoundTimer==2){
      for (int i=0; i<16; i++){

        // 0-3
        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, -1, 3, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, 1, 2, 3, 2);}, int(T*1000));
          break;
        }

        // 4-7
        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, -1, 3, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, -1, 2, 3, 2);}, int(T*1000));
          break;
        }

        // 8-11
        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, -1, 3, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == -1) && (sCh1 == 1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(-1, 1, 2, 3, 2);}, int(T*1000));
          break;
        }

        // 12-15
        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == -1) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, -1, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == -1) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, -1, 3, 2);}, int(T*1000));
          break;
        }

        if ( (sCh0 == 0) && (sCh1 == -1) && (sCh2 == 2) && (sCh3 == 3) ){
          soundTimer[currentSoundTimer].begin([]{soundInterruptFunc(0, -1, 2, 3, 2);}, int(T*1000));
          break;
        }

      }
    }

  }
}

// -----------------------------------------   SoundOFF
void SoundOFF(int c0=-1, int c1=-1, int c2=-1, int c3=-1){

  // Turn OFF sound (gain channel 0, gain channel 1, gain channel 2, gain channel 3)

  if (c0 != -1) {
    ReportData(120+c0, 0, (millis()-stateMachineStartTime));
    soundMixer.gain(c0, 0);
  }
  if (c1 != -1) {
    ReportData(120+c1, 0, (millis()-stateMachineStartTime));
    soundMixer.gain(c1, 0);
  }
  if (c2 != -1) {
    ReportData(120+c2, 0, (millis()-stateMachineStartTime));
    soundMixer.gain(c2, 0);
  }
  if (c3 != -1) {
    ReportData(120+c3, 0, (millis()-stateMachineStartTime));
    soundMixer.gain(c3, 0);
  }
}

// -----------------------------------------   soundInterruptFunc
void soundInterruptFunc(int Ch0=-1, int Ch1=-1, int Ch2=-1, int Ch3=-1, int CTimer=-1){
  // Turn off sounds
  SoundOFF(Ch0, Ch1, Ch2, Ch3);

  // Stop the interval timer
  soundTimer[CTimer].end();
}



#endif
