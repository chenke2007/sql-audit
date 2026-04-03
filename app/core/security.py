"""
安全模块 - 密码加密/解密

使用 Fernet 对称加密存储数据库密码
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# 从环境变量获取密钥，如果没有则生成一个（仅开发环境）
def get_fernet_key() -> bytes:
    """获取或生成 Fernet 密钥"""
    key = os.environ.get("FERNET_KEY")
    if key:
        return key.encode()

    # 开发环境：使用固定密钥（基于项目路径生成）
    import hashlib
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"sql_audit_salt_2024",  # 固定 salt，生产环境应使用环境变量
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(project_path.encode()))
    return key


# 全局 Fernet 实例
_fernet = None


def get_fernet() -> Fernet:
    """获取 Fernet 实例（懒加载）"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_fernet_key())
    return _fernet


def encrypt_password(password: str) -> str:
    """
    加密密码

    Args:
        password: 明文密码

    Returns:
        加密后的密文字符串
    """
    if not password:
        return ""
    f = get_fernet()
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted_password: str) -> str:
    """
    解密密码

    Args:
        encrypted_password: 加密后的密文

    Returns:
        明文密码
    """
    if not encrypted_password:
        return ""
    f = get_fernet()
    return f.decrypt(encrypted_password.encode()).decode()


def generate_fernet_key() -> str:
    """
    生成新的 Fernet 密钥

    用于初始化环境变量，运行: python -c "from app.core.security import generate_fernet_key; print(generate_fernet_key())"
    """
    return Fernet.generate_key().decode()
