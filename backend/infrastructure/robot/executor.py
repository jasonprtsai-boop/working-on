import time
import asyncio
from backend.utils.logger import logger
from .modbus_adapter import ModbusAdapter

class RobotExecutor:
    """
    [Infrastructure Layer] Physical Robot Command Executor.
    Responsibility: Sending raw commands to the hardware via Modbus.
    """
    def __init__(self, adapter: ModbusAdapter):
        self.adapter = adapter

    async def execute_command(self, command: str) -> bool:
        """Sends a G-code or Modbus command to the robot."""
        logger.debug(f"[Executor] Sending: {command}")

        # In a real Modbus setup, we might map G-code to registers
        # For now, we use the adapter's send_move
        success = self.adapter.send_move(command)

        if not success:
            logger.error(f"[Executor] Command failed: {command}")
            return False

        return True

    async def halt(self):
        """Emergency halt."""
        logger.critical("[Executor] EMERGENCY HALT REQUESTED")
        self.adapter.halt()

    async def reset(self):
        """Reset hardware state."""
        self.adapter.reset()
