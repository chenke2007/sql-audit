"""
PDF 导出模块

将 SQL 分析结果导出为 PDF 报告。
委托 HTML 生成给 HTMLExporter，再使用 weasyprint 转换为 PDF。
"""

import logging
from typing import Dict, Any

from app.exporters.base import BaseExporter, ExportResult
from app.exporters.html_exporter import HTMLExporter

logger = logging.getLogger(__name__)


class PDFExporter(BaseExporter):
    """PDF 导出器 - 委托 HTML 生成给 HTMLExporter，然后使用 weasyprint 转换"""

    @property
    def format_name(self) -> str:
        return "pdf"

    @property
    def display_name(self) -> str:
        return "PDF"

    @property
    def content_type(self) -> str:
        return "application/pdf"

    @property
    def filename_extension(self) -> str:
        return "pdf"

    def __init__(self):
        self._html_exporter = HTMLExporter()
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import weasyprint
            self.weasyprint = weasyprint
            self._available = True
        except ImportError:
            logger.warning("weasyprint 未安装，PDF 导出功能不可用。请运行: pip install weasyprint")
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def export(self, analysis_result: Dict[str, Any]) -> ExportResult:
        if not self._available:
            raise RuntimeError("PDF 导出功能不可用，请安装 weasyprint: pip install weasyprint")

        # 委托 HTML 生成给 HTMLExporter
        html_content = self._html_exporter._build_html_report(analysis_result)

        # 在 HTML 头部注入 PDF 专用的 @page 规则
        html_with_page = self._inject_pdf_styles(html_content)

        # 使用 weasyprint 转换为 PDF
        html = self.weasyprint.HTML(string=html_with_page)
        pdf_bytes = html.write_pdf()

        return ExportResult(
            content=pdf_bytes,
            content_type=self.content_type,
            filename_extension=self.filename_extension
        )

    def _inject_pdf_styles(self, html_content: str) -> str:
        """在 </head> 前注入 PDF 专用的 @page CSS"""
        pdf_styles = '''    <style>
        @page {
            size: A4;
            margin: 2cm;
        }
        .page-break {
            page-break-before: always;
        }
    </style>
'''
        # 将 pdf_styles 插入到 </head> 之前
        return html_content.replace('</head>', pdf_styles + '</head>')
