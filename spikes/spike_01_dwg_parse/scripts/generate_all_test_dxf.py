"""
Spike-1 测试底图生成器 — 航空工业制造领域
运行: python generate_all_test_dxf.py
输出: ../test_data/ 下 4 个 DXF 文件
依赖: pip install ezdxf
"""
import sys
import os
import struct

import ezdxf
from ezdxf.enums import TextEntityAlignment

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "test_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────
#  色号常量
# ──────────────────────────────────────────────────────────────────
WHITE, GRAY, RED, GREEN, BLUE, CYAN, MAGENTA, ORANGE, YELLOW = 7, 8, 1, 3, 5, 4, 6, 30, 2


# ══════════════════════════════════════════════════════════════════
#  Tier-1 : 机翼前缘组件车间  60 m × 30 m, 15 台设备
# ══════════════════════════════════════════════════════════════════
def create_tier1():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    layers = {
        "A-WALL":        WHITE,   "A-COLS":       GRAY,   "A-DOOR":       GREEN,
        "E-CRANE":       MAGENTA,
        "M-EQUIP":       CYAN,    "M-EQUIP-SAFE": RED,    "M-EQUIP-LABEL": WHITE,
        "P-FLOW":        GREEN,
        "S-ZONE-FOD":    ORANGE,  "S-ZONE-CHEM":  RED,    "S-ZONE-CLEAN": BLUE,
        "T-TEXT":        WHITE,   "T-DIM":        YELLOW,
    }
    for n, c in layers.items():
        doc.layers.add(n, color=c)

    W, H = 60.0, 30.0
    GRID = 6.0

    # --- 墙体 ---
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H), (0, 0)],
                        dxfattribs={"layer": "A-WALL", "const_width": 0.3})

    # --- 柱网 ---
    for ix in range(int(W / GRID) + 1):
        for iy in range(int(H / GRID) + 1):
            cx, cy = ix * GRID, iy * GRID
            if 0 < cx < W and 0 < cy < H:
                s = 0.25
                msp.add_lwpolyline(
                    [(cx - s, cy - s), (cx + s, cy - s),
                     (cx + s, cy + s), (cx - s, cy + s), (cx - s, cy - s)],
                    close=True, dxfattribs={"layer": "A-COLS"})

    # --- 门 ---
    for x1, y1, x2, y2, label in [
        (0, 3, 0, 6, "入口"), (W, 12, W, 18, "大件出入口"), (30, 0, 34, 0, "消防门"),
    ]:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "A-DOOR"})
        msp.add_text(label, height=0.4, dxfattribs={"layer": "T-TEXT"}).set_placement(
            ((x1 + x2) / 2, (y1 + y2) / 2 + 0.8), align=TextEntityAlignment.MIDDLE_CENTER)

    # --- 天车 ---
    msp.add_line((3, 12), (57, 12), dxfattribs={"layer": "E-CRANE"})
    msp.add_line((3, 12.6), (57, 12.6), dxfattribs={"layer": "E-CRANE"})
    msp.add_lwpolyline([(3, 6), (57, 6), (57, 18), (3, 18), (3, 6)],
                        dxfattribs={"layer": "E-CRANE"})
    msp.add_text("5T桥式天车", height=0.5, dxfattribs={"layer": "E-CRANE"}).set_placement(
        (30, 17), align=TextEntityAlignment.MIDDLE_CENTER)

    # --- 设备 (x, y, w, h, name, eq_id, safety_zone) ---
    equipment = [
        (4, 20, 4, 3,  "CNC-5轴铣-01",  "EQ-001", 1.0),
        (12, 20, 4, 3, "CNC-5轴铣-02",  "EQ-002", 1.0),
        (20, 20, 4, 3, "CNC-钻铣-03",   "EQ-003", 1.0),
        (4, 2, 3, 2.5,  "去毛刺-W1",     "EQ-004", 0.8),
        (10, 2, 3, 2.5, "清洗站-W2",     "EQ-005", 0.8),
        (16, 2, 5, 3,   "化铣槽",        "EQ-006", 2.0),
        (24, 2, 4, 2.5, "阳极氧化",      "EQ-007", 1.5),
        (31, 2, 3, 2.5, "密封站",        "EQ-008", 1.0),
        (4, 7, 8, 3,    "铆接工位×2",    "EQ-009", 1.5),
        (16, 7, 6, 3,   "胶接固化炉",    "EQ-010", 2.0),
        (38, 20, 8, 6,  "CMM检测间",     "EQ-011", 1.0),
        (50, 20, 6, 4,  "激光跟踪仪",    "EQ-012", 0.5),
        (28, 20, 5, 3,  "真空工装台",    "EQ-013", 1.0),
        (38, 7, 4, 3,   "超声NDT",       "EQ-014", 1.0),
        (46, 7, 5, 3,   "表面粗糙度仪",  "EQ-015", 0.5),
    ]
    for x, y, w, h, name, eq_id, sz in equipment:
        msp.add_lwpolyline(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)],
            close=True, dxfattribs={"layer": "M-EQUIP"})
        msp.add_lwpolyline(
            [(x - sz, y - sz), (x + w + sz, y - sz),
             (x + w + sz, y + h + sz), (x - sz, y + h + sz), (x - sz, y - sz)],
            close=True, dxfattribs={"layer": "M-EQUIP-SAFE"})
        msp.add_text(f"{eq_id}: {name}", height=0.35,
                     dxfattribs={"layer": "M-EQUIP-LABEL"}).set_placement(
            (x + w / 2, y + h / 2), align=TextEntityAlignment.MIDDLE_CENTER)

    # --- 功能分区 ---
    msp.add_lwpolyline([(1, 1), (59, 1), (59, 29), (1, 29), (1, 1)],
                        dxfattribs={"layer": "S-ZONE-FOD"})
    msp.add_text("FOD管控区", height=0.5, dxfattribs={"layer": "S-ZONE-FOD"}).set_placement(
        (55, 28), align=TextEntityAlignment.MIDDLE_CENTER)

    msp.add_lwpolyline([(14, 0.5), (30, 0.5), (30, 6.5), (14, 6.5), (14, 0.5)],
                        dxfattribs={"layer": "S-ZONE-CHEM"})
    msp.add_text("危化品隔离区", height=0.4, dxfattribs={"layer": "S-ZONE-CHEM"}).set_placement(
        (22, 6.2), align=TextEntityAlignment.MIDDLE_CENTER)

    msp.add_lwpolyline([(36, 18.5), (58, 18.5), (58, 28), (36, 28), (36, 18.5)],
                        dxfattribs={"layer": "S-ZONE-CLEAN"})
    msp.add_text("恒温检测区 20±1°C", height=0.4, dxfattribs={"layer": "S-ZONE-CLEAN"}).set_placement(
        (47, 27.5), align=TextEntityAlignment.MIDDLE_CENTER)

    # --- 工艺流线 ---
    flow = [(0, 4.5), (6, 21.5), (14, 21.5), (22, 21.5),
            (5.5, 3.25), (11.5, 3.25), (18.5, 3.5), (26, 3.25),
            (42, 23), (8, 8.5), (32.5, 3.25), (19, 8.5), (60, 15)]
    msp.add_lwpolyline(flow, dxfattribs={"layer": "P-FLOW"})

    fp = os.path.join(OUTPUT_DIR, "tier1_wing_leading_edge_workshop.dxf")
    doc.saveas(fp)
    return fp, len(equipment), len(layers)


