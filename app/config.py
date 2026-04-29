"""
SQL Audit System - Configuration Management

支持环境变量和配置文件两种方式配置。
优先使用环境变量，方便 Docker 部署。
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OracleConfig(BaseSettings):
    """Oracle数据库配置"""

    model_config = SettingsConfigDict(
        env_prefix="ORACLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    host: str = Field(default="localhost", description="Oracle主机地址")
    port: int = Field(default=1521, description="Oracle端口")
    service_name: str = Field(default="ORCL", description="Oracle服务名")
    username: str = Field(default="system", description="Oracle用户名")
    password: str = Field(default="", description="Oracle密码")

    # 连接池配置
    min_connections: int = Field(default=2, description="连接池最小连接数")
    max_connections: int = Field(default=10, description="连接池最大连接数")

    # 慢SQL阈值配置
    slow_sql_cpu_threshold_ms: int = Field(
        default=1000,
        description="慢SQL CPU时间阈值（毫秒）"
    )
    slow_sql_elapsed_threshold_ms: int = Field(
        default=1000,
        description="慢SQL执行时间阈值（毫秒）"
    )
    slow_sql_buffer_gets_threshold: int = Field(
        default=10000,
        description="慢SQL逻辑读阈值"
    )

    @property
    def connection_string(self) -> str:
        """生成Oracle连接字符串"""
        return f"{self.username}/{self.password}@{self.host}:{self.port}/{self.service_name}"


class LLMConfig(BaseSettings):
    """本地大模型配置"""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    base_url: str = Field(
        default="http://localhost:8000/v1",
        description="本地模型API地址"
    )
    model_name: str = Field(
        default="qwen3.5",
        description="模型名称"
    )
    api_key: str = Field(
        default="dummy-key",
        description="API密钥（本地模型通常不需要）"
    )

    # 调用参数
    timeout_seconds: int = Field(default=120, description="API调用超时时间")
    max_retries: int = Field(default=3, description="最大重试次数")
    temperature: float = Field(default=0.1, description="温度参数，越低越确定")
    max_tokens: int = Field(default=4096, description="最大返回token数")


class AppConfig(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 应用设置
    name: str = Field(default="sql-audit", description="应用名称")
    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")

    # 采集配置
    collector_interval_minutes: int = Field(
        default=5,
        description="自动采集间隔（分钟）"
    )
    collector_top_n: int = Field(
        default=20,
        description="每次采集Top N慢SQL"
    )

    # 分析配置
    max_sql_length_for_analysis: int = Field(
        default=50000,
        description="最大分析SQL长度（字符）"
    )
    max_execution_plan_depth: int = Field(
        default=50,
        description="最大执行计划深度"
    )


class Settings(BaseSettings):
    """全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    oracle: OracleConfig = Field(default_factory=OracleConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    app: AppConfig = Field(default_factory=AppConfig)


# 全局配置实例
settings = Settings()
