"""
Oracle Instant Client 初始化模块

负责检测平台、定位 instantclient 目录并启用 thick 模式。
"""

import logging
import os
import platform
import sys

import oracledb

logger = logging.getLogger(__name__)

# 全局状态：thick 模式是否已初始化
_thick_initialized = False


def _get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def get_lib_dir() -> str | None:
    """
    根据当前平台返回对应的 instantclient 库目录路径。

    Returns:
        库目录绝对路径，若不支持当前平台则返回 None
    """
    project_root = _get_project_root()
    sys_name = sys.platform
    machine = platform.machine().lower()

    if sys_name == "darwin":
        if machine in ("arm64", "aarch64"):
            lib_dir = os.path.join(project_root, "oracle_instantclient", "macos_arm64")
        else:
            lib_dir = os.path.join(project_root, "oracle_instantclient", "macos_x64")
    elif sys_name.startswith("linux"):
        lib_dir = os.path.join(project_root, "oracle_instantclient", "linux_x64")
    else:
        logger.warning(f"不支持的平台: {sys_name} {machine}")
        return None

    if os.path.exists(lib_dir):
        return lib_dir
    return None


def init_thick_mode() -> bool:
    """
    初始化 Oracle thick 模式。

    根据当前平台自动选择 instantclient 目录，调用一次
    ``oracledb.init_oracle_client()``。已初始化则跳过。

    Returns:
        thick 模式是否成功启用
    """
    global _thick_initialized

    if _thick_initialized:
        return True

    lib_dir = get_lib_dir()
    if not lib_dir:
        logger.info("未找到 Oracle Instant Client 目录，保持 thin 模式")
        return False

    try:
        oracledb.init_oracle_client(lib_dir=lib_dir)
        _thick_initialized = True
        logger.info(f"Oracle thick 模式已启用: {lib_dir}")
        return True
    except oracledb.Error as e:
        logger.warning(f"初始化 thick 模式失败: {e}")
        return False
    except Exception as e:
        logger.warning(f"初始化 thick 模式异常: {e}")
        return False


def is_thick_mode_available() -> bool:
    """检查 thick 模式是否已可用"""
    return _thick_initialized


def ensure_thick_mode() -> bool:
    """
    确保 thick 模式已初始化（若未初始化则尝试）。

    Returns:
        thick 模式是否可用
    """
    if _thick_initialized:
        return True
    return init_thick_mode()
