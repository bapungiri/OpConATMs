// Shared implementation for Struc/Unstruc Impure nosepoke state machines.
// Additional wrapper headers call RunNosepokeImpureMachine with desired value.

#ifndef _NosepokeImpureMachine_h
#define _NosepokeImpureMachine_h

struct NosepokeImpureStruct
{
    int rewardCounter;       // rewards delivered in current block
    int probArray[2];        // current port reward probabilities
    int blockNum;            // block index
    int trialCounter;        // lick-count trials (increment on lick only)
    int unstructuredProb;    // probability (%) of drawing unstructured pair for this animal
    uint64_t sessionStartMs; // session start epoch ms (per animal instance)
};

static void updateRewProbGeneric(NosepokeImpureStruct &st, int unstrProb)
{
    unsigned int randomEnvDraw = random(100);
    int prob1 = DrawAProb();
    int prob2;
    if (randomEnvDraw < (unsigned)unstrProb)
    {
        prob2 = DrawIndependentPair(prob1); // unstructured: independent sampling
    }
    else
    {
        prob2 = DrawDependentPair(prob1); // structured: complementary probabilities
    }
    st.probArray[0] = prob1;
    st.probArray[1] = prob2;
}

static void reportProbGeneric(const NosepokeImpureStruct &st)
{
    float ports[] = {1.0, 2.0};
    for (int i = 0; i < 2; ++i)
    {
        ReportData(83, (int)ports[i], st.probArray[i]);
    }
}

static int changeBlockGeneric(const NosepokeImpureStruct &st)
{
    const int min_length = 100; // minimum lick trials before allowing switch
    const int switchProb = 2;   // percent chance after minimum
    if (st.trialCounter >= min_length)
    {
        unsigned int randomDraw = random(100);
        if (randomDraw < (unsigned)switchProb)
        {
            ReportData(111, st.trialCounter, (millis() - stateMachineStartTime));
            ReportData(121, st.blockNum, (millis() - stateMachineStartTime));
            return 1;
        }
    }
    return 0;
}

static int checkSMStateStopGeneric(const NosepokeImpureStruct &st)
{
    if (stateStop)
    {
        ReportData(111, st.trialCounter, (millis() - stateMachineStartTime));
        ReportData(121, st.blockNum, (millis() - stateMachineStartTime));
        ReportData(63, st.rewardCounter, (millis() - stateMachineStartTime));
        EndCurrentStateMachine();
        RunStartANDEndStateMachine(&endStateMachine);
        EndCurrentTrainingProtocol();
        return 1;
    }
    return 0;
}

inline void NosepokeImpureMachineCore(NosepokeImpureStruct &st)
{
    // ---------for unstructured probability--------
    int unstrProb = 5;
    // -----------------

    st.unstructuredProb = unstrProb; // store for logging
    RunStartANDEndStateMachine(&startStateMachine);
    InitializeStateMachine();
    if (st.sessionStartMs == 0)
        st.sessionStartMs = epochMillis();

    st.blockNum = 0;

    while (!stateStop)
    {                                                           // block loop
        int blockStartTime = epochMillis() - st.sessionStartMs; // Relative to session start

        // Increment block but reset reward and trial counters
        st.blockNum++;
        st.trialCounter = 0;
        st.rewardCounter = 0;

        // Draw new reward probabilities
        updateRewProbGeneric(st, unstrProb);
        reportProbGeneric(st);

        int n = 0; // port index (1 or 2)
        int rewardPercent = 0;

        while (!stateStop)
        { // trials loop
            // session end controlled solely by Disable alarms or external stateStop triggers.
            HouseKeeping();
            if (checkSMStateStopGeneric(st))
                return;

            if (Nosepoke1DI.isOn() || Nosepoke2DI.isOn())
            {
                // Trial starts when nosepoke detected
                int trialStartTime = epochMillis() - st.sessionStartMs;
                unsigned int whenNosepoke = (millis() - stateMachineStartTime);

                // Detect which port
                n = !Nosepoke1DI.diRead() ? 1 : (!Nosepoke2DI.diRead() ? 2 : n);

                // Reporting port number and time of nosepoke, removed WhichNosepoke()
                ReportData(81, n, whenNosepoke);
                Nosepoke1DI.clear();
                Nosepoke2DI.clear();

                // Retrieving reward probability for chosen port and reporting
                rewardPercent = st.probArray[n - 1];
                ReportData(88, rewardPercent, (millis() - stateMachineStartTime));
                bool rewardFlag = false;

                // Deliver auditory cue for 500ms
                SpeakerPwdAO.on(50);
                delayHK(500);
                SpeakerPwdAO.off(0);

                // Lick window of 5s starts
                unsigned long lickWindowStart = millis();
                bool lickDetected = false;
                while ((millis() - lickWindowStart) <= 5000)
                {
                    if (stateStop || checkSMStateStopGeneric(st))
                    {
                        lickDetected = false;
                        break;
                    }
                    if (LickDI.isOn())
                    {
                        // Only valid lick trials are counted as trialCounter
                        st.trialCounter++;
                        lickDetected = true;
                        LickDI.clear();

                        // Draw random number for reward determination
                        unsigned int randomNumber = random(100);

                        if (randomNumber < rewardPercent)
                        {
                            GiveReward(1);
                            rewardFlag = true;
                            st.rewardCounter++;
                        }
                        else
                        {
                            ReportData(-51, 0, (millis() - stateMachineStartTime));
                        }
                        break;
                    }
                }

                if (!lickDetected)
                {
                    ReportData(-52, 0, (millis() - stateMachineStartTime));
                }
                if (!rewardFlag)
                {
                    ReportData(86, 1, (millis() - stateMachineStartTime));
                }

                // Calculate trial end time relative to session start time
                int trialEndTime = epochMillis() - st.sessionStartMs;

                // Report data for .dat file
                if (lickDetected)
                {
                    ReportTrialSummary(200,                 // Event code
                                       st.probArray[0],     // Port1
                                       st.probArray[1],     // Port2
                                       n,                   // Chosen port
                                       rewardFlag ? 1 : 0,  // Reward
                                       st.trialCounter,     // Trial ID
                                       st.blockNum,         // block ID
                                       st.unstructuredProb, // Environment type
                                       st.sessionStartMs,   // Session start epoch (64-bit)
                                       blockStartTime,      // Block start rel ms
                                       trialStartTime,      // Trial start rel ms
                                       trialEndTime);       // Trial end rel ms
                }
                else
                {
                    ReportTrialSummary(201,
                                       st.probArray[0],
                                       st.probArray[1],
                                       n,  // Chosen port = 0 for missed trial
                                       -1, // Didn't attempt
                                       st.trialCounter,
                                       st.blockNum,
                                       st.unstructuredProb,
                                       st.sessionStartMs,
                                       blockStartTime,
                                       trialStartTime,
                                       trialEndTime);
                }

                if (changeBlockGeneric(st))
                {
                    break; // start new block
                }
            }
            if (stateStop)
                break;

        } // end trials loop
        if (stateStop)
            break;

    } // end blocks loop
    checkSMStateStopGeneric(st);
}

// Parameterless wrapper required by the generic state machine function pointer array.
// The macro system declares/uses void NosepokeImpureMachine(void); so we provide an
// overload that owns a persistent state struct and delegates to the core implementation.
// Using a function-local static ensures a single instance per program (not per TU).
inline void NosepokeImpureMachine()
{
    // Non-static instance: resets every time this wrapper is invoked.
    NosepokeImpureStruct st = {0, {0, 0}, 0, 0, 0, 0};
    NosepokeImpureMachineCore(st);
}

#endif
