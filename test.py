#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
File: test.py
Purpose: 
Author: 
Date Created: 12/01/2025
"""

def check_target_serial_port() -> bool:
    
    TARGET_MANUFACTURER = 'FTDI'
    TARGET_PID = 24597
    TARGET_SERIAL_NUMBERS = {'DK0C1008', 'DK0C1008A'}

    from serial.tools import list_ports
    available_ports = list_ports.comports()

    if not available_ports:
        return False

    for port in available_ports:
        is_manufacturer_match = (port.manufacturer == TARGET_MANUFACTURER)
        is_pid_match = (port.pid == TARGET_PID)
        is_serial_match = (port.serial_number in TARGET_SERIAL_NUMBERS)

        if is_manufacturer_match and is_pid_match and is_serial_match:
            return True 

    return False


if __name__ == "__main__":
    print(check_target_serial_port())