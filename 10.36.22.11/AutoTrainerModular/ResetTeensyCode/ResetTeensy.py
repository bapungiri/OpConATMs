#! /usr/bin/python

import gpiod
from gpiod.line_settings import LineSettings, Direction, Value
import time

ProgPin = 19

try:
    request = gpiod.request_lines(
        "/dev/gpiochip4",
        consumer="reset-teensy",
        config={
            ProgPin: LineSettings(
                direction=Direction.OUTPUT,
                output_value=Value.INACTIVE,
            ),
        },
    )
    time.sleep(0.5)
    request.set_value(ProgPin, Value.ACTIVE)
finally:
    try:
        request.release()
    except Exception:
        pass