# ══════════════════════════════════════════════════════════════════
#  Tier-2 : 机身段对接装配厂  150 m × 80 m, 55 台设备
# ══════════════════════════════════════════════════════════════════
def create_tier2():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    layer_defs = {
        "A-WALL": WHITE, "A-COLS": GRAY, "A-DOOR": GREEN,
        "E-CRANE-20T": MAGENTA, "E-CRANE-10T": MAGENTA,
        "M-EQUIP": CYAN, "M-EQUIP-SAFE": RED, "M-EQUIP-LABEL": WHITE,
        "P-FLOW-MAIN": GREEN, "P-FLOW-AGV": ORANGE,
        "S-ZONE-FOD": ORANGE, "S-ZONE-CHEM": RED, "S-ZONE-CLEAN": BLUE,
        "S-ZONE-NDT": RED, "S-ZONE-FIRE": RED,
        "T-TEXT": WHITE, "T-DIM": YELLOW,
    }
    for n, c in layer_defs.items():
        doc.layers.add(n, color=c)

    W, H = 150.0, 80.0
    GRID = 10.0

    # 墙体
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H), (0, 0)],
                        dxfattribs={"layer": "A-WALL", "const_width": 0.4})
    # 柱网
    for ix in range(int(W / GRID) + 1):
        for iy in range(int(H / GRID) + 1):
            cx, cy = ix * GRID, iy * GRID
            if 0 < cx < W and 0 < cy < H:
                s = 0.35
                msp.add_lwpolyline(
                    [(cx - s, cy - s), (cx + s, cy - s),
                     (cx + s, cy + s), (cx - s, cy + s), (cx - s, cy - s)],
                    close=True, dxfattribs={"layer": "A-COLS"})

    # 大门
    for x1, y1, x2, y2, label in [
        (0, 30, 0, 42, "大件进口-1"), (W, 30, W, 42, "大件进口-2"),
        (60, 0, 68, 0, "人员入口"), (100, 0, 106, 0, "消防出口"),
    ]:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "A-DOOR"})
        msp.add_text(label, height=0.8, dxfattribs={"layer": "T-TEXT"}).set_placement(
            ((x1 + x2) / 2, (y1 + y2) / 2 + 1.5), align=TextEntityAlignment.MIDDLE_CENTER)

    # 天车
    for y_pos, label, layer in [
        (68, "20T天车-A", "E-CRANE-20T"), (38, "10T天车-B", "E-CRANE-10T"),
        (20, "20T天车-C", "E-CRANE-20T"), (55, "10T天车-D", "E-CRANE-10T"),
    ]:
        msp.add_line((3, y_pos), (147, y_pos), dxfattribs={"layer": layer})
        msp.add_line((3, y_pos + 0.8), (147, y_pos + 0.8), dxfattribs={"layer": layer})
        msp.add_text(label, height=0.6, dxfattribs={"layer": layer}).set_placement(
            (75, y_pos + 2), align=TextEntityAlignment.MIDDLE_CENTER)

    # 设备
    equipment = [
        # 壁板铆接区
        (10, 62, 8, 4, "自动钻铆机-01", "EQ-201"),
        (22, 62, 8, 4, "自动钻铆机-02", "EQ-202"),
        (34, 62, 6, 4, "框段铆接机-03", "EQ-203"),
        (44, 62, 6, 3, "手动铆接台-04", "EQ-204"),
        (54, 62, 6, 3, "手动铆接台-05", "EQ-205"),
        (64, 62, 5, 3, "锪窝机-06",    "EQ-206"),
        # 段间对接
        (30, 42, 20, 6, "对接型架(20m×6m)", "EQ-210"),
        (25, 50, 2, 1.5, "激光跟踪仪-L",    "EQ-211"),
        (52, 50, 2, 1.5, "激光跟踪仪-R",    "EQ-212"),
        (35, 50, 3, 1.5, "数字测量系统",     "EQ-213"),
        (55, 42, 5, 4,   "定位卡板台",       "EQ-214"),
        # 处理区
        (10, 26, 5, 4, "密封胶涂敷工位", "EQ-220"),
        (20, 26, 4, 3, "清洗间",         "EQ-221"),
        (30, 26, 6, 4, "NDT-X射线",      "EQ-222"),
        (45, 26, 8, 6, "恒温检测间",     "EQ-223"),
        (58, 26, 4, 3, "超声NDT",        "EQ-224"),
        (65, 26, 5, 3, "渗透检测台",     "EQ-225"),
        # 系统安装区
        (10, 10, 8, 5, "管路预装-A",  "EQ-230"),
        (25, 10, 8, 5, "电缆布线-B",  "EQ-231"),
        (40, 10, 8, 5, "系统集成-C",  "EQ-232"),
        (55, 10, 8, 5, "功能测试-D",  "EQ-233"),
        (68, 10, 6, 4, "液压站",      "EQ-234"),
        (78, 10, 6, 4, "气密测试台",  "EQ-235"),
        (88, 10, 5, 3, "气源站",      "EQ-236"),
        # 辅助
        (80, 62, 4, 3, "工具库",      "EQ-240"),
        (88, 62, 4, 3, "紧固件库",    "EQ-241"),
        (96, 62, 5, 4, "工艺准备间",  "EQ-242"),
        (80, 26, 4, 4, "密封胶配制间","EQ-243"),
        (104, 62, 5, 3, "油品库",     "EQ-244"),
        # 更多填充设备 → 达到 ~55
        (10, 72, 4, 3, "蒙皮滚弯机",  "EQ-250"),
        (18, 72, 4, 3, "拉形机",      "EQ-251"),
        (26, 72, 5, 3, "喷丸机",      "EQ-252"),
        (35, 72, 4, 3, "去毛刺台-1",  "EQ-253"),
        (43, 72, 4, 3, "去毛刺台-2",  "EQ-254"),
        (51, 72, 3, 2, "角磨站",      "EQ-255"),
        (58, 72, 5, 3, "清洗线",      "EQ-256"),
        (67, 72, 4, 3, "干燥炉",      "EQ-257"),
        (100, 10, 6, 4, "总装夹具台", "EQ-258"),
        (110, 10, 5, 3, "调平台",     "EQ-259"),
        (100, 26, 5, 4, "工量具校验间","EQ-260"),
        (110, 26, 5, 3, "环境监测柜",  "EQ-261"),
        (120, 62, 5, 3, "待检暂存区",  "EQ-262"),
        (120, 26, 5, 3, "合格品暂存",  "EQ-263"),
        (120, 10, 5, 4, "电气配电柜",  "EQ-264"),
        (130, 62, 5, 3, "成品包装台",  "EQ-265"),
        (130, 26, 5, 3, "零件清点区",  "EQ-266"),
        (130, 10, 5, 3, "废料回收站",  "EQ-267"),
        (75, 72, 4, 3, "铆钉预设台",  "EQ-268"),
        (83, 72, 5, 3, "胶接固化箱",  "EQ-269"),
        (92, 72, 5, 3, "保温箱",      "EQ-270"),
        (100, 72, 5, 3, "工装存放架", "EQ-271"),
        (110, 72, 6, 4, "AGV充电位",  "EQ-272"),
        (140, 42, 5, 6, "物料电梯",   "EQ-273"),
    ]
    for x, y, w, h, name, eq_id in equipment:
        sz = 1.2
        msp.add_lwpolyline(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)],
            close=True, dxfattribs={"layer": "M-EQUIP"})
        msp.add_lwpolyline(
            [(x - sz, y - sz), (x + w + sz, y - sz),
             (x + w + sz, y + h + sz), (x - sz, y + h + sz), (x - sz, y - sz)],
            close=True, dxfattribs={"layer": "M-EQUIP-SAFE"})
        msp.add_text(f"{eq_id}: {name}", height=0.45,
                     dxfattribs={"layer": "M-EQUIP-LABEL"}).set_placement(
            (x + w / 2, y + h / 2), align=TextEntityAlignment.MIDDLE_CENTER)

    # NDT辐射禁区
    msp.add_circle((33, 28), 15.0, dxfattribs={"layer": "S-ZONE-NDT"})
    msp.add_text("X射线辐射禁区(R=15m)", height=0.6,
                 dxfattribs={"layer": "S-ZONE-NDT"}).set_placement(
        (33, 44), align=TextEntityAlignment.MIDDLE_CENTER)

    # 恒温区
    msp.add_lwpolyline([(43, 24), (55, 24), (55, 34), (43, 34), (43, 24)],
                        dxfattribs={"layer": "S-ZONE-CLEAN"})
    msp.add_text("恒温检测区 20±0.5°C", height=0.5,
                 dxfattribs={"layer": "S-ZONE-CLEAN"}).set_placement(
        (49, 33.5), align=TextEntityAlignment.MIDDLE_CENTER)

    # AGV通道
    msp.add_lwpolyline([(3, 56), (147, 56), (147, 60), (3, 60), (3, 56)],
                        dxfattribs={"layer": "P-FLOW-AGV"})
    msp.add_text("AGV大件转运通道(4m宽, 50t承重)", height=0.5,
                 dxfattribs={"layer": "P-FLOW-AGV"}).set_placement(
        (75, 58), align=TextEntityAlignment.MIDDLE_CENTER)

    # 消防通道
    for fx in [50, 100]:
        msp.add_lwpolyline([(fx, 0), (fx + 4, 0), (fx + 4, H), (fx, H), (fx, 0)],
                            dxfattribs={"layer": "S-ZONE-FIRE"})

    fp = os.path.join(OUTPUT_DIR, "tier2_fuselage_join_facility.dxf")
    doc.saveas(fp)
    return fp, len(equipment), len(layer_defs)


