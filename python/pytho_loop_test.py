import serial
import time

# Укажите ваши порты
port1 = '/dev/ttyUSB0'
port2 = '/dev/ttyUSB1'

while True:

  try:
      ser1 = serial.Serial(port1, 9600, timeout=1)
      ser2 = serial.Serial(port2, 9600, timeout=1)
      
      print("Sending data from port1 to port2...")
      test_message = b"Hello RS485 Loop!"
      ser1.write(test_message)
      
      time.sleep(0.1) # Ждем физической передачи
      
      received = ser2.read(len(test_message))
      print(f"Received data on port2: {received}")
      
      if received == test_message:
          print("SUCCESS: Loop test passed!")
      else:
          print("ERROR: Data mismatch or timeout.")
          
      ser1.close()
      ser2.close()

      time.sleep(1)


      ser1 = serial.Serial(port2, 9600, timeout=1)
      ser2 = serial.Serial(port1, 9600, timeout=1)
      
      print("Sending data from port2 to port1...")
      test_message = b"Hello RS485 Loop!"
      ser1.write(test_message)
      
      time.sleep(0.1) # Ждем физической передачи
      
      received = ser2.read(len(test_message))
      print(f"Received data on port1: {received}")
      
      if received == test_message:
          print("SUCCESS: Loop test passed!")
      else:
          print("ERROR: Data mismatch or timeout.")
          
      ser1.close()
      ser2.close()

  except Exception as e:
      print(f"Error during test: {e}")

  time.sleep(1)
