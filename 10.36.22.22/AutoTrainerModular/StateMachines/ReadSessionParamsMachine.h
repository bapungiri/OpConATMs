#ifndef _ReadSessionParamsMachine_h
#define _ReadSessionParamsMachine_h

void ReadSessionParamsMachine() {

	RunStartANDEndStateMachine(&startStateMachine);
	InitializeStateMachine(); // Initialize state machine

	Serial.print('S');
	int endMarker = -1;
	int rc[4]; 
	int temp; 
	bool newData = false; 
	int counter = 0; 

	while (Serial.available() > 0 && newData == false) {
		temp = Serial.parseInt();
		if (temp == endMarker) {
			newData = true;
		}
		rc[counter] = temp;
		counter++;
	}
	currentTrainingProtocol = rc[0];
	currentStage[currentTrainingProtocol] = rc[1];
	dailyIntake = rc[2];
	weeklyIntake = rc[3];
}

#endif
