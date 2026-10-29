#! /usr/bin/python

import RPi.GPIO as GPIO
import time

ProgPin = 19

try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(ProgPin, GPIO.OUT)
    GPIO.output(ProgPin, GPIO.LOW)
    time.sleep(0.5)

    GPIO.output(ProgPin, GPIO.HIGH)
finally:
    GPIO.cleanup()
