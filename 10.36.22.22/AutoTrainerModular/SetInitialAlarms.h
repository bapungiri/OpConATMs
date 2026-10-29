/*
  Set initial alarms.
*/

#ifndef _SetInitialAlarms_h
#define _SetInitialAlarms_h

void SetInitialAlarms()
{

  // ## Add more alarm types: trigger once ....

  SetDailyAlarms(6, 0, 0, Utility, -1, HouseLightsOn, DoNothing, DoNothing);
  SetDailyAlarms(18, 0, 0, Utility, -1, HouseLightsOff, DoNothing, DoNothing);

  SetDailyAlarms(19, 0, 0, Training, 0, BlinkLightsToneWater, HouseLightsOff, DoNothing);
  SetDailyAlarms(19, 40, 0, Disable, -1, HouseLightsOff, DoNothing, DoNothing);

  SetDailyAlarms(23, 0, 0, Training, 0, BlinkLightsToneWater, HouseLightsOff, DoNothing);
  SetDailyAlarms(23, 40, 0, Disable, -1, HouseLightsOff, DoNothing, DoNothing);

  // SetDailyAlarms(13, 01, 0, Utility, -1, ReadSessionsParams, DoNothing, DoNothing);
  SetDailyAlarms(3, 0, 0, Training, 0, BlinkLightsToneWater, HouseLightsOff, DoNothing);
  SetDailyAlarms(3, 40, 0, Disable, -1, HouseLightsOff, DoNothing, DoNothing);

  SetDailyAlarms(5, 0, 0, Special, -1, HouseLightsOnToneWater, HouseLightsOff, DailyWater);
  SetDailyAlarms(5, 30, 0, Disable, -1, DoNothing, DoNothing, DoNothing);

  SetWeeklyAlarms(dowMonday, 4, 0, 0, Special, -1, HouseLightsOnToneWater, HouseLightsOff, WeeklyWater);
  SetWeeklyAlarms(dowMonday, 5, 0, 0, Disable, -1, DoNothing, DoNothing, DoNothing);
}

#endif
