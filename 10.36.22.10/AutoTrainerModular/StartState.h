/*
  Where the Teensy starts: training stage and water already given today/this
  week. MainCode.py rewrites this file before every compile from the animal's
  state.json, so a deploy or reboot continues where the animal was. This
  default (a new animal) starts at the first stage with no water.
*/

#ifndef _StartState_h
#define _StartState_h

#define START_STAGE 0
#define START_DAILY_INTAKE 0
#define START_WEEKLY_INTAKE 0

#endif
