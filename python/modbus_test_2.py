import time
from pymodbus.client import ModbusSerialClient

# --- НАСТРОЙКИ ПОДКЛЮЧЕНИЯ ---
PORT = '/dev/ttyUSB0'       # Порт вашего адаптера
BAUDRATE = 9600             # Скорость (должна совпадать с STM32)
SLAVE_ID = 1                # Адрес вашего STM32 устройства

# Инициализация Modbus RTU Клиента
client = ModbusSerialClient(
    port=PORT,
    baudrate=BAUDRATE,
    bytesize=8,
    parity='N',
    stopbits=1,
    timeout=1
)

def combine_32bit(msw, lsw):
    """Объединяет два 16-битных регистра в один 32-битный"""
    return (msw << 16) | lsw

def run_master():
    if not client.connect():
        print(f"Failed to connect to {PORT}")
        return

    print(f"Connected to {PORT}. Starting polling Slave ID {SLAVE_ID}...\n")

    try:
        while True:
            # 1. Читаем Input Registers (0x04) с адреса 0, всего 9 регистров
            # (Voltage, Current, Power, Energy_MSW, Energy_LSW, Uptime_MSW, Uptime_LSW, FW, Reset)
            result = client.read_input_registers(address=0, count=9, device_id=SLAVE_ID)
            
            if result.isError():
                print(f"Modbus Error: {result}")
            else:
                regs = result.registers
                
                # Парсинг согласно нашей Register Map
                voltage = regs[0] / 100.0
                current = regs[1] / 1000.0
                power   = regs[2] / 10.0
                
                energy = combine_32bit(regs[3], regs[4])
                uptime = combine_32bit(regs[5], regs[6])
                
                # Версия прошивки из HEX (например 0x0123 -> 1.2.3)
                fw_raw = regs[7]
                fw_ver = f"{(fw_raw >> 8) & 0x0F}.{(fw_raw >> 4) & 0x0F}.{fw_raw & 0x0F}"
                
                reset_cause = regs[8]

                # Вывод данных в терминал
                print("--- DATA PACKET ---")
                print(f"Voltage:         {voltage:.2f} V")
                print(f"Current:         {current:.3f} A")
                print(f"Power:           {power:.1f} W")
                print(f"Accumulated En.: {energy} Wh")
                print(f"Device Uptime:   {uptime} seconds")
                print(f"Firmware Ver:    {fw_ver}")
                print(f"Last Reset Code: {reset_cause}")
                print("-------------------\n")

            time.sleep(2) # Опрос каждые 2 секунды

    except KeyboardInterrupt:
        print("\nPolling stopped by user.")
    finally:
        client.close()
        print("Connection closed.")

if __name__ == "__main__":
    run_master()
