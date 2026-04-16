/*
  This file defines the analog circular buffer member functions
*/

#include "AnalogCircularBuffer.h"

anCircularBuffer::anCircularBuffer()
{
  // Class constructor goes here
}

// Increase the start or end index
int anCircularBuffer::increaseIndex(int p) {
  return (p + 1)&(2*circularBufferSize-1);
}

// Read from circular buffer
unsigned long* anCircularBuffer::readBuffer(char resetFlag) {

  tempIndexLoc = circularBufferStartIndex;

  for (int i=0; i<BUFFER_SIZE; i++)
  {
    tempLinearArray[i] = circularBufferLinearArray[tempIndexLoc&(circularBufferSize-1)];
    tempIndexLoc = increaseIndex(tempIndexLoc);
  }

  if (resetFlag == 'Y')
  {
    numNewWrittenItems = 0;
  }

  tempPtr = &tempLinearArray[0];
  return tempPtr;
}

// Write to circular buffer
void anCircularBuffer::writeBuffer(unsigned long value) {
  circularBufferLinearArray[circularBufferEndIndex&(circularBufferSize-1)] = value;
  if (isBufferFull()) {
    circularBufferStartIndex = increaseIndex(circularBufferStartIndex);
  }
  circularBufferEndIndex = increaseIndex(circularBufferEndIndex);
  numNewWrittenItems = min(++numNewWrittenItems, BUFFER_SIZE);
}

// Check if the circular buffer is empty
int anCircularBuffer::isBufferEmpty() {
  return (circularBufferEndIndex == circularBufferStartIndex);
}

// Check if the circular buffer is full
int anCircularBuffer::isBufferFull() {
  return (circularBufferEndIndex == (circularBufferStartIndex ^ circularBufferSize));
}

// Report number of new elements since previous reading
int anCircularBuffer::getNumNewItems() {
  return numNewWrittenItems;
}

// The class destructor
anCircularBuffer::~anCircularBuffer()
{
  // Class destructor goes here
}
