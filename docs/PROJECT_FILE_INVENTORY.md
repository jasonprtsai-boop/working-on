# 專案檔案整理與清理判定

盤點日期：2026-10-05。範圍：目前 working-on 工作目錄，不含上層其他專案。以檔案清單、入口、引用搜尋及設定檔判定用途；未執行真機，也未宣稱完成所有程式的可達性分析。Word 文件保留。

## 目錄用途

| 位置 | 用途與處理原則 |
| --- | --- |
| backend/ | 後端、事件、狀態、視覺、引擎與機械手臂；保留。 |
| frontend/ | Flask 網頁、靜態資源及前端測試；保留。 |
| tests/ | 後端測試；保留。 |
| scripts/ | 啟動、檢查、校正、診斷與發佈工具；命令列入口沒有被 import 不等於無用。 |
| config/、robot/ | 校正輸入與棋盤座標；保留。 |
| docs/ | 操作文件、設計來源與產生的圖；先處理版本衝突。 |
| data/ | SQLite、設定、校正、commissioning 與拍攝資料；不是垃圾目錄。 |
| logs/ | 執行紀錄與棋局／Excel 匯出；可按保留期限封存。 |
| .tools/ | 專案使用的本機工具；Node 被 node24.cmd、npm24.cmd、check_system.ps1 直接引用。 |
| .git/、.github/ | 版本歷史與 CI；保留。 |

## 可清理的檔案

| 項目 | 判定 | 具體處理 |
| --- | --- | --- |
| backend/、scripts/、tests/ 下 61 個 __pycache__ 目錄 | 可再產生的 Python 快取 | 關閉程式後可刪除；不影響原始碼。 |
| debug.log（153 bytes） | 除錯輸出 | 不需保存該次除錯證據時可刪除。 |
| snapshots/ | 本次檢查無檔案 | 可移除空目錄；執行時仍可重建。 |
| logs/exports/ 的 13 份 Excel | 歷史匯出，不是啟動必要資產 | 建議移至資料封存位置；不直接當作無關資料刪除。 |
| logs/game_records/ 的 13 份 Excel | 歷史棋局資料 | 同上；可能有實驗價值。 |
| chess_robot_experiment.xlsx（5120 bytes） | 實驗表，非原始碼 | 可移至實驗資料目錄；未檢查內容，不能判定可丟棄。 |
| data/tmvision_captures/ 的 4 張影像 | 歷史拍攝資料 | 如無校正／診斷需求可封存；未視覺檢查內容。 |

## 文件問題與需確認項目

1. README 引用 reports/document_cleanup_20260920/、markdown_before_cleanup.zip，但目前 reports/ 已不存在。該還原敘述不可再當有效還原指引。
2. README 與 SYSTEM_TMFLOW_KNOWLEDGE.txt 確認單張影像；FULL_NODE_DESIGN、FIELD_OPERATION_MANUAL 與多份產圖仍描述 v3.0 雙張流程。舊設計應標示歷史用途；不應直接用於現場設定。
3. docs/tmflow_v3_nodes.json 是 generate_tmflow_left_palette_diagrams.mjs 的輸入，NODE_SETUP_GUIDE 與圖由它產生。修訂應從來源模型開始，再同步產物，避免逐張修改或直接刪圖造成不一致。
4. PNG 與 SVG 屬同一設計的不同輸出格式，不是已確認無用副本。可日後選一種展示格式，但需同步修改文件連結、產圖工具及檢查。
5. scripts/maintenance/vacuum_db.py 沒有找到外部呼叫，但可獨立執行且針對本專案資料庫，暫保留。它直接複製 DB 作備份；若資料庫仍在寫入或使用 WAL，不應把這種備份視為一致性保證。
6. .tools/python-3.10.11/ 未出現在 python_resolver.mjs 的候選清單；仍可能供人工操作使用。需確認實際 Python 執行位置後才可移除整套工具，不能按第三方檔名逐檔刪除。

## 容易誤刪但仍必要

- frontend/index.html 被 backend/main.py 的 render_template 使用。
- backend/state/store/legacy_models.py 被 board_reducer 使用。
- backend/events/store/event_store.py 是 SQLite 儲存的相容介面，replay/export 仍引用。
- backend/runtime/workers/worker_manager.py 被 bootstrap 與 runtime_reports 使用。
- requirements.runtime.txt、requirements.vision.txt 被安裝與 CI 使用；requirements.lock.txt 被依賴稽核使用。用途不同，不能因套件重複就刪檔。
- 模型、引擎、.env、實機設定、data/runtime/app.db 及校正 JSON 保留。

## 額外發現

受保護資產的 pikafish.nnue 目前缺失。這是既有工作樹狀態，不能視為清理成果；真實引擎 readiness 需另行驗證。此盤點沒有下載或還原資產。

## 執行紀錄

本次新增用途與清理清單；未搬移核心目錄或刪除上述待確認項目。先前已清除代理人暫存、研究暫存與 _archive 舊備份。整理優先順序：修正失效文件連結 → 標示／統一 TMflow 設計版本 → 清理快取 → 封存歷史匯出。

後續執行（2026-10-05）：已刪除 61 個 Python 快取目錄、debug.log 與空 snapshots；26 份歷史 Excel、實驗表與 4 張拍攝影像移至 data/archive/20261005/，可移回原位置。README 失效還原敘述已修正；4 份舊 TMflow 文件已加上過期警告。PNG/SVG 同步因缺少 Node 24 執行檔及 Playwright 未完成，不能宣稱版本已統一。系統 Node 為 25.9.0，不符 package.json 的 24.x 要求；Python 啟動器亦找不到已安裝版本，因此保留 .tools/python-3.10.11/。不執行 vacuum_db.py，避免改動運作資料庫。

NNUE 複查：搜尋目前專案及 C:/Users/user/Desktop/專題 全部可讀目錄未找到 *.nnue；.env 指定的 backend/infrastructure/protected_assets/engine/pikafish.nnue 不存在。此結論只涵蓋上述搜尋範圍，不表示其他磁碟或壓縮檔內沒有模型。

後續更正：檢查 ZIP 內容後，在 code-15、16、17、18、19、20、21、23 壓縮包內找到模型。已從 C:/Users/user/Desktop/專題/專題程式/壓縮/code-23.zip 複製還原 pikafish.nnue，大小 53,212,941 bytes，SHA256 C4026370D7516D9B0F668447F9CA1931241538BDC689CDE6FEC6A991AC4D5F77，符合受保護資產清單；來源 ZIP 保留。已驗證檔案完整性，尚未執行引擎 runtime 驗證。搜尋曾遇到 15 個 test/.test_deps 存取拒絕，因此不宣稱已讀取所有子目錄。
