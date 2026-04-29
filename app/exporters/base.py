"""
导出器基类

定义所有导出器的统一接口和标准化结果容器。
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional


class ExportResult:
    """标准化的导出结果容器"""

    def __init__(
        self,
        content: bytes,
        content_type: str,
        filename_extension: str,
        filename_prefix: str = "sql_audit_report"
    ):
        self.content = content
        self.content_type = content_type
        self.filename_extension = filename_extension
        self.filename_prefix = filename_prefix

    def generate_filename(self, sql_id: Optional[str] = None) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        id_part = sql_id or 'unknown'
        # 清理 sql_id 中的特殊字符
        id_part = "".join(c if c.isalnum() or c in '-_' else '_' for c in str(id_part))
        return f"{self.filename_prefix}_{id_part}_{timestamp}.{self.filename_extension}"


class BaseExporter(ABC):
    """导出器基类 - 所有导出器必须实现此接口"""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """格式标识符，如 'pdf', 'html', 'markdown'"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """人类可读的格式名称，如 'PDF', 'HTML', 'Markdown'"""
        pass

    @property
    @abstractmethod
    def content_type(self) -> str:
        """HTTP Content-Type，如 'application/pdf', 'text/html; charset=utf-8'"""
        pass

    @property
    @abstractmethod
    def filename_extension(self) -> str:
        """文件扩展名，如 'pdf', 'html', 'md'"""
        pass

    @abstractmethod
    def export(self, analysis_result: Dict[str, Any]) -> ExportResult:
        """
        执行导出

        Args:
            analysis_result: 完整的分析结果字典

        Returns:
            ExportResult 包含文件内容、MIME类型、扩展名等信息
        """
        pass

    def is_available(self) -> bool:
        """检查导出器是否可用（依赖是否安装等）"""
        return True
