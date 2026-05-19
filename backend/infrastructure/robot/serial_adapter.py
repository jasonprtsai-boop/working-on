import time
from backend.utils.logger import logger

class SerialAdapter:
    """Handles low-level serial communication with the robotic arm hardware."""
    def __init__(self, port="COM3", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.connected = False

    def connect(self):
        # Mock serial connection
        self.connected = True
        logger.info(f"Robot connected on {self.port}")
        return True

    def send_move(self, gcode_list):
        """Sends a sequence of G-code commands and waits for completion."""
        if not self.connected:
            return False

        for cmd in gcode_list:
            if not self.send_gcode(cmd):
                return False
        return True

    def send_gcode(self, gcode):
        if self.connected:
            logger.debug(f"[Serial] Sending: {gcode}")
            # In a real system, we would wait for 'ok' response from Grbl/Marlin
            time.sleep(0.1)
            return True
        return False

    def disconnect(self):
        self.connected = False
