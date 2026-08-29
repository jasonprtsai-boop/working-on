# Architecture

## 分層

```text
Website
  -> Backend API / Socket.IO
  -> Application services
  -> Vision / Engine / Robot infrastructure
  -> TMvision / Pikafish / TMflow / TM5-700
```

網站不做棋規、AI、路徑規劃、Modbus 或 TMflow 控制。網站只顯示狀態、影像、棋盤、log，並送出「開始」、「我已下棋」、「停止」、「設定」這類高階指令。

## 主流程

```text
Player View
  -> POST /api/player-done
  -> CoordinateWorkflow.player_done()
  -> VisionCaptureSession.start()
  -> VisionSystem / InferenceWorker
  -> VISION_MOVE_DETECTED
  -> chess legality check
  -> ENGINE_ANALYSIS_REQUESTED
  -> EngineWorker / EngineService / Pikafish
  -> ENGINE_ANALYSIS_COMPLETED
  -> RobotFacade.execute_move() only when AUTO_EXECUTE_ROBOT=true
  -> RobotService / ModbusAdapter
  -> TMflow square-command registers
```

`AUTO_EXECUTE_ROBOT=false` 時，AI 走法會停在「已準備好但不送手臂」狀態。

## 主要責任

| 區域 | 目前責任 |
| --- | --- |
| `backend/main.py` | 建立 Flask app、Socket.IO、註冊 API、啟動服務。 |
| `backend/application/bootstrap.py` | 系統啟動與服務接線的集中入口。 |
| `backend/application/container.py` | Runtime service registry。 |
| `backend/application/use_cases/coordinate_workflow.py` | 玩家回合、視覺結果、AI 結果、robot 執行之間的 workflow。 |
| `backend/application/services/vision_service.py` | 將穩定棋盤轉成 move/FEN，發布 vision 事件。 |
| `backend/infrastructure/vision/vision_system.py` | 視覺 runtime owner：source、校正、YOLO、stream、FEN。 |
| `backend/infrastructure/vision/camera/vision_source_manager.py` | `opencv`、`tmvision_http`、`tmflow_json` 來源切換。 |
| `backend/interfaces/api/vision_frame_io.py` | TMvision/TMflow image ingest、snapshot、test frame。 |
| `backend/application/services/engine_service.py` | Pikafish/NNUE lifecycle 與 UCI 分析。 |
| `backend/application/services/robot_facade.py` | 唯一 robot entrypoint，依 fake/real 選 adapter。 |
| `backend/application/services/robot_service.py` | Move planning、adapter 呼叫、安全參數檢查。 |
| `backend/infrastructure/robot/modbus_adapter.py` | Modbus client/server 與 square-command handshake。 |
| `backend/infrastructure/robot/tmflow_socket_ingest_server.py` | TMflow Network Node -> PC TCP telemetry/status ingest。 |
| `backend/application/services/system_preflight.py` | 真機前的 software preflight。 |

## 視覺

目前支援三種來源：

| `VISION_SOURCE` | 用途 |
| --- | --- |
| `opencv` | USB/RTSP/OpenCV，相機直接接 PC。 |
| `tmvision_http` | TMvision/EIH External Classification/Detection POST 到 Python，下一步實測主線。 |
| `tmflow_json` | 舊式 TMflow/base64 JSON frame source，保留作備援。 |

TMvision HTTP ingest endpoint：

```text
POST /api/vision/tmvision/classify
POST /api/vision/tmvision/detect
GET  /api/vision/snapshot
GET  /api/camera/latest
```

`classify` 只需證明影像送達，回：

```json
{"message":"success","result":"frame_received","score":1.0}
```

`detect` 會回 TMvision External Detection 需要的 `annotations`。

## Robot / TMflow

目前推薦真機主線：

```text
Python PC = Modbus TCP server
TMflow = Modbus client/master polling command registers
```

Register contract：

| Register | 方向 | 變數 |
| ---: | --- | --- |
| 40001 | Python -> TMflow | `from_square` |
| 40002 | Python -> TMflow | `to_square` |
| 40003 | Python -> TMflow | `action_type` |
| 40004 | Python -> TMflow | `cmd_id` |
| 40005 | Python -> TMflow | `trigger` |
| 40006 | TMflow -> Python | `status` |
| 40007 | TMflow -> Python | `error_code` |
| 40008 | TMflow -> Python | `completed_cmd_id` |
| 40009 | TMflow -> Python | `heartbeat` |
| 40010 | TMflow -> Python | `robot_state` |

棋格編號：

```text
a0=0, b0=1, ... i0=8
a1=9, b1=10, ... i9=89
```

命令生命週期：

```text
Python writes command + trigger=1
TMflow writes status=1 Busy
TMflow executes safe motion
TMflow writes status=2 Done or status=3 Error
Python sees completed_cmd_id
Python clears trigger=0
TMflow returns Idle
```

## Event Contract

前端應依賴穩定事件：

```text
STATE_UPDATE
ENGINE.INFO_UPDATED
DIAGNOSTICS.UPDATED
VISION.FRAME_PROCESSED
ROBOT.STATUS_UPDATED
UI_TOAST
```

內部事件應優先使用 typed `BaseEvent`。legacy dict event 只作相容，不應新增。

## Queue Policy

| Queue | 容量 | 策略 |
| --- | ---: | --- |
| Vision frame | 1 | latest-only，丟舊保新。 |
| AI detect | 1 | latest-only，避免用過期棋局。 |
| Robot command | 10 | bounded，不自動丟棄。 |
| Persistence | 2000 default | bounded-with-warning，滿載要發 diagnostics。 |
| Legacy frame buffer | 3 | drop-oldest，供 stream/overlay 使用。 |

機械手臂命令有安全語意，不能像影像 frame 一樣被靜默覆蓋。

## Testing Baseline

目前保留測試重點在主線：

```text
TMvision HTTP source
TMvision detection response
minimal website API
workflow preflight gate
vision-to-robot calibration
YOLO/SAHI fallback
frontend player/setup/core smoke tests
```

若要恢復更大的歷史測試覆蓋，應以目前架構重新建，而不是直接搬回舊測試樹。