# ══════════════════════════════════════════════════════════════════
#  Tier-3 : 脉动式最终总装线  300 m × 120 m + 附属区
# ══════════════════════════════════════════════════════════════════
PULSE_STATIONS = [
    {"id": "ST-1", "name": "机身大部件对接", "pos": (20, 60), "size": (30, 25),
     "eq": [("对接型架-前机身", (12, 5), (2, 3)), ("对接型架-后机身", (12, 5), (2, 12)),
            ("激光跟踪仪×4", (2, 1), (25, 5)), ("高空作业平台×4", (8, 4), (2, 19)),
            ("临时紧固工具车", (2, 1), (15, 3)), ("测量臂-L", (1, 1), (20, 8)),
            ("测量臂-R", (1, 1), (20, 14)), ("工具柜-1", (2, 1), (27, 20))]},
    {"id": "ST-2", "name": "翼身对接+起落架", "pos": (55, 60), "size": (30, 25),
     "eq": [("翼身对接工装", (25, 6), (2, 5)), ("起落架安装台", (6, 4), (2, 15)),
            ("激光跟踪仪×2", (2, 1), (28, 3)), ("液压预充注台", (3, 2), (12, 19)),
            ("翼根整流罩台", (4, 3), (20, 15)), ("发动机吊挂工装", (5, 3), (18, 19)),
            ("工具柜-2", (2, 1), (27, 22))]},
    {"id": "ST-3", "name": "系统安装(管路+电缆)", "pos": (90, 60), "size": (30, 25),
     "eq": [("管路安装平台×2", (6, 5), (2, 3)), ("管路安装平台×2b", (6, 5), (10, 3)),
            ("线束铺设平台×2", (6, 5), (2, 12)), ("线束铺设平台×2b", (6, 5), (10, 12)),
            ("扭矩工具站×5", (8, 2), (20, 3)), ("扭矩工具站×5b", (8, 2), (20, 7)),
            ("气密测试接口", (4, 2), (20, 15)), ("氮气充注台", (3, 2), (20, 20))]},
    {"id": "ST-4", "name": "航电/内饰安装", "pos": (125, 60), "size": (30, 25),
     "eq": [("航电安装平台×3", (10, 4), (2, 3)), ("内饰安装平台×2", (8, 4), (2, 12)),
            ("功能测试设备×5", (6, 3), (20, 3)), ("座椅安装导轨", (10, 3), (2, 20)),
            ("行李架安装台", (6, 3), (15, 12)), ("舱门铰链安装", (4, 2), (20, 15)),
            ("客舱灯具安装", (4, 2), (20, 20))]},
    {"id": "ST-5", "name": "地面功能测试(GFT)", "pos": (20, 20), "size": (30, 25),
     "eq": [("液压测试台×2", (6, 4), (2, 3)), ("电气测试台×4", (8, 3), (2, 12)),
            ("燃油系统测试台", (5, 4), (15, 3)), ("环控系统测试台", (5, 3), (15, 12)),
            ("飞控系统测试台", (4, 3), (22, 18)), ("APU测试台", (4, 3), (15, 18)),
            ("氧气系统测试", (3, 2), (22, 8))]},
    {"id": "ST-6", "name": "交付前检查/客户接收", "pos": (55, 20), "size": (30, 25),
     "eq": [("外观检查台", (20, 8), (5, 3)), ("文档归档区", (6, 4), (5, 15)),
            ("客户验收区", (8, 5), (18, 15)), ("称重设备", (4, 3), (5, 22)),
            ("交付证书打印", (3, 2), (25, 22))]},
]

