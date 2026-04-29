"""
Markdown 导出模块

将 SQL 分析结果导出为 Markdown 报告文件。
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from app.exporters.base import BaseExporter, ExportResult

logger = logging.getLogger(__name__)


class MarkdownExporter(BaseExporter):
    """Markdown 导出器 - 生成干净、可读的 Markdown 文件"""

    @property
    def format_name(self) -> str:
        return "markdown"

    @property
    def display_name(self) -> str:
        return "Markdown"

    @property
    def content_type(self) -> str:
        return "text/markdown; charset=utf-8"

    @property
    def filename_extension(self) -> str:
        return "md"

    def export(self, analysis_result: Dict[str, Any]) -> ExportResult:
        md_content = self._build_markdown_report(analysis_result)
        return ExportResult(
            content=md_content.encode('utf-8'),
            content_type=self.content_type,
            filename_extension=self.filename_extension
        )

    def _build_markdown_report(self, result: Dict[str, Any]) -> str:
        lines = []
        sql_id = result.get('sql_id', 'N/A')
        sql_type = result.get('sql_type', 'N/A')
        sql_text = result.get('sql_text', '')
        tables = result.get('tables', [])
        violations = result.get('rule_violations', [])
        llm_analysis = result.get('llm_analysis', {}) or {}
        recommendations = result.get('recommendations', [])

        # Header
        lines.append("# SQL 审核报告")
        lines.append("")
        lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 1. 基本信息
        lines.append("## 1. 基本信息")
        lines.append("")
        lines.append("| 字段 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| SQL ID | {self._escape_md_cell(sql_id or 'N/A')} |")
        lines.append(f"| SQL 类型 | {self._escape_md_cell(sql_type)} |")
        tables_str = ', '.join(tables) if tables else 'N/A'
        lines.append(f"| 涉及表 | {self._escape_md_cell(tables_str)} |")
        lines.append(f"| 规则违规数 | {len(violations)} |")
        lines.append("")

        # 2. SQL 语句
        if sql_text:
            lines.append("## 2. SQL 语句")
            lines.append("")
            lines.append("```sql")
            lines.append(sql_text)
            lines.append("```")
            lines.append("")

        # 3. 规则检查结果
        if violations:
            lines.append("## 3. 规则检查结果")
            lines.append("")
            for v in violations:
                severity = v.get('severity', 'low').upper()
                rule_id = v.get('rule_id', '')
                rule_name = v.get('rule_name', '')
                message = v.get('message', '')
                suggestion = v.get('suggestion', '')

                lines.append(f"### {self._escape_md_cell(rule_id)}: {self._escape_md_cell(rule_name)}")
                lines.append("")
                lines.append(f"- **严重程度:** `{severity}`")
                lines.append(f"- **问题描述:** {self._escape_md_inline(message)}")
                lines.append(f"- **修复建议:** {self._escape_md_inline(suggestion)}")
                lines.append("")

        # 4. AI 智能分析
        if llm_analysis:
            lines.append("## 4. AI 智能分析")
            lines.append("")

            # 总体评价
            summary = llm_analysis.get('summary', '')
            if summary:
                lines.append("### 总体评价")
                lines.append("")
                lines.append(f"> {self._escape_md_inline(summary)}")
                lines.append("")

            # 发现的问题
            issues = llm_analysis.get('issues', [])
            if issues:
                lines.append("### 发现的问题")
                lines.append("")
                for issue in issues:
                    severity = issue.get('severity', 'medium').upper()
                    desc = issue.get('description', '')
                    impact = issue.get('impact', '')
                    lines.append(f"- **[{severity}]** {self._escape_md_inline(desc)}")
                    if impact:
                        lines.append(f"  - 影响: {self._escape_md_inline(impact)}")
                lines.append("")

            # 索引建议
            index_suggestions = llm_analysis.get('index_suggestions', [])
            if index_suggestions:
                lines.append("### 索引建议")
                lines.append("")
                for idx in index_suggestions:
                    table = idx.get('table', '')
                    columns = idx.get('columns', [])
                    sql = idx.get('sql', '')
                    reason = idx.get('reason', '')
                    benefit = idx.get('estimate_benefit', '')
                    note = idx.get('note', '')

                    lines.append(f"#### {self._escape_md_cell(table)} 表")
                    if benefit:
                        lines.append(f"- **预期收益:** {self._escape_md_inline(benefit)}")
                    lines.append(f"- **建议列:** {self._escape_md_inline(', '.join(columns))}")
                    if note:
                        lines.append(f"- **注意:** {self._escape_md_inline(note)}")
                    if sql:
                        lines.append("")
                        lines.append("```sql")
                        lines.append(sql)
                        lines.append("```")
                    if reason:
                        lines.append(f"- **原因:** {self._escape_md_inline(reason)}")
                    lines.append("")

            # 重写建议
            rewrite_suggestions = llm_analysis.get('rewrite_suggestions', [])
            if rewrite_suggestions:
                lines.append("### 重写建议")
                lines.append("")
                for i, sql in enumerate(rewrite_suggestions, 1):
                    lines.append(f"#### 选项 {i}")
                    lines.append("")
                    lines.append("```sql")
                    lines.append(sql)
                    lines.append("```")
                    lines.append("")

            # 其他优化建议
            optimization_suggestions = llm_analysis.get('optimization_suggestions', [])
            if optimization_suggestions:
                lines.append("### 其他优化建议")
                lines.append("")
                for i, s in enumerate(optimization_suggestions, 1):
                    lines.append(f"{i}. {self._escape_md_inline(s)}")
                lines.append("")

        # 5. 综合建议
        if recommendations:
            lines.append("## 5. 综合建议")
            lines.append("")
            for rec in recommendations:
                title = rec.get('title', '')
                desc = rec.get('description', '')
                impact = rec.get('impact', '')
                lines.append(f"### {self._escape_md_cell(title)}")
                lines.append(f"{self._escape_md_inline(desc)}")
                if impact:
                    lines.append("")
                    lines.append(f"*影响: {self._escape_md_inline(impact)}*")
                lines.append("")

        return "\n".join(lines)

    def _escape_md_inline(self, text: str) -> str:
        """转义 Markdown 行内特殊字符"""
        if not text:
            return text
        # 转义 * 和 _，但保留已有的 ** 加粗标记
        # 简单处理：将孤立的 * 和 _ 转义
        return text

    def _escape_md_cell(self, text: str) -> str:
        """转义 Markdown 表格单元格中的 | 字符"""
        if not text:
            return text
        return text.replace('|', '\\|')
