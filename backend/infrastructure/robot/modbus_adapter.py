import time
from backend.utils.logger import logger
from backend.utils import config

try:
    from pyModbusTCP.client import ModbusClient
    MODBUS_AVAILABLE = True
except ImportError:
    MODBUS_AVAILABLE = False
    logger.warning("pyModbusTCP not installed. ModbusAdapter can only run when FAKE_ROBOT=true.")

class ModbusAdapter:
    """
    Handles Industrial Modbus TCP communication with the TM5-700 robotic arm.
    Default Port: 502 (Standard Modbus TCP)
    """
    def __init__(self, host=config.ROBOT_IP, port=config.ROBOT_PORT):
        self.host = host
        self.port = port
        self.client = None
        self.connected = False

    def connect(self):
        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                self.connected = True
                logger.info(f"[MOCK] Robot connected on {self.host}:{self.port} (Modbus TCP)")
                return True
            self.connected = False
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing real robot connection.")
            return False

        try:
            self.client = ModbusClient(host=self.host, port=self.port, auto_open=True, timeout=2.0)
            if self.client.open():
                self.connected = True
                logger.info(f"Robot connected on {self.host}:{self.port} (Modbus TCP)")
                return True
            else:
                logger.error(f"Failed to connect to robot at {self.host}:{self.port}")
                return False
        except Exception as e:
            logger.error(f"Modbus Connection Error: {e}")
            return False

    def send_move(self, coordinates):
        """
        Sends target coordinates to Modbus holding registers.
        Assuming registers 7001-7006 represent X, Y, Z, RX, RY, RZ.
        """
        if not self.connected:
            return False

        if not MODBUS_AVAILABLE:
            if getattr(config, "FAKE_ROBOT", False):
                logger.info(f"[MOCK] Modbus Write: Registers 7000+ -> {coordinates}")
                time.sleep(0.5) # Simulate hardware latency
                return True
            logger.error("pyModbusTCP is required when FAKE_ROBOT=false; refusing motion command.")
            return False

        try:
            # Scale coordinates for register storage (e.g., mm * 100 for 2 decimal precision)
            scaled = [int(c * 100) for c in coordinates]
            success = self.client.write_multiple_registers(7000, scaled)
            if success:
                # Poll status register for 'Motion Complete' (e.g., register 7100)
                return self._wait_for_completion()
            return False
        except Exception as e:
            logger.error(f"Modbus Write Error: {e}")
            return False

    def _wait_for_completion(self, timeout=10):
        """Polls the completion flag from the robot."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Assuming register 7100: 1=Moving, 2=Complete, 3=Error
            status = self.client.read_holding_registers(7100, 1)
            if status and status[0] == 2:
                return True
            elif status and status[0] == 3:
                return False
            time.sleep(0.1)
        return False

    def halt(self):
        """Sends immediate stop signal to register (e.g., register 7099)."""
        if self.connected and MODBUS_AVAILABLE:
            self.client.write_single_register(7099, 1)
        logger.warning("[Modbus] HALT signal sent")

    def disconnect(self):
        if self.client:
            self.client.close()
        self.connected = False