AUXILIARY = [
    ("复合材料铺放车间(洁净室)", (10, -50), (30, 20), "S-ZONE-CLEAN"),
    ("喷漆机库(防爆区)", (45, -50), (40, 15), "S-ZONE-CHEM"),
    ("发动机挂装区", (90, -50), (25, 15), None),
    ("航电集成测试间(EMC屏蔽)", (120, -50), (20, 15), "S-ZONE-EMC"),
    ("线缆预制车间", (145, -50), (25, 15), None),
    ("大型CMM检测间(恒温)", (10, -75), (20, 15), "S-ZONE-CLEAN"),
    ("NDT中心(X光+超声)", (35, -75), (25, 15), "S-ZONE-NDT"),
    ("密封胶配制间(危化品)", (65, -75), (15, 10), "S-ZONE-CHEM"),
    ("动力站房(配电+空压+空调)", (85, -75), (40, 15), None),
    ("外场停机坪", (180, -50), (60, 30), None),
    ("燃油储罐区", (250, -75), (20, 15), "S-ZONE-CHEM"),
]


def create_tier3():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    layer_defs = {
        "A-WALL": WHITE, "A-COLS": GRAY, "A-DOOR": GREEN,
        "E-CRANE-30T": MAGENTA, "E-CRANE-10T": MAGENTA,
        "M-EQUIP": CYAN, "M-EQUIP-SAFE": RED, "M-EQUIP-LABEL": WHITE,
        "P-FLOW-PULSE": GREEN, "P-FLOW-AGV": ORANGE,
        "S-ZONE-FOD": ORANGE, "S-ZONE-CHEM": RED, "S-ZONE-CLEAN": BLUE,
        "S-ZONE-NDT": RED, "S-ZONE-EMC": MAGENTA, "S-ZONE-FIRE": RED,
        "T-TEXT": WHITE, "T-DIM": YELLOW, "T-STATION": GREEN,
    }
    for n, c in layer_defs.items():
        doc.layers.add(n, color=c)

    MW, MH = 300.0, 120.0

    # 主厂房
    msp.add_lwpolyline([(0, 0), (MW, 0), (MW, MH), (0, MH), (0, 0)],
                        dxfattribs={"layer": "A-WALL", "const_width": 0.5})

    # 柱网 12m×12m
    for ix in range(int(MW / 12) + 1):
        for iy in range(int(MH / 12) + 1):
            cx, cy = ix * 12, iy * 12
            if 0 < cx < MW and 0 < cy < MH:
                s = 0.4
                msp.add_lwpolyline(
                    [(cx - s, cy - s), (cx + s, cy - s),
                     (cx + s, cy + s), (cx - s, cy + s), (cx - s, cy - s)],
                    close=True, dxfattribs={"layer": "A-COLS"})

    # 天车
    for y_pos, label, layer in [
        (100, "30T天车-A", "E-CRANE-30T"), (95, "30T天车-B", "E-CRANE-30T"),
        (55, "10T天车-C", "E-CRANE-10T"), (50, "10T天车-D", "E-CRANE-10T"),
    ]:
        msp.add_line((5, y_pos), (MW - 5, y_pos), dxfattribs={"layer": layer})
        msp.add_text(label, height=0.8, dxfattribs={"layer": layer}).set_placement(
            (MW / 2, y_pos + 1.5), align=TextEntityAlignment.MIDDLE_CENTER)

    # 脉动站位 + 设备
    eq_count = 0
    for station in PULSE_STATIONS:
        sx, sy = station["pos"]
        sw, sh = station["size"]
        msp.add_lwpolyline(
            [(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh), (sx, sy)],
            dxfattribs={"layer": "T-STATION", "const_width": 0.2})
        msp.add_text(f"{station['id']}: {station['name']}", height=1.0,
                     dxfattribs={"layer": "T-STATION"}).set_placement(
            (sx + sw / 2, sy + sh - 2), align=TextEntityAlignment.MIDDLE_CENTER)
        for name, (ew, eh), (ox, oy) in station["eq"]:
            ex, ey = sx + ox, sy + oy
            eq_count += 1
            msp.add_lwpolyline(
                [(ex, ey), (ex + ew, ey), (ex + ew, ey + eh), (ex, ey + eh), (ex, ey)],
                close=True, dxfattribs={"layer": "M-EQUIP"})
            msp.add_text(name, height=0.4, dxfattribs={"layer": "M-EQUIP-LABEL"}).set_placement(
                (ex + ew / 2, ey + eh / 2), align=TextEntityAlignment.MIDDLE_CENTER)

    # AGV脉动通道
    msp.add_lwpolyline([(5, 56), (MW - 5, 56), (MW - 5, 59), (5, 59), (5, 56)],
                        dxfattribs={"layer": "P-FLOW-AGV", "const_width": 0.15})
    msp.add_text("AGV脉动通道(50t, 激光导航) → 每72h推进35m →", height=0.6,
                 dxfattribs={"layer": "P-FLOW-AGV"}).set_placement(
        (MW / 2, 57.5), align=TextEntityAlignment.MIDDLE_CENTER)

    # 附属厂房
    for name, (ax, ay), (aw, ah), zone_layer in AUXILIARY:
        msp.add_lwpolyline(
            [(ax, ay), (ax + aw, ay), (ax + aw, ay + ah), (ax, ay + ah), (ax, ay)],
            dxfattribs={"layer": "A-WALL", "const_width": 0.3})
        msp.add_text(name, height=0.6, dxfattribs={"layer": "T-TEXT"}).set_placement(
            (ax + aw / 2, ay + ah / 2), align=TextEntityAlignment.MIDDLE_CENTER)
        if zone_layer:
            msp.add_lwpolyline(
                [(ax - 1, ay - 1), (ax + aw + 1, ay - 1),
                 (ax + aw + 1, ay + ah + 1), (ax - 1, ay + ah + 1), (ax - 1, ay - 1)],
                dxfattribs={"layer": zone_layer})

    # 消防通道
    for fx in range(60, int(MW), 60):
        msp.add_lwpolyline([(fx, 0), (fx + 4, 0), (fx + 4, MH), (fx, MH), (fx, 0)],
                            dxfattribs={"layer": "S-ZONE-FIRE"})

    # 大门
    msp.add_line((0, 10), (0, 35), dxfattribs={"layer": "A-DOOR"})
    msp.add_text("大型铰链门 25m×100m", height=0.8, dxfattribs={"layer": "T-TEXT"}).set_placement(
        (-5, 22), align=TextEntityAlignment.MIDDLE_CENTER)

    fp = os.path.join(OUTPUT_DIR, "tier3_pulse_line_fal.dxf")
    doc.saveas(fp)
    return fp, eq_count, len(layer_defs)


