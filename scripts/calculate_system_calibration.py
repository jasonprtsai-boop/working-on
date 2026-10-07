"""
S.M.A.R.T. Chess Robot - 系統設定計算與同步工具 (v2.0 雙半區與象棋河界規則強化版)
讀取 config/system_parameters.json，支援：
1. 楚河漢界雙半區獨立仿射計算：
   - 上半區（黑方半盤 Ranks 5~9）：左上角 (a9) 與 右下角 (i5)
   - 下半區（紅方半盤 Ranks 0~4）：左上角 (a4) 與 右下角 (i0)
2. 楚河漢界（River）實際間距與擴展倍率分析
3. 中國象棋棋盤幾何與規則約束驗證：
   - 紅黑雙方九宮格（Palace）斜線交叉與天元中心 (e1, e8) 對齊
   - 相/象活動範圍不可過河限制（紅相 7 點、黑象 7 點）
   - 兵/卒過河前後走子規則檢驗
4. 全盤 90 棋格（a0~i9）毫米座標精準推算與安全邊界檢查
5. 相機透視校正矩陣生成
6. 自動同步寫入系統設定檔 (robot/calibration.json, data/setup_settings.json, data/vision_calibration.json)
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.kinematics import Kinematics
from backend.infrastructure.vision.calibration import (
    compute_calibration_quality,
    compute_warp_matrix,
    normalize_corners,
)


def load_config(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        raise FileNotFoundError(f"找不到設定檔：{file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fit_2d_affine(samples: List[Tuple[float, float, float, float]]) -> List[List[float]]:
    """Fit a 2x3 affine matrix: [x, y]^T = M * [col, row]^T + [tx, ty]^T."""
    pts_src = []
    pts_dst = []
    for col, row, x, y in samples:
        pts_src.append([col, row, 1.0])
        pts_dst.append([x, y])

    A = np.array(pts_src, dtype=np.float64)
    B = np.array(pts_dst, dtype=np.float64)
    # Solve A * M^T = B
    M_T, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    M = M_T.T  # 2x3
    return M.tolist()


def calculate_split_halves_kinematics(
    board_cfg: Dict[str, Any],
    limits_cfg: Dict[str, Any],
) -> Tuple[Kinematics, Dict[str, Any]]:
    """
    根據使用者提供的：
    - 上半區：左上角 (a9) 與 右下角 (i5)
    - 下半區：左上角 (a4) 與 右下角 (i0)
    分別計算上下半盤座標，並精確處理楚河漢界寬度。
    """
    upper_cfg = board_cfg.get("upper_half", {})
    lower_cfg = board_cfg.get("lower_half", {})

    u_tl = upper_cfg.get("top_left", {})       # a9
    u_br = upper_cfg.get("bottom_right", {})   # i5
    u_bl = upper_cfg.get("optional_bottom_left", {})  # a5
    u_tr = upper_cfg.get("optional_top_right", {})    # i9

    l_tl = lower_cfg.get("top_left", {})       # a4
    l_br = lower_cfg.get("bottom_right", {})   # i0
    l_bl = lower_cfg.get("optional_bottom_left", {})  # a0
    l_tr = lower_cfg.get("optional_top_right", {})    # i4

    # 1. 下半區 (紅方，Rank 0..4, Col 0..8)
    l_tl_x, l_tl_y = float(l_tl.get("x", 0.0)), float(l_tl.get("y", 260.0))  # a4
    l_br_x, l_br_y = float(l_br.get("x", 320.0)), float(l_br.get("y", 100.0)) # i0

    # 推導或讀取 a0 與 i4
    l_bl_x = float(l_bl.get("x")) if l_bl.get("x") is not None else l_tl_x
    l_bl_y = float(l_bl.get("y")) if l_bl.get("y") is not None else l_br_y  # a0
    l_tr_x = float(l_tr.get("x")) if l_tr.get("x") is not None else l_br_x
    l_tr_y = float(l_tr.get("y")) if l_tr.get("y") is not None else l_tl_y  # i4

    lower_samples = [
        (0.0, 4.0, l_tl_x, l_tl_y),  # a4: col 0, row 4
        (8.0, 0.0, l_br_x, l_br_y),  # i0: col 8, row 0
        (0.0, 0.0, l_bl_x, l_bl_y),  # a0: col 0, row 0
        (8.0, 4.0, l_tr_x, l_tr_y),  # i4: col 8, row 4
    ]
    lower_affine = _fit_2d_affine(lower_samples)

    # 2. 上半區 (黑方，Rank 5..9 -> relative 0..4, Col 0..8)
    u_tl_x, u_tl_y = float(u_tl.get("x", 0.0)), float(u_tl.get("y", 460.0))   # a9
    u_br_x, u_br_y = float(u_br.get("x", 320.0)), float(u_br.get("y", 300.0)) # i5

    # 推導或讀取 a5 與 i9
    u_bl_x = float(u_bl.get("x")) if u_bl.get("x") is not None else u_tl_x
    u_bl_y = float(u_bl.get("y")) if u_bl.get("y") is not None else u_br_y  # a5
    u_tr_x = float(u_tr.get("x")) if u_tr.get("x") is not None else u_br_x
    u_tr_y = float(u_tr.get("y")) if u_tr.get("y") is not None else u_tl_y  # i9

    upper_samples = [
        (0.0, 4.0, u_tl_x, u_tl_y),  # a9: col 0, relative row 4
        (8.0, 0.0, u_br_x, u_br_y),  # i5: col 8, relative row 0
        (0.0, 0.0, u_bl_x, u_bl_y),  # a5: col 0, relative row 0
        (8.0, 4.0, u_tr_x, u_tr_y),  # i9: col 8, relative row 4
    ]
    upper_affine = _fit_2d_affine(upper_samples)

    # 3. 楚河漢界 (River) 幾何分析
    # a4 到 a5 的距離為左側河寬；i4 到 i5 為右側河寬
    river_w_left = math.hypot(u_bl_x - l_tl_x, u_bl_y - l_tl_y)
    river_w_right = math.hypot(u_br_x - l_tr_x, u_br_y - l_tr_y)
    river_w_avg = (river_w_left + river_w_right) / 2.0

    lower_sq_x = float(math.hypot(lower_affine[0][0], lower_affine[1][0]))
    lower_sq_y = float(math.hypot(lower_affine[0][1], lower_affine[1][1]))
    upper_sq_x = float(math.hypot(upper_affine[0][0], upper_affine[1][0]))
    upper_sq_y = float(math.hypot(upper_affine[0][1], upper_affine[1][1]))

    avg_sq_y = (lower_sq_y + upper_sq_y) / 2.0
    river_ratio = river_w_avg / avg_sq_y if avg_sq_y > 0 else 1.0
    river_parallel_diff = abs(river_w_left - river_w_right)
    horizontal_offset = abs(u_bl_x - l_tl_x)

    # 4. 逆變換矩陣 (用於手臂 XY 轉棋格)
    def invert_aff(m):
        a, b, c = m[0]
        d, e, f = m[1]
        det = a * e - b * d
        if abs(det) < 1e-9:
            det = 1e-9
        return [
            [e / det, -b / det, -(e * c - b * f) / det],
            [-d / det, a / det, -(-d * c + a * f) / det],
        ]

    lower_inv = invert_aff(lower_affine)
    upper_inv = invert_aff(upper_affine)

    split_halves_data = {
        "lower_affine": lower_affine,
        "upper_affine": upper_affine,
        "lower_inverse_affine": lower_inv,
        "upper_inverse_affine": upper_inv,
        "lower_square_size": {"dx": round(lower_sq_x, 3), "dy": round(lower_sq_y, 3)},
        "upper_square_size": {"dx": round(upper_sq_x, 3), "dy": round(upper_sq_y, 3)},
        "river": {
            "width_left_mm": round(river_w_left, 2),
            "width_right_mm": round(river_w_right, 2),
            "average_width_mm": round(river_w_avg, 2),
            "width_ratio_to_grid": round(river_ratio, 3),
            "parallel_diff_mm": round(river_parallel_diff, 3),
            "horizontal_shift_mm": round(horizontal_offset, 3),
        },
    }

    # 5. 全局 Kinematics 實例配置
    dead_zone_cfg = board_cfg.get("dead_zone") or {}
    dead_zone_arg = {
        "x": float(dead_zone_cfg.get("x", 420.0)),
        "y": float(dead_zone_cfg.get("y", 100.0)),
        "z": float(dead_zone_cfg.get("z", 20.0)),
        "width": float(dead_zone_cfg.get("width", 80.0)),
        "height": float(dead_zone_cfg.get("height", 80.0)),
        "slot_spacing": float(dead_zone_cfg.get("slot_spacing", 25.0)),
        "slot_count": int(dead_zone_cfg.get("slot_count", 4)),
    }

    k = Kinematics()
    k.origin_x = l_bl_x
    k.origin_y = l_bl_y
    k.square_size_x = round((lower_sq_x + upper_sq_x) / 2.0, 3)
    k.square_size_y = round(avg_sq_y, 3)
    k.split_halves = split_halves_data
    k.dead_zone = (dead_zone_arg["x"], dead_zone_arg["y"])
    k.dead_zone_range = dead_zone_arg

    # 計算全域等效 2x3 仿射矩陣（方便向下相容）
    global_samples = lower_samples + [
        (col, row + 5.0, x, y) for col, row, x, y in upper_samples
    ]
    global_affine = _fit_2d_affine(global_samples)
    k.affine_matrix = global_affine

    # 6. 計算 90 個棋格座標
    files = "abcdefghi"
    ranks = "0123456789"
    grid_coords = {}
    limit_violations = []

    min_x = float(limits_cfg.get("min_x", -600.0))
    max_x = float(limits_cfg.get("max_x", 600.0))
    min_y = float(limits_cfg.get("min_y", 100.0))
    max_y = float(limits_cfg.get("max_y", 600.0))

    for r in ranks:
        r_int = int(r)
        for f in files:
            sq = f"{f}{r}"
            c_idx = files.index(f)
            if r_int <= 4:
                x = lower_affine[0][0] * c_idx + lower_affine[0][1] * r_int + lower_affine[0][2]
                y = lower_affine[1][0] * c_idx + lower_affine[1][1] * r_int + lower_affine[1][2]
            else:
                rel_r = r_int - 5
                x = upper_affine[0][0] * c_idx + upper_affine[0][1] * rel_r + upper_affine[0][2]
                y = upper_affine[1][0] * c_idx + upper_affine[1][1] * rel_r + upper_affine[1][2]

            norm_x = round(float(x), 2) + 0.0
            norm_y = round(float(y), 2) + 0.0
            grid_coords[sq] = {"x": norm_x, "y": norm_y}
            if not (min_x - 1e-3 <= float(x) <= max_x + 1e-3 and min_y - 1e-3 <= float(y) <= max_y + 1e-3):
                limit_violations.append(f"{sq}: ({norm_x}, {norm_y}) 超出範圍 [{min_x}~{max_x}, {min_y}~{max_y}]")

    # 死棋盒槽位
    dead_zone_slots = []
    for slot_idx in range(1, dead_zone_arg["slot_count"] + 1):
        dz_x, dz_y = k.get_dead_zone_coords(slot_idx)
        norm_dz_x = round(float(dz_x), 2) + 0.0
        norm_dz_y = round(float(dz_y), 2) + 0.0
        dead_zone_slots.append({"slot": slot_idx, "x": norm_dz_x, "y": norm_dz_y})
        if not (min_x - 1e-3 <= float(dz_x) <= max_x + 1e-3 and min_y - 1e-3 <= float(dz_y) <= max_y + 1e-3):
            limit_violations.append(f"死棋槽位 {slot_idx}: ({norm_dz_x}, {norm_dz_y}) 超出邊界")

    # 7. 中國象棋規則約束幾何檢查 (Rules Check)
    rule_checks = []

    # (A) 九宮格斜線中心檢查：紅方 e1、黑方 e8
    # 紅方九宮中心為 (d0+f2)/2 與 (f0+d2)/2
    d0, f2 = grid_coords["d0"], grid_coords["f2"]
    f0, d2 = grid_coords["f0"], grid_coords["d2"]
    e1 = grid_coords["e1"]
    diag1_mid = ((d0["x"] + f2["x"]) / 2, (d0["y"] + f2["y"]) / 2)
    diag2_mid = ((f0["x"] + d2["x"]) / 2, (f0["y"] + d2["y"]) / 2)
    red_palace_err = max(math.hypot(diag1_mid[0] - e1["x"], diag1_mid[1] - e1["y"]),
                         math.hypot(diag2_mid[0] - e1["x"], diag2_mid[1] - e1["y"]))
    rule_checks.append({
        "rule": "紅方九宮格斜線交會於天元 (e1)",
        "center_square": "e1",
        "error_mm": round(red_palace_err, 3),
        "passed": red_palace_err < 1.0,
    })

    # 黑方九宮中心為 (d7+f9)/2 與 (f7+d9)/2
    d7, f9 = grid_coords["d7"], grid_coords["f9"]
    f7, d9 = grid_coords["f7"], grid_coords["d9"]
    e8 = grid_coords["e8"]
    b_diag1_mid = ((d7["x"] + f9["x"]) / 2, (d7["y"] + f9["y"]) / 2)
    b_diag2_mid = ((f7["x"] + d9["x"]) / 2, (f7["y"] + d9["y"]) / 2)
    black_palace_err = max(math.hypot(b_diag1_mid[0] - e8["x"], b_diag1_mid[1] - e8["y"]),
                           math.hypot(b_diag2_mid[0] - e8["x"], b_diag2_mid[1] - e8["y"]))
    rule_checks.append({
        "rule": "黑方九宮格斜線交會於天元 (e8)",
        "center_square": "e8",
        "error_mm": round(black_palace_err, 3),
        "passed": black_palace_err < 1.0,
    })

    # (B) 相/象不可過河檢查 (Elephant / Bishop River Boundary)
    red_elephants = ["c0", "g0", "a2", "e2", "i2", "c4", "g4"]
    black_elephants = ["c9", "g9", "a7", "e7", "i7", "c5", "g5"]
    max_red_y = max(grid_coords[sq]["y"] for sq in red_elephants)
    min_black_y = min(grid_coords[sq]["y"] for sq in black_elephants)
    river_clearance = min_black_y - max_red_y
    rule_checks.append({
        "rule": "相/象不可過河（紅相 Y <= a4.y, 黑象 Y >= a5.y）",
        "red_elephant_max_y": round(max_red_y, 2),
        "black_elephant_min_y": round(min_black_y, 2),
        "river_gap_clearance_mm": round(river_clearance, 2),
        "passed": river_clearance >= 0,
    })

    # (C) 兵/卒過河交界線檢查
    rule_checks.append({
        "rule": "兵卒過河交界線（紅兵 Rank 3->4 渡河至 5；黑卒 Rank 6->5 渡河至 4）",
        "red_river_bank_y": grid_coords["e4"]["y"],
        "black_river_bank_y": grid_coords["e5"]["y"],
        "passed": grid_coords["e5"]["y"] > grid_coords["e4"]["y"],
    })

    # 8. 驗證獨立檢驗點 (validation_points)
    val_points = board_cfg.get("validation_points") or []
    val_results = []
    for vp in val_points:
        sq = vp.get("square", "").lower().strip()
        meas_x = float(vp.get("x", 0.0))
        meas_y = float(vp.get("y", 0.0))
        pred = grid_coords.get(sq)
        if pred is not None:
            err_x = pred["x"] - meas_x
            err_y = pred["y"] - meas_y
            err_dist = math.hypot(err_x, err_y)
            val_results.append({
                "square": sq,
                "description": vp.get("description", ""),
                "measured": {"x": meas_x, "y": meas_y},
                "predicted": pred,
                "error_x_mm": round(err_x, 3),
                "error_y_mm": round(err_y, 3),
                "distance_error_mm": round(err_dist, 3),
            })

    report = {
        "mode": "split_halves",
        "origin_x": round(k.origin_x, 3),
        "origin_y": round(k.origin_y, 3),
        "lower_half": {
            "origin": {"x": round(l_bl_x, 2), "y": round(l_bl_y, 2)},
            "square_size": split_halves_data["lower_square_size"],
            "affine_matrix": lower_affine,
        },
        "upper_half": {
            "origin": {"x": round(u_bl_x, 2), "y": round(u_bl_y, 2)},
            "square_size": split_halves_data["upper_square_size"],
            "affine_matrix": upper_affine,
        },
        "river_analysis": split_halves_data["river"],
        "global_equivalent_affine": global_affine,
        "rule_and_geometry_checks": rule_checks,
        "validation_evaluations": val_results,
        "dead_zone": dead_zone_arg,
        "dead_zone_slots": dead_zone_slots,
        "limit_violations": limit_violations,
        "grid_coordinates": grid_coords,
    }
    return k, report


def calculate_vision_perspective(
    vision_cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    target_size = tuple(vision_cfg.get("output_size", [1000, 1000]))

    # 支援上半區/下半區相機校正
    u_half = vision_cfg.get("upper_half")
    l_half = vision_cfg.get("lower_half")

    split_vision = None
    if u_half and l_half and "top_left" in u_half and "bottom_right" in u_half:
        # 上半區 4 角
        u_tl = u_half["top_left"]
        u_br = u_half["bottom_right"]
        u_corners = np.array([
            u_tl,
            [u_br[0], u_tl[1]],
            u_br,
            [u_tl[0], u_br[1]],
        ], dtype=np.float32)

        # 下半區 4 角
        l_tl = l_half["top_left"]
        l_br = l_half["bottom_right"]
        l_corners = np.array([
            l_tl,
            [l_br[0], l_tl[1]],
            l_br,
            [l_tl[0], l_br[1]],
        ], dtype=np.float32)

        half_target_size = (target_size[0], int(target_size[1] / 2))
        warp_upper = compute_warp_matrix(u_corners, half_target_size)
        warp_lower = compute_warp_matrix(l_corners, half_target_size)

        split_vision = {
            "upper_corners": u_corners.tolist(),
            "lower_corners": l_corners.tolist(),
            "upper_warp_matrix": warp_upper.tolist(),
            "lower_warp_matrix": warp_lower.tolist(),
        }

    # 全盤整張透視矩陣 (向下相容)
    corners = vision_cfg.get("board_corners")
    if not corners or len(corners) != 4:
        if split_vision:
            # 由雙半區推導全盤 4 外角
            corners = [
                split_vision["upper_corners"][0],  # a9
                split_vision["upper_corners"][1],  # i9
                split_vision["lower_corners"][2],  # i0
                split_vision["lower_corners"][3],  # a0
            ]
        else:
            return None

    src_pts = np.array(normalize_corners(corners), dtype=np.float32)
    warp_matrix = compute_warp_matrix(src_pts, target_size)
    quality = compute_calibration_quality(src_pts, warp_matrix, target_size)

    result = {
        "version": 2,
        "output_size": list(target_size),
        "board_corners": [list(pt) for pt in corners],
        "warp_matrix": warp_matrix.tolist(),
        "quality_metrics": quality,
    }
    if split_vision:
        result["split_halves_vision"] = split_vision
    return result


def sync_to_system_files(
    cfg: Dict[str, Any],
    kinematics: Kinematics,
    vision_calib: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    saved_paths = {}

    # 1. 更新 robot/calibration.json
    robot_calib_path = PROJECT_ROOT / "robot" / "calibration.json"
    robot_calib_path.parent.mkdir(parents=True, exist_ok=True)
    kinematics.save_calibration(path=str(robot_calib_path))
    saved_paths["robot_calibration"] = str(robot_calib_path)

    # 2. 更新 data/vision_calibration.json
    if vision_calib:
        vis_calib_path = PROJECT_ROOT / "data" / "vision_calibration.json"
        vis_calib_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "output_size": vision_calib["output_size"],
            "warp_matrix": vision_calib["warp_matrix"],
            "board_corners": vision_calib["board_corners"],
            "metadata": {
                "source": "split_halves_config" if "split_halves_vision" in vision_calib else "manual_config",
                "quality": vision_calib.get("quality_metrics", {}),
            },
        }
        if "split_halves_vision" in vision_calib:
            payload["split_halves_vision"] = vision_calib["split_halves_vision"]

        with open(vis_calib_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        saved_paths["vision_calibration"] = str(vis_calib_path)

    # 3. 更新 data/setup_settings.json
    setup_settings_path = PROJECT_ROOT / "data" / "setup_settings.json"
    current_settings = {}
    if setup_settings_path.exists():
        try:
            with open(setup_settings_path, "r", encoding="utf-8") as f:
                current_settings = json.load(f)
        except Exception:
            current_settings = {}

    motion_cfg = cfg.get("robot_motion", {})
    limits_cfg = cfg.get("robot_limits", {})
    conn_cfg = cfg.get("system_connection", {})
    vision_cfg = cfg.get("vision_calibration", {})

    merged = current_settings if isinstance(current_settings, dict) else {}

    vision_sec = merged.setdefault("vision", {})
    vision_sec["source"] = vision_cfg.get("source", "opencv")
    vision_sec["camera_index"] = int(vision_cfg.get("camera_index", 0))

    robot_sec = merged.setdefault("robot", {})
    robot_runtime = robot_sec.setdefault("runtime", {})
    robot_runtime["fake_robot"] = bool(conn_cfg.get("fake_robot", False))
    robot_runtime["auto_execute_robot"] = bool(conn_cfg.get("auto_execute_robot", False))

    robot_conn = robot_sec.setdefault("connection", {})
    robot_conn["adapter"] = conn_cfg.get("adapter", "modbus")
    robot_conn["ip"] = conn_cfg.get("robot_ip", "192.168.10.10")
    robot_conn["port"] = int(conn_cfg.get("robot_port", 502))
    robot_conn["pc_ip"] = conn_cfg.get("pc_ip", "192.168.10.50")
    robot_conn["subnet_mask"] = conn_cfg.get("subnet_mask", "255.255.0.0")

    robot_motion = robot_sec.setdefault("motion", {})
    robot_motion["z_safe"] = float(motion_cfg.get("z_safe", 150.0))
    robot_motion["z_grab"] = float(motion_cfg.get("z_grab", 20.0))
    robot_motion["place_z_offset"] = float(motion_cfg.get("place_z_offset", 2.0))
    robot_motion["tool_rx"] = float(motion_cfg.get("tool_rx", 0.0))
    robot_motion["tool_ry"] = float(motion_cfg.get("tool_ry", 0.0))
    robot_motion["tool_rz"] = float(motion_cfg.get("tool_rz", 0.0))
    robot_motion["travel_speed"] = float(motion_cfg.get("travel_speed", 30.0))
    robot_motion["lift_speed"] = float(motion_cfg.get("lift_speed", 30.0))
    robot_motion["approach_speed"] = float(motion_cfg.get("approach_speed", 15.0))
    robot_motion["default_acceleration"] = float(motion_cfg.get("default_acceleration", 60.0))
    robot_motion["timeout_sec"] = float(motion_cfg.get("timeout_sec", 10.0))

    robot_limits = robot_sec.setdefault("limits", {})
    robot_limits["min_x"] = float(limits_cfg.get("min_x", -600.0))
    robot_limits["max_x"] = float(limits_cfg.get("max_x", 600.0))
    robot_limits["min_y"] = float(limits_cfg.get("min_y", 100.0))
    robot_limits["max_y"] = float(limits_cfg.get("max_y", 600.0))
    robot_limits["min_z"] = float(limits_cfg.get("min_z", 0.0))
    robot_limits["max_z"] = float(limits_cfg.get("max_z", 250.0))

    setup_settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(setup_settings_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    saved_paths["setup_settings"] = str(setup_settings_path)

    return saved_paths


def print_cli_summary(
    board_report: Dict[str, Any],
    vision_report: Optional[Dict[str, Any]],
    saved_paths: Dict[str, str],
    dry_run: bool,
):
    print("\n" + "=" * 75)
    print("   S.M.A.R.T. 象棋機械手臂 - 雙半區與楚河漢界設定計算報告 (v2.0)")
    print("=" * 75)

    print("\n[1] 棋盤雙半區獨立仿射計算結果 (Split Halves Kinematics):")
    low = board_report["lower_half"]
    up = board_report["upper_half"]
    print(f"  ● 下半區（紅方半盤 Ranks 0~4）：")
    print(f"      基準原點 (a0) : ({low['origin']['x']:.2f}, {low['origin']['y']:.2f}) mm")
    print(f"      棋格尺寸     : 橫向 dx = {low['square_size']['dx']:.2f} mm, 縱向 dy = {low['square_size']['dy']:.2f} mm")
    print(f"  ● 上半區（黑方半盤 Ranks 5~9）：")
    print(f"      基準原點 (a5) : ({up['origin']['x']:.2f}, {up['origin']['y']:.2f}) mm")
    print(f"      棋格尺寸     : 橫向 dx = {up['square_size']['dx']:.2f} mm, 縱向 dy = {up['square_size']['dy']:.2f} mm")

    print("\n[2] 楚河漢界 (River) 幾何規格分析:")
    riv = board_report["river_analysis"]
    print(f"  - 左側河界寬度 (a4 到 a5) : {riv['width_left_mm']:.2f} mm")
    print(f"  - 右側河界寬度 (i4 到 i5) : {riv['width_right_mm']:.2f} mm")
    print(f"  - 平均河界寬度           : {riv['average_width_mm']:.2f} mm")
    print(f"  - 河界 / 標準格高倍率     : {riv['width_ratio_to_grid']:.3f} 倍 ({'標準 1 倍格距' if abs(riv['width_ratio_to_grid']-1.0)<0.05 else '實體河界加寬'})")
    print(f"  - 河界平行度偏差 (左右差) : {riv['parallel_diff_mm']:.2f} mm")
    print(f"  - 上下半盤水平對齊偏差   : {riv['horizontal_shift_mm']:.2f} mm")

    print("\n[3] 中國象棋規則幾何約束驗證 (Rules & Geometry Verification):")
    for chk in board_report.get("rule_and_geometry_checks", []):
        tag = "[PASS]" if chk["passed"] else "[WARN]"
        err_info = f" (誤差: {chk['error_mm']:.2f}mm)" if "error_mm" in chk else ""
        print(f"  {tag} {chk['rule']}{err_info}")

    print("\n[4] 獨立驗證點殘差 (Validation Points Residuals):")
    val_points = board_report.get("validation_evaluations", [])
    if val_points:
        for vp in val_points:
            sq = vp["square"].upper()
            meas = vp["measured"]
            pred = vp["predicted"]
            dist_err = vp["distance_error_mm"]
            status = "PASS (<3mm)" if dist_err <= 3.0 else "WARNING"
            print(f"  - 格點 {sq} ({vp['description']}):")
            print(f"      實測: ({meas['x']:.1f}, {meas['y']:.1f}) -> 預測: ({pred['x']:.1f}, {pred['y']:.1f}) | 歐氏誤差: {dist_err:.2f} mm [{status}]")
    else:
        print("  - (未設定 validation_points)")

    print("\n[5] 死棋盒棄子區 (Dead Zone):")
    dz = board_report["dead_zone"]
    print(f"  - 棄子起點 : ({dz['x']:.1f}, {dz['y']:.1f}, {dz['z']:.1f}) mm，共 {dz['slot_count']} 格，間距 {dz['slot_spacing']} mm")
    for s in board_report["dead_zone_slots"]:
        print(f"      Slot {s['slot']}: ({s['x']:.1f}, {s['y']:.1f}) mm")

    print("\n[6] 關鍵棋格座標取樣 (90 點部分展示):")
    key_squares = ["a0", "i0", "e1", "a4", "i4", "a5", "i5", "e8", "a9", "i9"]
    grid = board_report["grid_coordinates"]
    for sq in key_squares:
        if sq in grid:
            print(f"  - 格點 {sq.upper():<3} : X = {grid[sq]['x']:7.2f} mm,  Y = {grid[sq]['y']:7.2f} mm")

    if board_report["limit_violations"]:
        print("\n[!] 安全軟體邊界檢查警告 (Safety Limit Violations):")
        for v in board_report["limit_violations"]:
            print(f"    [!] {v}")
    else:
        print("\n[V] 安全工作區檢查：所有 90 個棋格與死棋盒位置皆在手臂安全工作區內！")

    if vision_report:
        print("\n[7] 相機視覺透視校正 (Vision Perspective):")
        print(f"  - 輸出尺寸 : {vision_report['output_size']}")
        qm = vision_report.get("quality_metrics", {})
        print(f"  - 棋盤包圍面積 : {qm.get('area_px', 0):.0f} px^2 ({qm.get('area_ratio', 0)*100:.1f}%)")
        print(f"  - 邊長比 (長/寬): {qm.get('edge_ratio', 1.0):.2f}")
        if "split_halves_vision" in vision_report:
            print("  - [OK] 已成功生成上下半區獨立視覺透視矩陣，徹底消除相機視角下的河界拉伸變形。")

    print("\n" + "-" * 75)
    if dry_run:
        print("※ 模式：--dry-run（模擬計算完成，未改寫系統設定檔）")
    else:
        print("※ 系統設定檔更新狀態：")
        for name, p in saved_paths.items():
            print(f"  - [OK] 已同步更新 {name:<20}: {p}")
    print("=" * 75 + "\n")


def main():
    parser = argparse.ArgumentParser(description="S.M.A.R.T. 象棋機械手臂設定計算與同步工具 (v2.0)")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config/system_parameters.json",
        help="輸入參數檔路徑 (預設: config/system_parameters.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅進行驗證與計算，不寫入覆蓋系統檔案",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="reports/calibration_calculation_report.json",
        help="輸出詳細計算報告 JSON 路徑 (預設: reports/calibration_calculation_report.json)",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = PROJECT_ROOT / cfg_path

    try:
        cfg = load_config(cfg_path)
    except Exception as exc:
        print(f"[ERROR] 讀取設定檔失敗: {exc}")
        sys.exit(1)

    board_cfg = cfg.get("board_calibration", {})
    limits_cfg = cfg.get("robot_limits", {})
    vision_cfg = cfg.get("vision_calibration", {})

    # 1. 棋盤座標計算（優先使用雙半區 split_halves 模式）
    try:
        if "upper_half" in board_cfg and "lower_half" in board_cfg:
            kinematics, board_report = calculate_split_halves_kinematics(board_cfg, limits_cfg)
        else:
            # 向下相容傳統 fit_points
            from scripts.calculate_system_calibration import calculate_board_kinematics as calc_legacy
            kinematics, board_report = calc_legacy(board_cfg, limits_cfg)
    except Exception as exc:
        print(f"[ERROR] 棋盤座標計算失敗: {exc}")
        sys.exit(1)

    # 2. 相機透視變換計算
    vision_report = None
    if vision_cfg:
        try:
            vision_report = calculate_vision_perspective(vision_cfg)
        except Exception as exc:
            print(f"[WARNING] 視覺透視矩陣計算失敗: {exc}")

    # 3. 寫入系統檔案
    saved_paths = {}
    if not args.dry_run:
        saved_paths = sync_to_system_files(cfg, kinematics, vision_report)

    # 4. 產出報告
    report_data = {
        "calculated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_config_file": str(cfg_path),
        "board_kinematics": board_report,
        "vision_perspective": vision_report,
        "robot_motion": cfg.get("robot_motion", {}),
        "robot_limits": cfg.get("robot_limits", {}),
        "saved_files": saved_paths,
    }
    report_path = PROJECT_ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    # 4.1 產出 90 格易讀座標文字對照表（清楚標示楚河漢界）
    coords_txt_path = PROJECT_ROOT / "reports" / "calculated_board_coordinates.txt"
    files = "abcdefghi"
    ranks = "9876543210"
    lines = [
        "=" * 85,
        "S.M.A.R.T. 象棋機械手臂 - 90 棋格機械手臂座標對照表 (單位: mm, 雙半區獨立計算版)",
        f"計算時間: {report_data['calculated_at']}",
        "=" * 85,
        f"楚河漢界寬度: {board_report['river_analysis']['average_width_mm']:.2f} mm "
        f"(標準格高倍率: {board_report['river_analysis']['width_ratio_to_grid']:.3f}x)",
        "-" * 85,
    ]
    grid = board_report["grid_coordinates"]
    for r in ranks:
        row_str = f"Rank {r}: "
        for f in files:
            sq = f"{f}{r}"
            c = grid.get(sq, {"x": 0.0, "y": 0.0})
            row_str += f"{sq}:({c['x']:6.1f},{c['y']:6.1f}) "
        lines.append(row_str)
        if r == "5":
            lines.append("        " + "~" * 68 + " [楚河漢界]")
    lines.append("-" * 85)
    lines.append("死棋盒棄子區槽位 (Dead Zone):")
    for s in board_report["dead_zone_slots"]:
        lines.append(f"  Slot {s['slot']}: X = {s['x']:6.1f} mm, Y = {s['y']:6.1f} mm")
    lines.append("=" * 85)
    coords_txt_path.write_text("\n".join(lines), encoding="utf-8")

    # 5. CLI 終端總結輸出
    print_cli_summary(board_report, vision_report, saved_paths, args.dry_run)


if __name__ == "__main__":
    main()
