# Modbus RTU Protocol Documentation

## 1. Modbus Register Map

All data registers in this device are 16-bit words and use **Big-Endian** byte ordering (Most Significant Byte first). 

For 32-bit parameters (e.g., Energy, Uptime), values are split across two consecutive registers. The Master must read both registers and combine them using the following formula:

$$\text{Value} = (\text{MSW} \times 65536) + \text{LSW}$$

### 1.1. Input Registers (3x Type, Protocol Addresses: 0-Based, Read-Only)

| Address (HEX) | Address (DEC) | Parameter Name | Data Type | Scale / Format | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0x0000** | 0 | Supply Voltage (U) | `uint16_t` | ×100 (100 = 1.00 V) | Main power rail voltage. E.g., `1245` represents 12.45 V. |
| **0x0001** | 1 | Current Consumption (I) | `uint16_t` | ×1000 (1000 = 1.000 A) | Current load in mA. E.g., `250` represents 0.250 A (250 mA). |
| **0x0002** | 2 | Instantaneous Power (P) | `uint16_t` | ×10 (10 = 1.0 W) | Active power in Watts. E.g., `155` represents 15.5 W. |
| **0x0003** | 3 | Accumulated Energy [MSW] | `uint32_t` | 1 = 1 Wh | Most Significant Word of total energy counter. |
| **0x0004** | 4 | Accumulated Energy [LSW] | (Split) | Range: 0...4,294,967,295 | Least Significant Word. Combine MSW + LSW for full Wh value. |
| **0x0005** | 5 | Device Uptime [MSW] | `uint32_t` | 1 = 1 second | Most Significant Word of system uptime. |
| **0x0006** | 6 | Device Uptime [LSW] | (Split) | Range: up to 136 years | Least Significant Word. Total time elapsed since power-on. |
| **0x0007** | 7 | Firmware Version | `uint16_t` | `0xXYZ` -> X.Y.Z | BCD encoded version. E.g., version `1.2.3` is read as `0x0123`. |
| **0x0008** | 8 | Last Reset Cause | `uint16_t` | Code | Status code indicating the last MCU reset source (see Table 1.3). |

### 1.2. Holding Registers (4x Type, Protocol Addresses: 0-Based, Read-Write)

| Address (HEX) | Address (DEC) | Parameter Name | Data Type | Valid Range | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0x0000** | 0 | Command: Reset Energy Counter | `uint16_t` | `0` or `12345` | Writing a security key `12345` clears Accumulated Energy registers. |
| **0x0001** | 1 | Modbus Device ID (Slave ID) | `uint16_t` | 1...247 | Modbus network address. Saved to internal Flash on change. |

### 1.3. Reference: Last Reset Cause Codes (Register 0x0008)

The value is captured from the hardware `RCC->CSR` register at MCU startup:
* `1` — **Power-On / Power-Down Reset (POR / PDR):** Normal power application.
* `2` — **External Reset (NRST Pin):** Physical reset button triggered.
* `3` — **Independent Watchdog Reset (IWDG):** Code freeze detected by hardware watchdog.
* `4` — **Software Reset (SYSRESETREQ):** Software-requested reboot (e.g., firmware trigger).
* `5` — **Low-Power Reset:** System wake-up from Deep Sleep/Standby modes.

---

## 2. Modbus RTU Frame Format

Modbus RTU frames are transmitted asynchronously over a serial communication line (RS-485). Each frame consists of four mandatory fields, transmitted with no gaps between characters.

```
+-------------------+---------------------+-------------------------+-------------------+
|  Slave ID (Address| Function Code (FC)  |          Data           |   CRC-16 Checksum |
|      (1 byte)     |      (1 byte)       |      (N × bytes)        |      (2 bytes)    |
+-------------------+---------------------+-------------------------+-------------------+

<-------------------------------- Total Frame: Max 256 bytes ----------------------> 
```

### 2.1. Field Breakdown

1. **Slave ID (1 byte):** The target address of the device (1 to 247). Address 0 is reserved for broadcast messages (no response is sent).
2. **Function Code (1 byte):** Defines the action requested by the Master. Supported function codes are:
    * `0x03` (Read Holding Registers)
    * `0x04` (Read Input Registers)
    * `0x06` (Write Single Holding Register)
    * `0x10` (Write Multiple Holding Registers)
3. **Data Field (N bytes):** Contains sub-arguments like starting register addresses, quantity of registers, or data values.
4. **Error Check / CRC-16 (2 bytes):** Cyclic Redundancy Check used to detect transmission errors. Standard polynomial `0xA001` is used. It is transmitted in Little-Endian format (Low byte first).

### 2.2. Frame Timing Constraints

* **End of Frame (3.5T):** A silent interval of at least 3.5 character times must separate consecutive frames. This signals to the STM32 that a complete frame has arrived.
* **Inter-character Timeout (1.5T):** The maximum allowable silent interval between individual characters within a single frame is 1.5 character times. Exceeding this limit causes the frame to be discarded as corrupted.

---

## 3. Modbus Exception Codes

If the Master sends an invalid request, the Slave will respond with an **Exception Frame**.
An exception frame modifies the requested Function Code by setting its highest bit to 1 (achieved by adding `0x80` to the original code) and appends a 1-byte Exception Code to describe the error.

### 3.1. Supported Exception Codes

| Code (HEX) | Code (DEC) | Exception Name | Description | Trigger Conditions on This Device |
| :--- | :--- | :--- | :--- | :--- |
| **0x01** | 1 | ILLEGAL FUNCTION | The function code received in the query is not supported by the slave. | Triggered if the Master sends any function code other than `0x03`, `0x04`, `0x06`, or `0x10`. |
| **0x02** | 2 | ILLEGAL DATA ADDRESS | The data address received in the query is not an allowable address for the slave. | Triggered if the Master tries to read Input Registers beyond address `0x0008` or Holding Registers beyond `0x0001`. |
| **0x03** | 3 | ILLEGAL DATA VALUE | A value contained in the query data field is not allowable for the slave. | Triggered if: <br> • The Master attempts to write a Modbus ID outside the `1...247` range. <br> • The quantity of requested registers is set to `0` or exceeds the maximum buffer length. |
| **0x04** | 4 | SLAVE DEVICE FAILURE | An unrecoverable error occurred while the slave was attempting to perform the requested action. | Triggered if a hardware failure occurs during an internal Flash memory write operations while updating the Device ID. |

### 3.2. Exception Frame Example

* **Master Request (Invalid Address):** Master attempts to read Input Register `0x0020` (which does not exist) from Slave ID 1.

  `01 04 00 20 00 01 85 C0`

* **Slave Exception Response:** Returns Function Code `0x84` (`0x04 + 0x80`) and Exception Code `0x02` (Illegal Data Address).

  `01 84 02 C2 C1`

  * `01` — Slave ID 1
  * `04 + 08` → `0x84` — Read Input Registers Exception Indicator
  * `02` — Exception Code (Illegal Data Address)
  * `C2 C1` — CRC-16 Checksum
