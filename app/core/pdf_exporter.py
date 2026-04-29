"""
PDF 导出模块（已弃用）

此模块已弃用，请使用 app.exporters.pdf_exporter 中的 PDFExporter。
保留此处仅用于向后兼容，将在后续版本中移除。
"""

import warnings

warnings.warn(
    "app.core.pdf_exporter 已弃用，请使用 app.exporters.pdf_exporter。",
    DeprecationWarning,
    stacklevel=2
)

# 向后兼容：重新导出新的 PDFExporter 和全局实例
from app.exporters import PDFExporter  # noqa: E402,F401
from app.exporters import pdf_exporter  # noqa: E402,F401
