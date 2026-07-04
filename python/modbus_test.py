#!/usr/bin/env python3
import argparse
import logging
import signal
import sys
import time
from contextlib import contextmanager

try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    print("Error: pymodbus is not installed.")
    print("Please install it using: pip install pymodbus")
    sys.exit(1)


def computeCRC(message: bytes) -> bytes:
    try:
        from pymodbus.utilities import computeCRC as pymodbus_compute_crc
    except ImportError:
        pymodbus_compute_crc = None

    if pymodbus_compute_crc is not None:
        return pymodbus_compute_crc(message)

    crc = 0xFFFF
    for pos in message:
        crc ^= pos
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


@contextmanager
def alarm_timeout(seconds: float):
    if seconds <= 0:
        yield
        return

    def handler(signum, frame):
        raise TimeoutError(f"Timed out after {seconds:.2f}s")

    previous_handler = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def main():
    parser = argparse.ArgumentParser(description="Modbus RTU Master Test for STM32G030")
    parser.add_argument('--port', type=str, default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', type=int, default=9600, help='Baud rate')
    parser.add_argument('--slave', type=int, default=1, help='Modbus Slave ID')
    parser.add_argument('--loop', action='store_true', help='Repeat the Modbus reads indefinitely')
    parser.add_argument('--interval', type=float, default=1.0, help='Delay between reads when --loop is used')
    parser.add_argument('--timeout', type=float, default=0.5, help='Maximum time to wait for each Modbus reply')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s: %(message)s')
    logging.getLogger('pymodbus').setLevel(logging.CRITICAL + 10)
    logging.getLogger('pymodbus.transaction').setLevel(logging.CRITICAL + 10)
    logging.getLogger('pymodbus.transport').setLevel(logging.CRITICAL + 10)
    logging.getLogger('pymodbus.client').setLevel(logging.CRITICAL + 10)

    # pymodbus 3.x uses ModbusSerialClient without the method argument usually, 
    # but some versions require method='rtu' or framer. 
    # Providing standard defaults.
    client = ModbusSerialClient(
        port=args.port,
        baudrate=args.baud,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=args.timeout,
        retries=0
    )

    if not client.connect():
        print(f"Failed to connect to {args.port}")
        return

    orig_execute = client.execute

    def debug_execute(no_response_expected, request):
        print("DEBUG: request object:", repr(request))
        print("DEBUG: request type:", type(request).__name__)
        try:
            raw = request.encode()
            print("MODBUS TX len=", len(raw), "bytes")
            print("MODBUS TX:", " ".join(f"0x{b:02X}" for b in raw))
        except Exception as exc:
            raw = b''
            print("MODBUS TX error:", exc)

        try:
            if hasattr(client, 'unit'):
                slave_id = client.unit
            elif hasattr(client, 'device_id'):
                slave_id = client.device_id
            else:
                slave_id = args.slave
            adu = bytes([slave_id]) + raw + computeCRC(bytes([slave_id]) + raw)
            print("RTU ADU len=", len(adu), "bytes")
            print("RTU ADU:", " ".join(f"0x{b:02X}" for b in adu))
        except Exception as exc:
            print("RTU ADU error:", exc)

        response = orig_execute(no_response_expected, request)
        print("DEBUG: response object:", repr(response))
        if response is not None and hasattr(response, 'encode'):
            try:
                raw_response = response.encode()
                print("MODBUS RX len=", len(raw_response), "bytes")
                print("MODBUS RX:", " ".join(f"0x{b:02X}" for b in raw_response))
            except Exception as exc:
                print("MODBUS RX error:", exc)
        else:
            print("MODBUS RX: no encoded response available")
        return response

    client.execute = debug_execute

    print(f"Connected to {args.port}. Testing Modbus Slave ID {args.slave}...")

    iteration = 0
    while True:
        iteration += 1
        if args.loop:
            print(f"\n=== Iteration {iteration} ===")
        else:
            print("\n=== Single pass ===")

        try:
            # 1. Read Holding Registers (FW Version and Serial Num mappings)
            print("\n--- Reading Holding Registers (0x03) ---")
            with alarm_timeout(args.timeout):
                res = client.read_holding_registers(address=0, count=3, device_id=args.slave)
            if not res.isError():
                fw_hex = hex(res.registers[0])
                serial_hi = res.registers[1]
                serial_lo = res.registers[2]
                serial_num = (serial_hi << 16) | serial_lo
                print(f"Holding Reg 0 (FW Version)   : {fw_hex}")
                print(f"Holding Reg 1-2 (Serial Num) : {serial_num} (0x{serial_num:08X})")
            else:
                print(f"Error reading Holding Registers: {res}")
        except Exception as exc:
            print(f"Error reading Holding Registers: {exc}")

        try:
            # 2. Read Input Registers (0-8 per modbus_reg.md)
            print("\n--- Reading Input Registers (0x04) ---")
            with alarm_timeout(args.timeout):
                res = client.read_input_registers(address=0, count=9, device_id=args.slave)
            if not res.isError():
                print(f"Input Reg 0 (Voltage)     : {res.registers[0]}")
                print(f"Input Reg 1 (Current)     : {res.registers[1]}")
                print(f"Input Reg 2 (Power)       : {res.registers[2]}")

                energy_msw = res.registers[3]
                energy_lsw = res.registers[4]
                print(f"Input Reg 3-4 (Energy)    : {(energy_msw << 16) | energy_lsw}")

                uptime_msw = res.registers[5]
                uptime_lsw = res.registers[6]
                print(f"Input Reg 5-6 (Uptime)    : {(uptime_msw << 16) | uptime_lsw}")

                print(f"Input Reg 7 (FW Version)  : {hex(res.registers[7])}")
                print(f"Input Reg 8 (Reset Cause) : {res.registers[8]}")
            else:
                print(f"Error reading Input Registers: {res}")
        except Exception as exc:
            print(f"Error reading Input Registers: {exc}")

        if not args.loop:
            break

        print(f"Waiting {args.interval:.1f}s before next poll...")
        time.sleep(args.interval)

    client.close()
    print("\nTest complete.")

if __name__ == '__main__':
#    ./python/modbus_test.py --port /dev/ttyUSB0 --baud 9600 --slave 1

  try:
        main()
  except KeyboardInterrupt:
      print("\nPolling stopped by user.")
  finally:
      print("Connection closed.")

