#!/usr/bin/env python3
import serial
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description="RS485 Loop Test Echo Server")
    parser.add_argument('--port', type=str, default='/dev/ttyUSB0', help='Serial port (e.g. /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=9600, help='Baud rate')
    args = parser.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"Listening on {args.port} at {args.baud} baud...")
        print("Waiting for 'RS485_LOOP_TEST_OK' from STM32 and echoing it back.")
        
        while True:
            if ser.in_waiting > 0:
                line = ser.readline()
                if line:
                    print(f"Received: {line}")
                    # Echo back exactly what was received to pass the STM32 loop test
                    ser.write(line)
                    print(f"Echoed back.")
            time.sleep(0.01)
    except serial.SerialException as e:
        print(f"Serial Error: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == '__main__':
    main()

# run:
# ./rs485_echo.py --port /dev/ttyUSB0 --baud 9600     
