/*
  This file sets the state machines and training protocols.
*/

#ifndef _SetStateMachineTP_h
#define _SetStateMachineTP_h

// Define number of state machines, training protocols, and max number of stages
#define numStates 16          // Number of state machines (removed separate Struc/Unstruc wrappers)
#define numTrainingProtocol 1 // Number of training protocol
#define maxNumStage 7         // Maximum number of stages in training protocols

//  List of all state machines
#define FOREACH_STATEMACHINE(SM) \
  SM(DailyWater)                 \
  SM(WeeklyWater)                \
  SM(HouseLightsOn)              \
  SM(HouseLightsOff)             \
  SM(HouseLightsOnToneWater)     \
  SM(BlinkLightsToneWater)       \
  SM(NosepokeNonSession)         \
  SM(LickTest)                   \
  SM(LickTrain)                  \
  SM(NosepokeRewardNonSession)   \
  SM(Nosepoke1sound)             \
  SM(NosepokeProb70)             \
  SM(NosepokeProb40)             \
  SM(NosepokeImpure)             \
  SM(ReadSessionParams)          \
  SM(DoNothing)

// Define enum list of state machines (integer value = 0,1,2,...,numStates-1)
#define GENERATE_ENUM(x) x,
typedef enum
{
  FOREACH_STATEMACHINE(GENERATE_ENUM)
} stateMachine;

// Training protocols
stateMachine trainingProtocol[numTrainingProtocol][maxNumStage][3] = {
    // Training protocol #1, id = xx
    /*{
    {NosePoke,               TapNonSession},
    {ToneConditioning,       TapNonSession},
    {ToneTapTraining,        TapNonSession},
    {TapTraining,            DoNothing},
    {TapProb60,              DoNothing},
    {TapProb30,              DoNothing},
    {TwoTap,                 DoNothing}
    },*/
    // Training protocol #2, id = xx
    /*{
    {NosePoke,               TapNonSession},
    {ToneConditioning,       TapNonSession},
    {ToneTapTraining,        TapNonSession},
    {TapTraining,            DoNothing},
    {TapProb60,              DoNothing},
    {TapProb30,              DoNothing},
    {TwoTap,                 DoNothing}
    },*/
    // Training Protocol for Nosepoke Task, id = 0
    // {
    // {LickTest, 		           NosepokeNonSession},
    // {LickTrain,              NosepokeNonSession},
    // {Nosepoke2sound,         NosepokeNonSession},
    // {Nosepoke1sound,         DoNothing},
    // {NosepokeProb70,         DoNothing},
    // {NosepokeStr,		DoNothing}
    // }
    // New training protocol for nosepoke task, id = 0, 8/2/23
    {
        // {LickTrain,               NosepokeRewardNonSession},
        // {LickTest,               NosepokeRewardNonSession},
        // {Nosepoke1sound,         NosepokeRewardNonSession},
        // {Nosepoke1sound,         DoNothing},
        // {NosepokeProb70,         DoNothing},
        // {NosepokeProb40,	       DoNothing},
        {NosepokeImpure, DoNothing}}};
#endif
