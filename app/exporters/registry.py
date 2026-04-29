"""
导出器注册表

策略模式分发器，管理所有导出器实例。
"""

from typing import Dict, List, Optional, Any

from app.exporters.base import BaseExporter, ExportResult


class ExporterRegistry:
    """导出器注册表 - 策略模式分发器"""

    def __init__(self):
        self._exporters: Dict[str, BaseExporter] = {}

    def register(self, exporter: BaseExporter) -> None:
        """注册一个导出器实例"""
        self._exporters[exporter.format_name] = exporter

    def get(self, format_name: str) -> Optional[BaseExporter]:
        """获取指定格式的导出器"""
        return self._exporters.get(format_name)

    def list_formats(self) -> List[Dict[str, str]]:
        """列出所有可用的导出格式"""
        return [
            {
                "name": exp.format_name,
                "display_name": exp.display_name,
                "extension": exp.filename_extension,
                "available": exp.is_available()
            }
            for exp in self._exporters.values()
        ]

    def export(self, format_name: str, analysis_result: Dict[str, Any]) -> ExportResult:
        """统一导出入口"""
        exporter = self.get(format_name)
        if not exporter:
            available = [f["name"] for f in self.list_formats()]
            raise ValueError(f"不支持的导出格式: {format_name}。可用格式: {available}")
        if not exporter.is_available():
            raise RuntimeError(f"导出格式 {format_name} 当前不可用（缺少依赖）")
        return exporter.export(analysis_result)


# 全局注册表实例
registry = ExporterRegistry()
