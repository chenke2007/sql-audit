/**
 * SQL Audit System - Vue 3 Application
 */

const { createApp, ref, computed, onMounted, watch } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const app = createApp({
    setup() {
        // State
        const activeMenu = ref('analyze');
        const oracleConnected = ref(false);
        const analyzeMode = ref('text');

        // Analysis inputs
        const sqlText = ref('');
        const sqlId = ref('');
        const useLLM = ref(true);
        const useRules = ref(true);

        // Loading states
        const analyzing = ref(false);
        const collecting = ref(false);
        const loadingRules = ref(false);

        // Data
        const analysisResult = ref(null);
        const collectedSQLs = ref([]);
        const rules = ref([]);

        // Computed
        const oracleStatus = computed(() => {
            return {
                type: oracleConnected.value ? 'success' : 'danger',
                text: oracleConnected.value ? 'Oracle 已连接' : 'Oracle 未连接'
            };
        });

        // Methods
        const handleMenuSelect = (index) => {
            activeMenu.value = index;
            if (index === 'rules') {
                loadRules();
            }
        };

        // Health check
        const checkHealth = async () => {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                oracleConnected.value = data.oracle_connection;
            } catch (error) {
                console.error('Health check failed:', error);
                oracleConnected.value = false;
            }
        };

        // Analyze SQL
        const analyzeSQL = async () => {
            if (!sqlText.value.trim()) {
                ElMessage.warning('请输入 SQL 语句');
                return;
            }

            analyzing.value = true;
            analysisResult.value = null;

            try {
                const response = await fetch('/api/analyze/single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sql_text: sqlText.value,
                        use_llm: useLLM.value,
                        use_rules: useRules.value,
                        include_plan: oracleConnected.value
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '分析失败');
                }

                const result = await response.json();
                analysisResult.value = result;

                ElMessage.success('分析完成');

                // Highlight SQL
                setTimeout(() => {
                    document.querySelectorAll('pre code').forEach((block) => {
                        if (window.hljs) {
                            hljs.highlightElement(block);
                        }
                    });
                }, 100);

            } catch (error) {
                console.error('Analysis error:', error);
                ElMessage.error(error.message || '分析失败，请检查网络连接');
            } finally {
                analyzing.value = false;
            }
        };

        // Analyze by SQL_ID
        const analyzeBySqlId = async () => {
            if (!sqlId.value.trim()) {
                ElMessage.warning('请输入 SQL_ID');
                return;
            }

            analyzing.value = true;
            analysisResult.value = null;

            try {
                const response = await fetch(`/api/analyze/by-sql-id?sql_id=${encodeURIComponent(sqlId.value)}&use_llm=${useLLM.value}`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '分析失败');
                }

                const result = await response.json();
                analysisResult.value = result;

                ElMessage.success('分析完成');

            } catch (error) {
                console.error('Analysis error:', error);
                ElMessage.error(error.message || '分析失败');
            } finally {
                analyzing.value = false;
            }
        };

        // Collect slow SQLs
        const collectSlowSQLs = async () => {
            if (!oracleConnected.value) {
                ElMessage.warning('Oracle 未连接，无法采集');
                return;
            }

            collecting.value = true;

            try {
                const response = await fetch('/api/collect/slow-sqls', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        top_n: 20,
                        cpu_threshold_ms: 1000
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || '采集失败');
                }

                const result = await response.json();
                collectedSQLs.value = result;

                ElMessage.success(`采集到 ${result.length} 条慢 SQL`);

            } catch (error) {
                console.error('Collection error:', error);
                ElMessage.error(error.message || '采集失败');
            } finally {
                collecting.value = false;
            }
        };

        // Analyze collected SQL
        const analyzeCollectedSQL = (row) => {
            sqlText.value = row.sql_text;
            activeMenu.value = 'analyze';
            analyzeMode.value = 'text';
            analyzeSQL();
        };

        // Show SQL detail
        const showSQLDetail = (row) => {
            ElMessageBox.alert(
                `<pre style="max-height: 400px; overflow: auto;"><code class="language-sql">${escapeHtml(row.sql_text)}</code></pre>`,
                'SQL 详情',
                {
                    dangerouslyUseHTMLString: true,
                    confirmButtonText: '关闭',
                    customClass: 'sql-detail-dialog'
                }
            );
        };

        // Load rules
        const loadRules = async () => {
            loadingRules.value = true;

            try {
                const response = await fetch('/api/analyze/rules');
                const data = await response.json();
                rules.value = data.rules.map(r => ({ ...r, toggling: false }));
            } catch (error) {
                console.error('Load rules error:', error);
                ElMessage.error('加载规则失败');
            } finally {
                loadingRules.value = false;
            }
        };

        // Toggle rule
        const toggleRule = async (ruleId, enabled) => {
            const rule = rules.value.find(r => r.rule_id === ruleId);
            if (rule) rule.toggling = true;

            try {
                const response = await fetch(`/api/analyze/rules/${ruleId}/toggle?enabled=${enabled}`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    throw new Error('切换失败');
                }

                ElMessage.success(enabled ? '规则已启用' : '规则已禁用');

            } catch (error) {
                console.error('Toggle rule error:', error);
                ElMessage.error('切换规则失败');
                // Revert
                if (rule) rule.enabled = !enabled;
            } finally {
                if (rule) rule.toggling = false;
            }
        };

        // Handle upload success
        const handleUploadSuccess = (response) => {
            if (Array.isArray(response) && response.length > 0) {
                sqlText.value = response[0].sql_text;
                analyzeMode.value = 'text';
                ElMessage.success('文件上传成功，请点击分析');
            }
        };

        // Handle upload error
        const handleUploadError = (error) => {
            console.error('Upload error:', error);
            ElMessage.error('文件上传失败');
        };

        // Utility functions
        const getRiskType = (level) => {
            const map = {
                'CRITICAL': 'danger',
                'HIGH': 'warning',
                'MEDIUM': '',
                'LOW': 'success',
                '严重': 'danger',
                '高': 'warning',
                '中': '',
                '低': 'success'
            };
            return map[level] || 'info';
        };

        const getSeverityType = (severity) => {
            const map = {
                'critical': 'danger',
                'high': 'warning',
                'medium': 'info',
                'low': 'success',
                'info': ''
            };
            return map[severity] || 'info';
        };

        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        // Watch for menu changes
        watch(activeMenu, (newVal) => {
            if (newVal === 'collection' && collectedSQLs.value.length === 0 && oracleConnected.value) {
                collectSlowSQLs();
            }
        });

        // On mount
        onMounted(() => {
            checkHealth();
            // Check health every 30 seconds
            setInterval(checkHealth, 30000);
        });

        return {
            // State
            activeMenu,
            oracleConnected,
            analyzeMode,
            sqlText,
            sqlId,
            useLLM,
            useRules,
            analyzing,
            collecting,
            loadingRules,
            analysisResult,
            collectedSQLs,
            rules,

            // Computed
            oracleStatus,

            // Methods
            handleMenuSelect,
            analyzeSQL,
            analyzeBySqlId,
            collectSlowSQLs,
            analyzeCollectedSQL,
            showSQLDetail,
            loadRules,
            toggleRule,
            handleUploadSuccess,
            handleUploadError,
            getRiskType,
            getSeverityType
        };
    }
});

// Register Element Plus Icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

// Use Element Plus
app.use(ElementPlus);

// Mount
app.mount('#app');
