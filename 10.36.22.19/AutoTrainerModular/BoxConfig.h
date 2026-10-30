/*
  Pin level each sensor type has while active. MainCode.py rewrites this file from
  userInfo.in (Nosepoke_Active, Lick_Active) before every compile; these are the defaults.
*/

#ifndef _BoxConfig_h
#define _BoxConfig_h
#define LICK_ACTIVE HIGH    // tongue on the spout
#define NOSEPOKE_ACTIVE LOW // nose in the port
#endif
