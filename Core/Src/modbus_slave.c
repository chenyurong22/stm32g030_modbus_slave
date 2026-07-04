#include "modbus_slave.h"
#include "nanomodbus.h"
#include "usart.h"
#include "gpio.h"
#include <string.h>

extern UART_HandleTypeDef huart2;

// Circular buffer for UART RX
#define RX_BUFFER_SIZE 256
static uint8_t rx_buffer[RX_BUFFER_SIZE];
static volatile uint16_t rx_head = 0;
static volatile uint16_t rx_tail = 0;

static nmbs_t nmbs;
static nmbs_platform_conf platform_conf;
static nmbs_callbacks callbacks;

static uint32_t uid_32bit = 0;
static uint16_t fw_version = 0x0100; // 1.0.0
static uint8_t modbus_slave_id = MODBUS_DEFAULT_SLAVE_ID;
static uint16_t measured_voltage_x100 = 1;      // 0 -> 0.00 V
static uint16_t measured_current_x1000 = 2;     // 0 -> 0.000 A
static uint16_t measured_power_x10 = 3;         // 0 -> 0.0 W
static uint32_t energy_counter_wh = 4;
static uint32_t uptime_seconds = 0;
static uint32_t last_uptime_ms = 0;
static uint16_t last_reset_cause = 2;

static void RS485_DE_Enable(void) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET);
}

static void RS485_DE_Disable(void) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_RESET);
}

// nanoMODBUS Platform Callbacks
static int32_t platform_read(uint8_t* buf, uint16_t count, int32_t byte_timeout_ms, void* arg) {
    uint16_t bytes_read = 0;
    uint32_t start_time = HAL_GetTick();

    while (bytes_read < count) {
        if (rx_head != rx_tail) {
            buf[bytes_read++] = rx_buffer[rx_tail];
            rx_tail = (rx_tail + 1) % RX_BUFFER_SIZE;
            start_time = HAL_GetTick(); // Reset timeout on successful byte read
        } else {
            if (byte_timeout_ms >= 0 && (HAL_GetTick() - start_time) > (uint32_t)byte_timeout_ms) {
                break; // Timeout
            }
        }
    }
    return bytes_read;
}

static int32_t platform_write(const uint8_t* buf, uint16_t count, int32_t byte_timeout_ms, void* arg) {
    RS485_DE_Enable();
    HAL_StatusTypeDef status = HAL_UART_Transmit(&huart2, (uint8_t*)buf, count, byte_timeout_ms > 0 ? byte_timeout_ms * count : HAL_MAX_DELAY);
    RS485_DE_Disable();
    return (status == HAL_OK) ? count : -1;
}

static void update_runtime_counters(void) {
    uint32_t now_ms = HAL_GetTick();
    uint32_t elapsed_ms = now_ms - last_uptime_ms;
    if (elapsed_ms >= 1000U) {
        uint32_t seconds = elapsed_ms / 1000U;
        uptime_seconds += seconds;
        last_uptime_ms += seconds * 1000U;
    }
}

static uint16_t get_reset_cause_code(void) {
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_PWRRST)) {
        return 1;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_PINRST)) {
        return 2;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_IWDGRST)) {
        return 3;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_SFTRST)) {
        return 4;
    }
    if (__HAL_RCC_GET_FLAG(RCC_FLAG_LPWRRST)) {
        return 5;
    }
    return 1;
}

// nanoMODBUS Register Callbacks
static nmbs_error read_holding_registers(uint16_t address, uint16_t quantity, uint16_t* registers_out, uint8_t unit_id, void* arg) {
    (void)unit_id;
    (void)arg;

    for (uint16_t i = 0; i < quantity; i++) {
        uint16_t addr = address + i;

        switch (addr) {
            case 0x0000:
                registers_out[i] = 0;
                break;
            case 0x0001:
                registers_out[i] = modbus_slave_id;
                break;
            default:
                return NMBS_EXCEPTION_ILLEGAL_DATA_ADDRESS;
        }
    }
    return NMBS_ERROR_NONE;
}

static nmbs_error read_input_registers(uint16_t address, uint16_t quantity, uint16_t* registers_out, uint8_t unit_id, void* arg) {
    (void)unit_id;
    (void)arg;

    for (uint16_t i = 0; i < quantity; i++) {
        uint16_t addr = address + i;

        switch (addr) {
            case 0x0000:
                registers_out[i] = measured_voltage_x100;
                break;
            case 0x0001:
                registers_out[i] = measured_current_x1000;
                break;
            case 0x0002:
                registers_out[i] = measured_power_x10;
                break;
            case 0x0003:
                registers_out[i] = (energy_counter_wh >> 16) & 0xFFFFU;
                break;
            case 0x0004:
                registers_out[i] = energy_counter_wh & 0xFFFFU;
                break;
            case 0x0005:
                registers_out[i] = (uptime_seconds >> 16) & 0xFFFFU;
                break;
            case 0x0006:
                registers_out[i] = uptime_seconds & 0xFFFFU;
                break;
            case 0x0007:
                registers_out[i] = fw_version;
                break;
            case 0x0008:
                registers_out[i] = last_reset_cause;
                break;
            default:
                return NMBS_EXCEPTION_ILLEGAL_DATA_ADDRESS;
        }
    }
    return NMBS_ERROR_NONE;
}

