"""
导出器模块

提供 SQL 分析结果的多种格式导出功能。
"""

from app.exporters.base import BaseExporter, ExportResult
from app.exporters.registry import ExporterRegistry, registry
from app.exporters.html_exporter import HTMLExporter
from app.exporters.pdf_exporter import PDFExporter
from app.exporters.markdown_exporter import MarkdownExporter

# 自动注册所有导出器
pdf_exporter = PDFExporter()
registry.register(pdf_exporter)
registry.register(HTMLExporter())
registry.register(MarkdownExporter())

__all__ = [
    "BaseExporter",
    "ExportResult",
    "ExporterRegistry",
    "registry",
    "HTMLExporter",
    "PDFExporter",
    "MarkdownExporter",
    "pdf_exporter",
]
