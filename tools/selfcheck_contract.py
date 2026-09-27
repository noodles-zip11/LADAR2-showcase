import ast
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CAN_RECV4_PATH = REPO_ROOT / "can_recv4.py"
CAN_PARSER_PATH = REPO_ROOT / "can_parser.py"
CAN_C_PATH = REPO_ROOT / "Core" / "Src" / "can.c"
CMAKE_PRESETS_PATH = REPO_ROOT / "CMakePresets.json"
TOOLS_DIR = REPO_ROOT / "tools"
SELFCHECK_ALL_PATH = TOOLS_DIR / "selfcheck_all.ps1"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
REQUIRED_RUNTIME_PACKAGES = {
    "python-can",
    "gs-usb",
    "libusb-package",
    "pyusb",
    "pyside6",
    "pyqtgraph",
    "paho-mqtt",
    "numpy",
    "matplotlib",
}
EXPECTED_FIELDS = [
    "host_rx_time_us",
    "t_sample_us",
    "angle_tick",
    "angle_deg",
    "distance_cm",
    "x_mm",
    "y_mm",
    "quality",
    "status",
]
FORBIDDEN_TOKENS = [
    "open_bus(",
    "QApplication",
    "PointCloudWindow",
    "can.interface",
    "socketcan",
    "os.system",
    "subprocess.Popen",
]
IMPORT_CAN_RECV4_REQUIRED = {
    "selfcheck_protocol.py",
    "selfcheck_csv_roundtrip.py",
    "selfcheck_geometry.py",
    "selfcheck_fixtures.py",
}


def fail(message):
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_equal(actual, expected, context):
    if actual != expected:
        fail(f"{context}: expected {expected!r}, got {actual!r}")


def load_assignment_constants(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"FRAME_HEADER_ID", "FRAME_TAIL_ID", "FORMAL_CSV_FIELDS"}:
                constants[name] = ast.literal_eval(node.value)
    return constants


def strip_c_comments(source):
    without_block = re.sub(r"/\*[\s\S]*?\*/", "", source)
    return re.sub(r"//.*", "", without_block)


def extract_c_function_body(source, function_name):
    signature = re.search(rf"\b{re.escape(function_name)}\b\s*\([^)]*\)\s*\{{", source)
    if signature is None:
        fail(f"Core/Src/can.c is missing function {function_name}")
    body_start = signature.end() - 1
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[body_start + 1:index]
    fail(f"Core/Src/can.c function {function_name} has unbalanced braces")


def find_required_pattern(pattern, text, message, start=0):
    match = re.search(pattern, text[start:])
    if match is None:
        fail(message)
    return start + match.start(), start + match.end()


def require_last_assignment(text, index, pattern, label):
    assignment_pattern = re.compile(rf"aData\s*\[\s*{index}\s*\]\s*=.*?;", re.DOTALL)
    matches = list(assignment_pattern.finditer(text))
    if not matches:
        fail(f"{label}: missing aData[{index}] assignment")
    last_assignment = matches[-1].group(0)
    if re.fullmatch(pattern, last_assignment) is None:
        fail(f"{label}: final aData[{index}] assignment is {last_assignment.strip()!r}")


def require_patterns(text, checks, context):
    for label, pattern in checks:
        if re.search(pattern, text) is None:
            fail(f"{context} is missing {label}")


def has_controlled_can_recv4_import(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        ):
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and first_arg.value == "can_recv4":
            return True
    return False


def check_can_recv4_contract():
    constants = load_assignment_constants(CAN_RECV4_PATH)
    parser_constants = load_assignment_constants(CAN_PARSER_PATH)
    constants.update(parser_constants)
    assert_equal(constants.get("FRAME_HEADER_ID"), 0x123, "FRAME_HEADER_ID contract")
    assert_equal(constants.get("FRAME_TAIL_ID"), 0x124, "FRAME_TAIL_ID contract")
    assert_equal(constants.get("FORMAL_CSV_FIELDS"), EXPECTED_FIELDS, "FORMAL_CSV_FIELDS contract")


