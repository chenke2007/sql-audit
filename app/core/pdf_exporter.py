"""
PDF 导出模块

将 SQL 分析结果导出为 PDF 报告，支持与前端一致的样式。
使用 HTML + weasyprint 实现更精确的样式控制。
"""

import io
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PDFExporter:
    """PDF 导出器 - 使用 HTML 渲染实现与前端一致的样式"""

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """检查依赖是否安装"""
        try:
            import weasyprint
            self.weasyprint = weasyprint
            self.available = True
        except ImportError:
            logger.warning("weasyprint 未安装，PDF 导出功能不可用。请运行: pip install weasyprint")
            self.available = False

    def export_analysis_report(self, analysis_result: Dict[str, Any]) -> bytes:
        """
        导出分析结果报告

        Args:
            analysis_result: 分析结果字典

        Returns:
            PDF 文件字节数据
        """
        if not self.available:
            raise RuntimeError("PDF 导出功能不可用，请安装 weasyprint: pip install weasyprint")

        html_content = self._build_html_report(analysis_result)

        # 使用 weasyprint 生成 PDF
        html = self.weasyprint.HTML(string=html_content)
        pdf_bytes = html.write_pdf()

        return pdf_bytes

    def _build_html_report(self, result: Dict[str, Any]) -> str:
        """构建 HTML 报告"""
        sql_text = result.get('sql_text', '')
        sql_type = result.get('sql_type', 'N/A')
        sql_id = result.get('sql_id', 'N/A')
        tables = result.get('tables', [])
        violations = result.get('rule_violations', [])
        llm_analysis = result.get('llm_analysis', {})
        recommendations = result.get('recommendations', [])

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>SQL Audit Report</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #1f2937;
            margin: 0;
            padding: 0;
        }}

        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1a56db;
        }}

        .header h1 {{
            color: #1a56db;
            font-size: 24px;
            margin: 0 0 10px 0;
        }}

        .header .meta {{
            color: #6b7280;
            font-size: 12px;
        }}

        .section {{
            margin-bottom: 24px;
        }}

        .section-title {{
            color: #1a56db;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid #e5e7eb;
        }}

        .subsection-title {{
            color: #374151;
            font-size: 14px;
            font-weight: 600;
            margin: 16px 0 8px 0;
        }}

        /* 基本信息表格 */
        .info-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .info-table th {{
            background: #1a56db;
            color: white;
            text-align: left;
            padding: 10px 12px;
            font-weight: 600;
        }}

        .info-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e5e7eb;
        }}

        .info-table tr:nth-child(even) {{
            background: #f9fafb;
        }}

        .info-table td:first-child {{
            font-weight: 600;
            width: 120px;
            background: #f3f4f6;
        }}

        /* SQL 代码块 */
        .sql-code {{
            background: #111827;
            color: #f3f4f6;
            padding: 16px;
            border-radius: 8px;
            font-family: "Menlo", "Monaco", "Courier New", monospace;
            font-size: 12px;
            line-height: 1.5;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            word-break: break-all;
        }}

        /* 规则违规卡片 */
        .violation-card {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
        }}

        .violation-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }}

        .severity-badge {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .severity-critical {{ background: #fee2e2; color: #991b1b; }}
        .severity-high {{ background: #ffedd5; color: #9a3412; }}
        .severity-medium {{ background: #fef3c7; color: #92400e; }}
        .severity-low {{ background: #d1fae5; color: #065f46; }}

        .rule-name {{
            font-weight: 600;
            color: #111827;
        }}

        .violation-message {{
            color: #4b5563;
            margin-bottom: 4px;
        }}

        .violation-suggestion {{
            color: #2563eb;
            font-size: 13px;
        }}

        /* AI 分析部分 */
        .ai-summary {{
            background: #dbeafe;
            border: 1px solid #93c5fd;
            border-radius: 8px;
            padding: 12px;
            color: #1e40af;
        }}

        .issue-item {{
            border-left: 4px solid #e5e7eb;
            padding-left: 12px;
            margin-bottom: 12px;
        }}

        .issue-item.high {{ border-left-color: #ef4444; background: #fef2f2; padding: 8px 8px 8px 12px; border-radius: 0 4px 4px 0; }}
        .issue-item.medium {{ border-left-color: #f59e0b; background: #fffbeb; padding: 8px 8px 8px 12px; border-radius: 0 4px 4px 0; }}
        .issue-item.low {{ border-left-color: #3b82f6; background: #eff6ff; padding: 8px 8px 8px 12px; border-radius: 0 4px 4px 0; }}

        .issue-severity {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            margin-right: 8px;
            text-transform: uppercase;
        }}

        .issue-severity.high {{ background: #fecaca; color: #991b1b; }}
        .issue-severity.medium {{ background: #fde68a; color: #92400e; }}
        .issue-severity.low {{ background: #bfdbfe; color: #1e40af; }}

        /* 索引建议卡片 - 与前端一致的绿色主题 */
        .index-card {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}

        .index-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .index-table {{
            font-weight: 600;
            color: #166534;
            font-size: 14px;
        }}

        .index-columns {{
            color: #15803d;
            font-size: 13px;
            margin-bottom: 8px;
        }}

        .index-sql {{
            background: #111827;
            color: #f3f4f6;
            padding: 12px;
            border-radius: 6px;
            font-family: "Menlo", "Monaco", "Courier New", monospace;
            font-size: 11px;
            overflow-x: auto;
            margin: 8px 0;
            white-space: pre-wrap;
            word-wrap: break-word;
            word-break: break-all;
        }}

        .index-reason {{
            color: #166534;
            font-size: 13px;
        }}

        .index-reason strong {{
            color: #15803d;
        }}

        .estimate-benefit {{
            font-size: 11px;
            background: #dcfce7;
            color: #166534;
            padding: 2px 8px;
            border-radius: 4px;
        }}

        /* 重写建议 */
        .rewrite-sql {{
            background: #111827;
            color: #f3f4f6;
            padding: 12px;
            border-radius: 6px;
            font-family: "Menlo", "Monaco", "Courier New", monospace;
            font-size: 11px;
            overflow-x: auto;
            margin: 8px 0;
            white-space: pre-wrap;
            word-wrap: break-word;
            word-break: break-all;
        }}

        /* 优化建议列表 */
        .suggestion-list {{
            padding-left: 20px;
        }}

        .suggestion-list li {{
            margin-bottom: 8px;
            color: #4b5563;
        }}

        /* 综合建议 */
        .recommendation-item {{
            border-left: 4px solid #1a56db;
            padding-left: 12px;
            margin-bottom: 16px;
        }}

        .recommendation-title {{
            font-weight: 600;
            color: #111827;
            margin-bottom: 4px;
        }}

        .recommendation-desc {{
            color: #4b5563;
            font-size: 13px;
        }}

        .recommendation-impact {{
            color: #6b7280;
            font-size: 12px;
            font-style: italic;
            margin-top: 4px;
        }}

        /* 空状态 */
        .empty-state {{
            color: #9ca3af;
            font-style: italic;
            padding: 12px;
            text-align: center;
        }}

        /* 分页 */
        .page-break {{
            page-break-before: always;
        }}

        /* 复制按钮提示 */
        .copy-hint {{
            font-size: 11px;
            color: #6b7280;
            font-style: italic;
            margin-top: 4px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>SQL 审核报告</h1>
        <div class="meta">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
'''

        # 1. 基本信息
        html += f'''
    <div class="section">
        <div class="section-title">1. 基本信息</div>
        <table class="info-table">
            <tr>
                <th>字段</th>
                <th>值</th>
            </tr>
            <tr>
                <td>SQL ID</td>
                <td>{sql_id or 'N/A'}</td>
            </tr>
            <tr>
                <td>SQL 类型</td>
                <td>{sql_type}</td>
            </tr>
            <tr>
                <td>涉及表</td>
                <td>{', '.join(tables) if tables else 'N/A'}</td>
            </tr>
            <tr>
                <td>规则违规数</td>
                <td>{len(violations)}</td>
            </tr>
        </table>
    </div>
'''

        # 2. SQL 语句
        if sql_text:
            html += f'''
    <div class="section">
        <div class="section-title">2. SQL 语句</div>
        <pre class="sql-code">{self._escape_html(sql_text)}</pre>
    </div>
'''

        # 3. 规则检查结果
        if violations:
            html += '''
    <div class="section">
        <div class="section-title">3. 规则检查结果</div>
'''
            for v in violations:
                severity = v.get('severity', 'low')
                rule_id = v.get('rule_id', '')
                rule_name = v.get('rule_name', '')
                message = v.get('message', '')
                suggestion = v.get('suggestion', '')

                html += f'''
        <div class="violation-card">
            <div class="violation-header">
                <span class="severity-badge severity-{severity}">{severity.upper()}</span>
                <span class="rule-name">{rule_id}: {rule_name}</span>
            </div>
            <div class="violation-message">{message}</div>
            <div class="violation-suggestion">{suggestion}</div>
        </div>
'''
            html += '    </div>\n'

        # 4. AI 智能分析
        if llm_analysis:
            html += '''
    <div class="section">
        <div class="section-title">4. AI 智能分析</div>
'''

            # 总体评价
            summary = llm_analysis.get('summary', '')
            if summary:
                html += f'''
        <div class="subsection-title">总体评价</div>
        <div class="ai-summary">{summary}</div>
'''

            # 发现的问题
            issues = llm_analysis.get('issues', [])
            if issues:
                html += '''
        <div class="subsection-title">发现的问题</div>
'''
                for issue in issues:
                    severity = issue.get('severity', 'medium')
                    desc = issue.get('description', '')
                    impact = issue.get('impact', '')

                    html += f'''
        <div class="issue-item {severity}">
            <span class="issue-severity {severity}">{severity}</span>
            <strong>{desc}</strong>
            {f'<div style="color:#6b7280;margin-top:4px;">影响: {impact}</div>' if impact else ''}
        </div>
'''

            # 索引建议
            index_suggestions = llm_analysis.get('index_suggestions', [])
            if index_suggestions:
                html += '''
        <div class="subsection-title">索引建议</div>
'''
                for idx in index_suggestions:
                    table = idx.get('table', '')
                    columns = idx.get('columns', [])
                    sql = idx.get('sql', '')
                    reason = idx.get('reason', '')
                    benefit = idx.get('estimate_benefit', '')

                    html += f'''
        <div class="index-card">
            <div class="index-header">
                <span class="index-table">{table} 表</span>
                {f'<span class="estimate-benefit">{benefit}</span>' if benefit else ''}
            </div>
            <div class="index-columns">列: {', '.join(columns)}</div>
'''
                    if sql:
                        html += f'''            <pre class="index-sql">{self._escape_html(sql)}</pre>
'''
                    if reason:
                        html += f'''            <div class="index-reason"><strong>原因:</strong> {reason}</div>
'''
                    html += '''        </div>
'''

            # 重写建议
            rewrite_suggestions = llm_analysis.get('rewrite_suggestions', [])
            if rewrite_suggestions:
                html += '''
        <div class="subsection-title">重写建议</div>
'''
                for i, rewrite_sql in enumerate(rewrite_suggestions, 1):
                    html += f'''
        <div style="margin-bottom:12px;">
            <div style="color:#6b7280;font-size:12px;margin-bottom:4px;">选项 {i}:</div>
            <pre class="rewrite-sql">{self._escape_html(rewrite_sql)}</pre>
        </div>
'''

            # 其他优化建议
            optimization_suggestions = llm_analysis.get('optimization_suggestions', [])
            if optimization_suggestions:
                html += '''
        <div class="subsection-title">其他优化建议</div>
        <ol class="suggestion-list">
'''
                for s in optimization_suggestions:
                    html += f'''            <li>{s}</li>
'''
                html += '''        </ol>
'''

            html += '    </div>\n'

        # 5. 综合建议
        if recommendations:
            html += '''
    <div class="section page-break">
        <div class="section-title">5. 综合建议</div>
'''
            for rec in recommendations:
                title = rec.get('title', '')
                desc = rec.get('description', '')
                impact = rec.get('impact', '')

                html += f'''
        <div class="recommendation-item">
            <div class="recommendation-title">{title}</div>
            <div class="recommendation-desc">{desc}</div>
            {f'<div class="recommendation-impact">影响: {impact}</div>' if impact else ''}
        </div>
'''
            html += '    </div>\n'

        html += '''
</body>
</html>
'''
        return html

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))


# 全局导出器实例
pdf_exporter = PDFExporter()
