"""List available serial ports using pyserial."""

from serial.tools import list_ports


def list_serial_ports():
    """Return a list of available serial port device names."""
    return [port.device for port in list_ports.comports()]


if __name__ == "__main__":
    ports = list_serial_ports()
    if not ports:
        print("No serial ports found.")
    else:
        print("Available serial ports:")
        for port in ports:
            print(f"- {port}")