def check_firmware_contract():
    source = strip_c_comments(CAN_C_PATH.read_text(encoding="utf-8"))
    body = extract_c_function_body(source, "LIDAR_SendCAN")

    require_patterns(
        body,
        [
            ("float angle = point->angle_deg", r"float\s+angle\s*=\s*point\s*->\s*angle_deg\s*;"),
            (
                "memcpy(&ang_bits, &angle, sizeof(ang_bits))",
                r"memcpy\s*\(\s*&\s*ang_bits\s*,\s*&\s*angle\s*,\s*sizeof\s*\(\s*ang_bits\s*\)\s*\)\s*;",
            ),
        ],
        "Core/Src/can.c LIDAR_SendCAN angle provenance",
    )

    first_stdid_start, first_stdid_end = find_required_pattern(
        r"pHeader\s*->\s*StdId\s*=\s*0x123\s*;",
        body,
        "Core/Src/can.c LIDAR_SendCAN is missing pHeader->StdId = 0x123",
    )
    second_stdid_start, second_stdid_end = find_required_pattern(
        r"pHeader\s*->\s*StdId\s*=\s*0x124\s*;",
        body,
        "Core/Src/can.c LIDAR_SendCAN is missing pHeader->StdId = 0x124",
        start=first_stdid_end,
    )
    if second_stdid_start <= first_stdid_start:
        fail("Core/Src/can.c LIDAR_SendCAN does not assign 0x123 before 0x124")

    first_send_start, first_send_end = find_required_pattern(
        r"HAL_CAN_AddTxMessage\s*\(",
        body,
        "Core/Src/can.c LIDAR_SendCAN is missing first HAL_CAN_AddTxMessage call",
        start=first_stdid_end,
    )
    second_send_start, _ = find_required_pattern(
        r"HAL_CAN_AddTxMessage\s*\(",
        body,
        "Core/Src/can.c LIDAR_SendCAN is missing second HAL_CAN_AddTxMessage call",
        start=second_stdid_end,
    )
    if not (first_stdid_start < first_send_start < second_stdid_start < second_send_start):
        fail("Core/Src/can.c LIDAR_SendCAN frame order is not 0x123/send then 0x124/send")

    first_frame_setup = body[:first_send_start]
    second_frame_setup = body[first_send_end:second_send_start]
    dlc_pattern = re.compile(r"pHeader\s*->\s*DLC\s*=\s*(\d+)\s*;")
    first_dlc_matches = list(dlc_pattern.finditer(first_frame_setup))
    second_dlc_matches = list(dlc_pattern.finditer(second_frame_setup))
    if not first_dlc_matches or first_dlc_matches[-1].group(1) != "8":
        fail("Core/Src/can.c LIDAR_SendCAN first frame does not set pHeader->DLC = 8 before send")
    if not second_dlc_matches or second_dlc_matches[-1].group(1) != "8":
        fail("Core/Src/can.c LIDAR_SendCAN second frame does not set pHeader->DLC = 8 before send")

    first_frame_assignments = [
        (0, r"aData\s*\[\s*0\s*\]\s*=\s*seq\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (1, r"aData\s*\[\s*1\s*\]\s*=\s*\(\s*point\s*->\s*distance_cm\s*>>\s*8\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (2, r"aData\s*\[\s*2\s*\]\s*=\s*point\s*->\s*distance_cm\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (3, r"aData\s*\[\s*3\s*\]\s*=\s*\(\s*ang_bits\s*>>\s*24\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (4, r"aData\s*\[\s*4\s*\]\s*=\s*\(\s*ang_bits\s*>>\s*16\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (5, r"aData\s*\[\s*5\s*\]\s*=\s*\(\s*ang_bits\s*>>\s*8\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (6, r"aData\s*\[\s*6\s*\]\s*=\s*ang_bits\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
        (7, r"aData\s*\[\s*7\s*\]\s*=\s*point\s*->\s*quality\s*;", "Core/Src/can.c LIDAR_SendCAN first frame"),
    ]
    second_frame_assignments = [
        (0, r"aData\s*\[\s*0\s*\]\s*=\s*seq\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (1, r"aData\s*\[\s*1\s*\]\s*=\s*\(\s*point\s*->\s*t_sample_us\s*>>\s*24\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (2, r"aData\s*\[\s*2\s*\]\s*=\s*\(\s*point\s*->\s*t_sample_us\s*>>\s*16\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (3, r"aData\s*\[\s*3\s*\]\s*=\s*\(\s*point\s*->\s*t_sample_us\s*>>\s*8\s*\)\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (4, r"aData\s*\[\s*4\s*\]\s*=\s*point\s*->\s*t_sample_us\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (5, r"aData\s*\[\s*5\s*\]\s*=\s*\(\s*point\s*->\s*angle_tick\s*\)\s*>>\s*8\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (6, r"aData\s*\[\s*6\s*\]\s*=\s*point\s*->\s*angle_tick\s*&\s*0xFF\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
        (7, r"aData\s*\[\s*7\s*\]\s*=\s*point\s*->\s*status\s*;", "Core/Src/can.c LIDAR_SendCAN second frame"),
    ]
    for index, pattern, label in first_frame_assignments:
        require_last_assignment(first_frame_setup, index, pattern, label)
    for index, pattern, label in second_frame_assignments:
        require_last_assignment(second_frame_setup, index, pattern, label)


def check_cmake_presets():
    data = json.loads(CMAKE_PRESETS_PATH.read_text(encoding="utf-8"))
    build_presets = data.get("buildPresets", [])
    if not any(preset.get("name") == "Debug" for preset in build_presets):
        fail("CMakePresets.json is missing Debug build preset")


def check_selfcheck_all_inventory():
    """确认每个 selfcheck_*.py 都纳入总入口，避免新增脚本被漏跑。"""
    source = SELFCHECK_ALL_PATH.read_text(encoding="utf-8")
    actual = {path.name for path in TOOLS_DIR.glob("selfcheck_*.py")}
    configured = set(re.findall(r"""['"]tools/(selfcheck_[^'"]+\.py)['"]""", source))

    missing = sorted(actual - configured)
    extra = sorted(configured - actual)
    if missing:
        fail(f"selfcheck_all.ps1 does not run these scripts: {missing}")
    if extra:
        fail(f"selfcheck_all.ps1 references missing selfcheck scripts: {extra}")


def normalize_requirement_name(line):
    # 只做静态依赖清单检查，不安装包；下划线和连字符按 Python 包名惯例归一化。
    name = line.split("#", 1)[0].strip()
    if not name:
        return None
    name = re.split(r"[<>=!~\[]", name, maxsplit=1)[0].strip()
    return name.lower().replace("_", "-") or None


def check_requirements_contract():
    declared = {
        name
        for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        for name in [normalize_requirement_name(line)]
        if name
    }
    missing = sorted(REQUIRED_RUNTIME_PACKAGES - declared)
    if missing:
        fail(f"requirements.txt is missing runtime packages: {missing}")


def check_harness_side_effect_guards():
    target_files = sorted(TOOLS_DIR.glob("selfcheck_*.py"))
    for path in target_files:
        name = path.name
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
        stripped_source = "\n".join(lines)
        if name != "selfcheck_contract.py":
            for token in FORBIDDEN_TOKENS:
                if token in stripped_source:
                    fail(f"forbidden token {token!r} found in {name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "can_recv4":
                        fail(f"{name} uses forbidden direct import can_recv4")
            elif isinstance(node, ast.ImportFrom) and node.module == "can_recv4":
                fail(f"{name} uses forbidden from can_recv4 import form")
        if name in IMPORT_CAN_RECV4_REQUIRED and not has_controlled_can_recv4_import(tree):
            fail(f"{name} does not use controlled can_recv4 import")


def main():
    check_can_recv4_contract()
    check_firmware_contract()
    check_cmake_presets()
    check_selfcheck_all_inventory()
    check_requirements_contract()
    check_harness_side_effect_guards()
    print("PASS: selfcheck_contract")


if __name__ == "__main__":
    main()
