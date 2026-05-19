from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple
import hashlib
import json
import uuid

@dataclass(frozen=True)
class PieceState:
    piece_id: str
    piece_type: str
    color: str
    position: str

@dataclass(frozen=True)
class BoardState:
    fen: str
    turn: str
    move_number: int
    pieces: Tuple[PieceState, ...]
    move_history: Tuple[str, ...]

@dataclass(frozen=True)
class VisionState:
    last_confidence: float
    last_detection_time: datetime
    camera_online: bool

@dataclass(frozen=True)
class RobotState:
    robot_online: bool
    current_action: str
    last_completed_move: Optional[str]

@dataclass(frozen=True)
class EngineState:
    engine_online: bool
    last_analysis_depth: int
    last_score_cp: Optional[int]

@dataclass(frozen=True)
class GameState:
    snapshot_id: str
    version: int

    board: BoardState
    vision: VisionState
    robot: RobotState
    engine: EngineState

    created_at: datetime
    state_hash: str

    @staticmethod
    def create_initial():
        board = BoardState(
            fen="initial",
            turn="red",
            move_number=0,
            pieces=tuple(),
            move_history=tuple(),
        )
        vision = VisionState(
            last_confidence=0.0,
            last_detection_time=datetime.utcnow(),
            camera_online=True,
        )
        robot = RobotState(
            robot_online=True,
            current_action="idle",
            last_completed_move=None,
        )
        engine = EngineState(
            engine_online=True,
            last_analysis_depth=0,
            last_score_cp=None,
        )
        temp = GameState(
            snapshot_id=str(uuid.uuid4()),
            version=1,
            board=board,
            vision=vision,
            robot=robot,
            engine=engine,
            created_at=datetime.utcnow(),
            state_hash="",
        )
        return temp.with_hash()

    def with_hash(self):
        serialized = json.dumps({
            "fen": self.board.fen,
            "turn": self.board.turn,
            "move_number": self.board.move_number,
            "moves": self.board.move_history,
        }, sort_keys=True)

        hashed = hashlib.sha256(serialized.encode()).hexdigest()

        return GameState(
            snapshot_id=self.snapshot_id,
            version=self.version,
            board=self.board,
            vision=self.vision,
            robot=self.robot,
            engine=self.engine,
            created_at=self.created_at,
            state_hash=hashed,
        )

    def to_dict(self):
        """Standardized serialization for frontend/export."""
        return {
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "board": {
                "fen": self.board.fen,
                "turn": self.board.turn,
                "move_number": self.board.move_number,
                "moves": list(self.board.move_history)
            },
            "vision": {
                "confidence": self.vision.last_confidence,
                "online": self.vision.camera_online
            },
            "robot": {
                "online": self.robot.robot_online,
                "status": self.robot.current_action
            },
            "engine": {
                "online": self.engine.engine_online,
                "depth": self.engine.last_analysis_depth,
                "score": self.engine.last_score_cp
            },
            "hash": self.state_hash,
            "timestamp": self.created_at.isoformat()
        }
