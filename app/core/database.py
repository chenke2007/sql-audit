"""
数据库管理模块

管理 SQLite 元数据数据库和动态数据库连接
"""

import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from app.core.security import encrypt_password, decrypt_password


# SQLite 数据库路径
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "sql_audit_metadata.db"
)


def init_metadata_db():
    """初始化元数据数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建数据源表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS db_sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            db_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            service_name TEXT,
            sid TEXT,
            database TEXT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_db_sources_type ON db_sources(db_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_db_sources_host ON db_sources(host)
    """)

    conn.commit()
    conn.close()


@contextmanager
def get_metadata_db():
    """获取元数据数据库连接（上下文管理器）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


class DBSource:
    """数据库源模型"""

    def __init__(
        self,
        id: str,
        name: str,
        db_type: str,
        host: str,
        port: int,
        username: str,
        password: str,
        service_name: Optional[str] = None,
        sid: Optional[str] = None,
        database: Optional[str] = None,
        description: Optional[str] = None,
        is_default: bool = False,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None
    ):
        self.id = id
        self.name = name
        self.db_type = db_type.lower()
        self.host = host
        self.port = port
        self.username = username
        self._password = password  # 加密后的密码
        self.service_name = service_name
        self.sid = sid
        self.database = database
        self.description = description or ""
        self.is_default = is_default
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def password(self) -> str:
        """获取解密后的密码"""
        return decrypt_password(self._password)

    @password.setter
    def password(self, value: str):
        """设置并加密密码"""
        self._password = encrypt_password(value)

    def to_dict(self, include_password: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "name": self.name,
            "db_type": self.db_type,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "service_name": self.service_name,
            "sid": self.sid,
            "database": self.database,
            "description": self.description,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        if include_password:
            result["password"] = self.password
        return result

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DBSource":
        """从数据库行创建实例"""
        return cls(
            id=row["id"],
            name=row["name"],
            db_type=row["db_type"],
            host=row["host"],
            port=row["port"],
            username=row["username"],
            password=row["password"],  # 已加密
            service_name=row["service_name"],
            sid=row["sid"],
            database=row["database"],
            description=row["description"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


class DBSourceManager:
    """数据库源管理器"""

    @staticmethod
    def create(
        name: str,
        db_type: str,
        host: str,
        port: int,
        username: str,
        password: str,
        service_name: Optional[str] = None,
        sid: Optional[str] = None,
        database: Optional[str] = None,
        description: Optional[str] = None
    ) -> DBSource:
        """创建新的数据源"""
        source_id = str(uuid.uuid4())
        encrypted_password = encrypt_password(password)

        # 如果是第一个数据源，设为默认
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM db_sources")
            count = cursor.fetchone()[0]
            is_default = count == 0

            cursor.execute("""
                INSERT INTO db_sources
                (id, name, db_type, host, port, service_name, sid, database,
                 username, password, description, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id, name, db_type.lower(), host, port,
                service_name, sid, database, username, encrypted_password,
                description or "", is_default
            ))
            conn.commit()

        return DBSourceManager.get_by_id(source_id)

    @staticmethod
    def get_by_id(source_id: str) -> Optional[DBSource]:
        """根据 ID 获取数据源"""
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM db_sources WHERE id = ?",
                (source_id,)
            )
            row = cursor.fetchone()
            return DBSource.from_row(row) if row else None

    @staticmethod
    def get_by_name(name: str) -> Optional[DBSource]:
        """根据名称获取数据源"""
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM db_sources WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            return DBSource.from_row(row) if row else None

    @staticmethod
    def get_default() -> Optional[DBSource]:
        """获取默认数据源"""
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM db_sources WHERE is_default = 1 LIMIT 1"
            )
            row = cursor.fetchone()
            return DBSource.from_row(row) if row else None

    @staticmethod
    def list_all(
        db_type: Optional[str] = None,
        host: Optional[str] = None,
        name: Optional[str] = None
    ) -> List[DBSource]:
        """列出数据源，支持筛选"""
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM db_sources WHERE 1=1"
            params = []

            if db_type:
                query += " AND db_type = ?"
                params.append(db_type.lower())
            if host:
                query += " AND host LIKE ?"
                params.append(f"%{host}%")
            if name:
                query += " AND name LIKE ?"
                params.append(f"%{name}%")

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [DBSource.from_row(row) for row in rows]

    @staticmethod
    def update(
        source_id: str,
        name: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        service_name: Optional[str] = None,
        sid: Optional[str] = None,
        database: Optional[str] = None,
        description: Optional[str] = None,
        is_default: Optional[bool] = None
    ) -> Optional[DBSource]:
        """更新数据源"""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if host is not None:
            updates.append("host = ?")
            params.append(host)
        if port is not None:
            updates.append("port = ?")
            params.append(port)
        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if password is not None:
            updates.append("password = ?")
            params.append(encrypt_password(password))
        if service_name is not None:
            updates.append("service_name = ?")
            params.append(service_name)
        if sid is not None:
            updates.append("sid = ?")
            params.append(sid)
        if database is not None:
            updates.append("database = ?")
            params.append(database)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if is_default is not None:
            # 如果设为默认，先清除其他默认
            if is_default:
                with get_metadata_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE db_sources SET is_default = 0 WHERE is_default = 1"
                    )
                    conn.commit()
            updates.append("is_default = ?")
            params.append(is_default)

        if not updates:
            return DBSourceManager.get_by_id(source_id)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(source_id)

        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE db_sources SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        return DBSourceManager.get_by_id(source_id)

    @staticmethod
    def delete(source_id: str) -> bool:
        """删除数据源"""
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM db_sources WHERE id = ?", (source_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

            # 如果删除了默认，把第一个设为默认
            if deleted:
                cursor.execute(
                    "SELECT id FROM db_sources ORDER BY created_at LIMIT 1"
                )
                first = cursor.fetchone()
                if first:
                    cursor.execute(
                        "UPDATE db_sources SET is_default = 1 WHERE id = ?",
                        (first["id"],)
                    )
                    conn.commit()

            return deleted

    @staticmethod
    def test_connection(source: DBSource) -> tuple[bool, str]:
        """测试数据源连接"""
        try:
            if source.db_type == "oracle":
                return DBSourceManager._test_oracle(source)
            elif source.db_type == "mysql":
                return DBSourceManager._test_mysql(source)
            elif source.db_type == "postgresql":
                return DBSourceManager._test_postgresql(source)
            else:
                return False, f"不支持的数据库类型: {source.db_type}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _test_oracle(source: DBSource) -> tuple[bool, str]:
        """测试 Oracle 连接"""
        import oracledb

        try:
            if source.service_name:
                dsn = f"{source.host}:{source.port}/{source.service_name}"
            elif source.sid:
                dsn = f"{source.host}:{source.port}/{source.sid}"
            else:
                return False, "Oracle 连接需要 SID 或 Service Name"

            conn = oracledb.connect(
                user=source.username,
                password=source.password,
                dsn=dsn
            )

            # 获取版本信息
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM v$version WHERE banner LIKE 'Oracle%'")
            version = cursor.fetchone()[0]

            conn.close()
            return True, version
        except oracledb.Error as e:
            error_msg = str(e)
            # DPY-3010: 数据库版本太旧，thin 模式不支持
            if "DPY-3010" in error_msg:
                return False, (
                    "该数据库的 Oracle 版本太旧（低于 12.1），"
                    "当前使用的 python-oracledb thin 模式不支持此版本。"
                )
            return False, error_msg
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _test_mysql(source: DBSource) -> tuple[bool, str]:
        """测试 MySQL 连接（预留）"""
        return False, "MySQL 支持开发中"

    @staticmethod
    def _test_postgresql(source: DBSource) -> tuple[bool, str]:
        """测试 PostgreSQL 连接（预留）"""
        return False, "PostgreSQL 支持开发中"


# 初始化数据库
init_metadata_db()