# ══════════════════════════════════════════════════════════════════
#  Tier-CORRUPT : 故意损坏的 DXF 文件（S1-TC06）
# ══════════════════════════════════════════════════════════════════
def create_corrupted():
    """先生成一个有效 DXF，然后截断并注入垃圾字节"""
    fp_good = os.path.join(OUTPUT_DIR, "_tmp_good.dxf")
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 100))
    doc.saveas(fp_good)

    with open(fp_good, "rb") as f:
        data = f.read()

    # 截断到前 40%，追加垃圾字节
    corrupted = data[:int(len(data) * 0.4)] + b"\x00\xff" * 200
    fp = os.path.join(OUTPUT_DIR, "corrupted_file.dxf")
    with open(fp, "wb") as f:
        f.write(corrupted)

    os.remove(fp_good)
    return fp


# ══════════════════════════════════════════════════════════════════
#  Tier-REF : 含参考点的 DXF（S1-TC04 坐标对齐测试）
# ══════════════════════════════════════════════════════════════════
def create_reference_points():
    """3 个已知参考点 + 坐标系偏移/旋转"""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    doc.layers.add("REF-POINTS", color=RED)
    doc.layers.add("A-WALL", color=WHITE)

    # 墙体（带偏移的坐标系：原点偏移 1000,2000mm, 旋转 0°）
    msp.add_lwpolyline(
        [(1000, 2000), (61000, 2000), (61000, 32000), (1000, 32000), (1000, 2000)],
        dxfattribs={"layer": "A-WALL", "const_width": 300})

    # 参考点（DXF坐标 vs 真实世界坐标的映射）
    ref_data = [
        {"dwg_x": 1000, "dwg_y": 2000, "real_x": 0, "real_y": 0, "label": "REF-A (原点)"},
        {"dwg_x": 61000, "dwg_y": 2000, "real_x": 60000, "real_y": 0, "label": "REF-B (X=60m)"},
        {"dwg_x": 1000, "dwg_y": 32000, "real_x": 0, "real_y": 30000, "label": "REF-C (Y=30m)"},
    ]
    for r in ref_data:
        msp.add_circle((r["dwg_x"], r["dwg_y"]), 200, dxfattribs={"layer": "REF-POINTS"})
        msp.add_text(r["label"], height=150, dxfattribs={"layer": "REF-POINTS"}).set_placement(
            (r["dwg_x"] + 300, r["dwg_y"] + 300), align=TextEntityAlignment.LEFT)

    fp = os.path.join(OUTPUT_DIR, "reference_points_offset.dxf")
    doc.saveas(fp)

    # 保存参考点映射为 JSON
    import json
    ref_json_path = os.path.join(OUTPUT_DIR, "reference_points_mapping.json")
    with open(ref_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "description": "DXF坐标到真实世界坐标的参考点映射（单位mm）",
            "unit": "mm",
            "points": [{"dwg": [r["dwg_x"], r["dwg_y"]],
                         "real": [r["real_x"], r["real_y"]],
                         "label": r["label"]} for r in ref_data]
        }, f, ensure_ascii=False, indent=2)

    return fp, ref_json_path


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("Spike-1 航空制造 DXF 测试数据生成")
    print("=" * 70)

    fp1, n1, l1 = create_tier1()
    print(f"✅ Tier-1  {fp1}  ({n1} equip, {l1} layers)")

    fp2, n2, l2 = create_tier2()
    print(f"✅ Tier-2  {fp2}  ({n2} equip, {l2} layers)")

    fp3, n3, l3 = create_tier3()
    print(f"✅ Tier-3  {fp3}  ({n3} equip, {l3} layers)")

    fp_corrupt = create_corrupted()
    print(f"✅ Corrupted  {fp_corrupt}")

    fp_ref, fp_ref_json = create_reference_points()
    print(f"✅ RefPoints  {fp_ref}")
    print(f"   mapping    {fp_ref_json}")

    print()
    print("生成文件清单：")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        sz = os.path.getsize(os.path.join(OUTPUT_DIR, f))
        print(f"  {f:50s} {sz:>10,} bytes")
