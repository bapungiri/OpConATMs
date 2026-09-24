/*
  This file defines specific functions shared between state machines.
*/

#ifndef _SpecificFunctions_h
#define _SpecificFunctions_h
#include <math.h>

void WhichNosepoke(int unsigned nptime){ // checking which nosepoke and reporting
  uint8_t recordNosepoke[4] = {!Nosepoke1DI.diRead(), !Nosepoke2DI.diRead()};
  int whichnosepoke[2]  = {1,2};
  for (int i = 0; i<=1; ++i){
    if ((recordNosepoke[i] ==1)){
      ReportData(81, whichnosepoke[i], nptime);
    }
  }
  Nosepoke1DI.clear();  
  Nosepoke2DI.clear();
}

float GenerateProb(float mu, float xval){
  const float amp = 0.7;
  const float sig = 1.75/2;
  const float vo = 0.1;
  
  float dx = xval - mu;
  float dx2 = dx * dx;
  float s2 = 2.0*sig*sig;
  float e = expf(-dx2/s2);
  float prob = amp * e + vo;
  return prob;
}

int DrawAProb(){
  //Draw a probability value from the set {20, 30, 40, 60, 70, 80}
  int probArr[6] = {20, 30, 40, 60, 70, 80};
  int n = random(6);
  int prob = probArr[n];
  return prob;
}

int DrawDependentPair(int prob1){
  // Given prob1, draw a paired probability such that prob1 + prob2 = 100
  int prob2 = 100 - prob1;
  return prob2;
}

int DrawIndependentPair(int prob1){
  // Given prob1, draw a paired probability such that prob1 + prob2 != 100
	int probArr[6] = {20, 30, 40, 60, 70, 80}; 
	
	int idx;
	do {
		idx = random(6);
  } while (probArr[idx] == (100 - prob1) || probArr[idx] == prob1);

  int prob2 = probArr[idx];
	return prob2;
}

void permutePorts(float* ports, int sizer){
  for (int i = 0; i< sizer; ++i){
    int n = random(0, sizer);
    float temp = ports[n];
    ports[n] = ports[i];
    ports[i] = temp;
  }
}

float SessionMean(){
// choose a random number from 1 to 8. that is session mean, or use a randomly gen sequence e.g.
  // (7, 6, 1, 7, 8, 7, 1, 4, 6, 6, 2, 3, 6, 4, 5, 2, 2, 7, 7, 8, 1, 2, 1, 4, 2, 8, 1, 1, 5, 7, 3, 2, 3,
  // 2, 5, 8, 6, 1, 4, 1, 5, 4, 8, 7, 4, 8, 2, 4, 8, 8, 6, 5, 3, 8, 1, 6, 6, 7, 4, 6, 7, 3, 5, 8, 5,
  // 3, 5, 3, 7, 4, 4, 6, 8, 3, 7, 6, 8, 1, 3, 6, 3, 2, 6, 5, 5, 6, 1, 3, 4, 2, 6, 7, 3, 6, 2, 7, 2, 5, 3, 7);
  int unsigned randomNumber = random(1,5);
  ReportData(82, randomNumber, (millis()-stateMachineStartTime));
  return (float)randomNumber;
}
#endif
