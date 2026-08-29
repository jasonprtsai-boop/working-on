# Configuration

## 讀取順序

設定來源不只 `.env`。目前 development 模式會依下列來源組合：

```text
.env
  + backend/config.yaml if present
  + data/setup_settings.json for setup-managed robot/vision values
```

因此看到 `.env` 裡某個值，不代表最後一定生效。像目前 robot Modbus port，`.env` 可能寫 `502`，但 `data/setup_settings.json` 會把實際值覆蓋成 `1502`。

## Profile 分工

| Profile | `APP_ENV` | `SYSTEM_MODE` | 用途 |
| --- | --- | --- |
| Simulation | `development` | `simulation` | 沒接硬體的安全首跑。 |
| Lab real robot | `development` | `lab_real_robot` | 實驗室真機測試，仍保留開發彈性。 |
| Production | `production` | `production` | 真正正式部署，啟動嚴格安全檢查。 |

`APP_ENV` 是安全等級；`SYSTEM_MODE` 是系統語意。不要用 `SYSTEM_MODE=production` 取代 `APP_ENV=production`。

## Simulation 建議

```env
APP_ENV=development
SYSTEM_MODE=simulation
SMART_CHESS_HOST=127.0.0.1
SMART_CHESS_BIND_ALL=false
FAKE_ROBOT=true
FAKE_VISION=true
FAKE_AI=true
AUTO_EXECUTE_ROBOT=false
ENGINE_AUTO_ANALYZE=false
VISION_SOURCE=opencv
```

## Lab Real Robot 建議

用於 TMvision/EIH 與 TMflow/TM5-700 現場測試：

```env
APP_ENV=development
SYSTEM_MODE=lab_real_robot
SMART_CHESS_BIND_ALL=1
SMART_CHESS_HOST=0.0.0.0
PORT=5000
CHESS_SECRET_KEY=replace-with-32-plus-character-secret
CORS_ALLOWED_ORIGINS=http://192.168.10.50:5000

FAKE_ROBOT=false
FAKE_VISION=false
FAKE_AI=false
AUTO_EXECUTE_ROBOT=false

ROBOT_IP=192.168.10.10
ROBOT_PC_IP=192.168.10.50
ROBOT_SUBNET_MASK=255.255.0.0

VISION_SOURCE=tmvision_http
VISION_TMFLOW_INGEST_KEY=replace-with-shared-tmvision-key

TMFLOW_INGEST_SERVER_ENABLED=true
TMFLOW_INGEST_SERVER_HOST=0.0.0.0
TMFLOW_INGEST_SERVER_PORT=9001
TMFLOW_INGEST_KEY=replace-with-shared-telemetry-key

ROBOT_ADAPTER=modbus
ROBOT_MODBUS_ROLE=server
ROBOT_MODBUS_SERVER_HOST=192.168.10.50
ROBOT_MODBUS_SERVER_PORT=1502
ROBOT_MODBUS_PAYLOAD_MODE=square_command
```

注意：只要 `VISION_SOURCE=tmvision_http` 且是 real/shared network，就必須設定 `VISION_TMFLOW_INGEST_KEY`。這是避免任何同網段裝置都能任意 POST 圖片進後端。

## Production 必要條件

真正正式部署時，`scripts/check_production_config.py --current --require-production` 會要求：

- `APP_ENV=production`
- `SYSTEM_MODE` 不能是 `simulation`、`test`、`demo`
- `FAKE_ROBOT=false`
- `FAKE_VISION=false`
- `FAKE_AI=false`
- `VISION_ALLOW_SIMULATION_FALLBACK=false`
- `CONTROL_AUTH_REQUIRED=true`
- `RATE_LIMITS_ENABLED=true`
- `SOCKET_PUBLIC_SNAPSHOT_ENABLED=false`
- `EVENTBUS_ALLOW_LEGACY_DICT_EVENTS=false`
- `CHESS_SECRET_KEY` 是強密鑰
- `DB_PATH` 與 `JWT_REVOCATION_DB_PATH` 是非 memory 的絕對路徑
- bind-all 時必須 `SMART_CHESS_BIND_ALL=1`
- TMvision/TMflow ingest 必須有非空 key

## Env 檢查結果

本次整理檢查到：

- `.env` 裡的 `ROBOT_COMMAND_QUEUE_SIZE` 沒有被目前程式讀取，已從本機 `.env` 移除。
- `.env.example` 補齊程式可讀但原本未文件化的設定，例如 `SETUP_SETTINGS_FILE`、`JWT_REVOCATION_DB_PATH`、OpenCV capture 參數、vision degrade 參數、robot XYZ limits、tool rotation、Modbus telemetry。
- 沒有把實際 `.env` 的密碼或密鑰寫進文件。

## 常見誤解

### `APP_ENV=development` 不是錯誤

實驗室測 TMvision/TMflow 時可以維持 development，這樣比較容易調整設定。它只代表「還不是正式部署安全等級」。

### `SYSTEM_MODE=production` 容易誤導

它不會自動啟動 production security。若只是接真機測試，請用 `SYSTEM_MODE=lab_real_robot`。

### `AUTO_EXECUTE_ROBOT=false` 是目前最重要的保護之一

即使 AI 算出走法，也不會自動送手臂。要打開前必須完成 TMvision、Modbus、點位、吸盤、安全高度、急停等現場測試。
