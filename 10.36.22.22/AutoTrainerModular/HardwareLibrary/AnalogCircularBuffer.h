/*
  This file declares the analog circular buffer
*/

#ifndef _AnalogCircularBuffer_h
#define _AnalogCircularBuffer_h

// Analog Circular Buffer Size = 2^11 (Power of 2)
#define BUFFER_SIZE 2048

class anCircularBuffer
{
public:

  // The class constructor
  anCircularBuffer();

  // Increase circularBufferStartIndex or circularBufferEndIndex
  int increaseIndex(int p);

  // Read from circular buffer
  unsigned long* readBuffer(char='Y');

  // Write to circular buffer
  void writeBuffer(unsigned long value);

  // Check if the circular buffer is empty
  int isBufferEmpty();

  // Check if the circular buffer is full
  int isBufferFull();

  // Report number of new elements since previous reading
  int getNumNewItems();

  // The class destructor
  virtual ~anCircularBuffer();

private:
  
  // The circular buffer size, start index, end index, and linear array
  int circularBufferSize = BUFFER_SIZE;
  int circularBufferStartIndex = 0;
  int circularBufferEndIndex = 0;
  unsigned long circularBufferLinearArray[BUFFER_SIZE];

  int tempIndexLoc = 0;
  unsigned long tempLinearArray[BUFFER_SIZE];
  unsigned long* tempPtr;
  int numNewWrittenItems = 0;
};

#endif
