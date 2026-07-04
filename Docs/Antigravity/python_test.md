1. RS485 Loop Test (python/rs485_echo.py)
This script opens the serial port and waits to receive data. Whenever it receives data (like the "RS485_LOOP_TEST_OK\r\n" message your STM32 is sending), it instantly echoes it back. This allows your STM32 to successfully pass its internal loop test!

To run it:

bash
./python/rs485_echo.py --port /dev/ttyUSB0 --baud 9600
(Make sure the #define LOOP_TEST_ is active in your main.c before running this!)

2. PyModbus Client Master (python/modbus_test.py)
This script uses the pymodbus library to act as a Modbus Master. It connects to the device, queries the Holding Registers for the FW Version and Serial Number, and then queries the Input Registers (0-8) just like you mapped out in your modbus_reg.md document.

To run it:

bash
# First, ensure pymodbus is installed on your Ubuntu machine
pip install pymodbus
# Then run the test script
./python/modbus_test.py --port /dev/ttyUSB0 --baud 9600 --slave 1
(Make sure to comment out #define LOOP_TEST_ in your main.c so the Modbus stack is active before running this!)