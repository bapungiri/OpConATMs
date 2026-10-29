/*
The queue object implementation to report serial data.
*/

#ifndef _QUEUEARRAY_H
#define _QUEUEARRAY_H

#include <Arduino.h>

#define queueSize 3000

template<typename T>
class QueueArray {
public:

    QueueArray();
    ~QueueArray();

    void enqueue(const T i);

    T dequeue();

    bool isEmpty() const;

    bool isFull() const;

    int count() const;

    void setPrinter(Print & p);

  private:

    void exit(const char * m) const;

    void blink() const;

    static const int ledPin = 13;

    Print * printer;
    T * contents;

    int items;

    int head;
    int tail;
};

template<typename T>
QueueArray<T>::QueueArray() {

  items = 0;

  head = 0;
  tail = 0;

  printer = NULL;

  contents =(T *) malloc(sizeof(T) * queueSize);

  if(contents == NULL)
    exit("E,Insufficient memory to initialize report queue.");
}

template<typename T>
QueueArray<T>::~QueueArray() {

  free(contents);

  contents = NULL;
  printer = NULL;

  items = 0;

  head = 0;
  tail = 0;
}

template<typename T>
void QueueArray<T>::enqueue(const T i) {

  if(isFull())
    exit("E,Report queue is full. Cannot write to queue.");

  contents[tail++] = i;

  if(tail == queueSize) tail = 0;

  items++;
}

template<typename T>
T QueueArray<T>::dequeue() {

  if(isEmpty())
    exit("E,Can NOT pop item from report queue because queue is empty.");

  T item = contents[head++];

  items--;

  if(head == queueSize) head = 0;

  return item;
}


template<typename T>
bool QueueArray<T>::isEmpty() const {
  return items == 0;
}

template<typename T>
bool QueueArray<T>::isFull() const {
  return items == queueSize;
}

template<typename T>
int QueueArray<T>::count() const {
  return items;
}

template<typename T>
void QueueArray<T>::setPrinter(Print & p) {
  printer = &p;
}

template<typename T>
void QueueArray<T>::exit(const char * m) const {
  if(printer)
  {
    printer->println(m);
  }

  //blink();
}

template<typename T>
void QueueArray<T>::blink() const {
  pinMode(ledPin, OUTPUT);

  while(true) {
    digitalWrite(ledPin, HIGH);
    delay(250);
    digitalWrite(ledPin, LOW);
    delay(250);
  }

}

#endif