static nmbs_error write_single_register(uint16_t address, uint16_t value, uint8_t unit_id, void* arg) {
    (void)unit_id;
    (void)arg;

    switch (address) {
        case 0x0000:
            if (value != 12345U) {
                return NMBS_EXCEPTION_ILLEGAL_DATA_VALUE;
            }
            energy_counter_wh = 0;
            break;
        case 0x0001:
            if (value < 1U || value > 247U) {
                return NMBS_EXCEPTION_ILLEGAL_DATA_VALUE;
            }
            modbus_slave_id = (uint8_t)value;
            nmbs_server_create(&nmbs, modbus_slave_id, &platform_conf, &callbacks);
            break;
        default:
            return NMBS_EXCEPTION_ILLEGAL_DATA_ADDRESS;
    }
    return NMBS_ERROR_NONE;
}

static nmbs_error write_multiple_registers(uint16_t address, uint16_t quantity, const uint16_t* registers,
                                           uint8_t unit_id, void* arg) {
    (void)unit_id;
    (void)arg;

    if (quantity != 1U) {
        return NMBS_EXCEPTION_ILLEGAL_DATA_VALUE;
    }

    switch (address) {
        case 0x0000:
            if (registers[0] != 12345U) {
                return NMBS_EXCEPTION_ILLEGAL_DATA_VALUE;
            }
            energy_counter_wh = 0;
            break;
        case 0x0001:
            if (registers[0] < 1U || registers[0] > 247U) {
                return NMBS_EXCEPTION_ILLEGAL_DATA_VALUE;
            }
            modbus_slave_id = (uint8_t)registers[0];
            nmbs_server_create(&nmbs, modbus_slave_id, &platform_conf, &callbacks);
            break;
        default:
            return NMBS_EXCEPTION_ILLEGAL_DATA_ADDRESS;
    }
    return NMBS_ERROR_NONE;
}

void Modbus_Init(void) {
    // Squeeze 96-bit UID into 32-bit (XORing the 3 words)
    uint32_t uid0 = HAL_GetUIDw0();
    uint32_t uid1 = HAL_GetUIDw1();
    uint32_t uid2 = HAL_GetUIDw2();
    uid_32bit = uid0 ^ uid1 ^ uid2;
    last_reset_cause = get_reset_cause_code();
    last_uptime_ms = HAL_GetTick();

    RS485_DE_Disable();

    // Disable hardware RTO (Receiver Timeout) as nanoMODBUS handles timing
    __HAL_UART_DISABLE_IT(&huart2, UART_IT_RTO);
    
    // Enable RXNE interrupt
    __HAL_UART_ENABLE_IT(&huart2, UART_IT_RXNE);

    // Initialize nanoMODBUS platform conf
    nmbs_platform_conf_create(&platform_conf);
    platform_conf.transport = NMBS_TRANSPORT_RTU;
    platform_conf.read = platform_read;
    platform_conf.write = platform_write;
    platform_conf.arg = NULL;

    // Initialize nanoMODBUS callbacks
    nmbs_callbacks_create(&callbacks);
    callbacks.read_holding_registers = read_holding_registers;
    callbacks.read_input_registers = read_input_registers;
    callbacks.write_single_register = write_single_register;
    callbacks.write_multiple_registers = write_multiple_registers;

    // Create nanoMODBUS instance
    nmbs_server_create(&nmbs, MODBUS_DEFAULT_SLAVE_ID, &platform_conf, &callbacks);
    // nmbs_set_read_timeout(&nmbs, 3000); // 100ms timeout
    nmbs_set_byte_timeout(&nmbs, 20);  // 20ms byte timeout (modbus inter-character timeout)
}

void Modbus_Process(void) {
    update_runtime_counters();
    nmbs_server_poll(&nmbs);
}

void Modbus_UART_IRQHandler(void) {
    if (__HAL_UART_GET_FLAG(&huart2, UART_FLAG_RXNE) != RESET) {
        uint8_t data = (uint8_t)(huart2.Instance->RDR & 0xFF);
        uint16_t next_head = (rx_head + 1) % RX_BUFFER_SIZE;
        if (next_head != rx_tail) {
            rx_buffer[rx_head] = data;
            rx_head = next_head;
        }
    }
    
    // Clear overrun error if it happens
    if (__HAL_UART_GET_FLAG(&huart2, UART_FLAG_ORE) != RESET) {
        __HAL_UART_CLEAR_FLAG(&huart2, UART_CLEAR_OREF);
    }
}
