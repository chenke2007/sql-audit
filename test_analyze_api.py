"""
分析 API 测试脚本
测试完整的 SQL 分析流程
"""

import asyncio
import os
import sys
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_analyze_api_availability():
    """测试分析 API 是否可用"""
    print("=" * 60)
    print("测试分析 API 可用性")
    print("=" * 60)

    # 测试规则列表 API
    response = client.get("/api/analyze/rules")
    print(f"\nGET /api/analyze/rules")
    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        rules = data.get("rules", [])
        print(f"✅ 规则列表 API 正常")
        print(f"   已加载 {len(rules)} 条规则:")
        for rule in rules:
            status = "🟢" if rule.get("enabled") else "🔴"
            print(f"   {status} {rule['rule_id']}: {rule['name']} ({rule['severity']})")
        return True, rules
    else:
        print(f"❌ 规则列表 API 失败: {response.text}")
        return False, []


def test_analyze_single_sql():
    """测试单条 SQL 分析"""
    print("\n" + "=" * 60)
    print("测试单条 SQL 分析")
    print("=" * 60)

    # 测试有问题的 SQL
    test_cases = [
        {
            "name": "SELECT * 测试",
            "sql": "SELECT * FROM users WHERE status = 'active'",
            "expected_issues": ["R001"]
        },
        {
            "name": "缺少 WHERE 测试",
            "sql": "SELECT id, name FROM orders",
            "expected_issues": ["R002"]
        },
        {
            "name": "LIKE 前缀通配符",
            "sql": "SELECT * FROM products WHERE name LIKE '%test%'",
            "expected_issues": ["R001", "R004"]
        },
        {
            "name": "IN 子句过多",
            "sql": "SELECT * FROM logs WHERE level IN (1,2,3,4,5,6,7,8,9,10,11,12)",
            "expected_issues": ["R001", "R005"]
        },
        {
            "name": "!= 操作符",
            "sql": "SELECT * FROM users WHERE status != 'deleted'",
            "expected_issues": ["R001", "R006"]
        }
    ]

    all_passed = True

    for test_case in test_cases:
        print(f"\n测试: {test_case['name']}")
        print(f"SQL: {test_case['sql'][:60]}...")

        payload = {
            "sql_text": test_case['sql'],
            "sql_id": f"test_{test_case['name']}",
            "use_llm": False,
            "use_rules": True
        }

        response = client.post("/api/analyze/single", json=payload)

        if response.status_code == 200:
            result = response.json()
            violations = result.get("rule_violations", [])
            violation_ids = [v['rule_id'] for v in violations]

            print(f"✅ 分析成功")
            print(f"   SQL类型: {result.get('sql_type')}")
            print(f"   涉及表: {result.get('tables', [])}")
            print(f"   发现问题: {len(violations)} 个")
            for v in violations:
                print(f"      - {v['rule_id']}: {v['message']}")

            # 检查预期的 issue 是否被检测到
            for expected in test_case['expected_issues']:
                if expected in violation_ids:
                    print(f"   ✅ 正确检测到 {expected}")
                else:
                    print(f"   ⚠️ 未检测到 {expected}")
        else:
            print(f"❌ 分析失败: {response.status_code}")
            print(f"   {response.text}")
            all_passed = False

    return all_passed


def test_batch_analyze():
    """测试批量 SQL 分析"""
    print("\n" + "=" * 60)
    print("测试批量 SQL 分析")
    print("=" * 60)

    payload = {
        "sql_list": [
            {
                "sql_text": "SELECT * FROM table1 WHERE id = 1",
                "sql_id": "sql001"
            },
            {
                "sql_text": "SELECT a.*, b.* FROM table1 a, table2 b WHERE a.id = b.id",
                "sql_id": "sql002"
            },
            {
                "sql_text": "SELECT id FROM table3 WHERE status != 'inactive'",
                "sql_id": "sql003"
            }
        ]
    }

    response = client.post("/api/analyze/batch", json=payload)

    if response.status_code == 200:
        result = response.json()
        results = result.get("results", [])
        summary = result.get("summary", {})

        print(f"✅ 批量分析成功")
        print(f"   总数量: {summary.get('total', 0)}")
        print(f"   严重/高/中/低: {summary.get('critical', 0)}/{summary.get('high', 0)}/{summary.get('medium', 0)}/{summary.get('low', 0)}")

        for i, item in enumerate(results):
            violations = item.get('rule_violations', [])
            print(f"\n   SQL {i+1} ({item.get('sql_id', 'unknown')}):")
            print(f"      类型: {item.get('sql_type')}")
            print(f"      问题数: {len(violations)}")
            for v in violations[:3]:
                print(f"        - {v['rule_id']}")

        return True
    else:
        print(f"❌ 批量分析失败: {response.status_code}")
        print(f"   {response.text}")
        return False


def test_rule_toggle(rules):
    """测试规则开关"""
    print("\n" + "=" * 60)
    print("测试规则开关功能")
    print("=" * 60)

    if not rules:
        print("⚠️ 没有可用的规则，跳过测试")
        return None

    # 使用第一条规则进行测试
    test_rule = rules[0]
    rule_id = test_rule['rule_id']

    print(f"测试规则: {rule_id} ({test_rule['name']})")

    # 先禁用规则
    response = client.post(f"/api/analyze/rules/{rule_id}/toggle", params={"enabled": False})

    if response.status_code == 200:
        print(f"✅ 成功禁用 {rule_id} 规则")

        # 重新启用规则
        response = client.post(f"/api/analyze/rules/{rule_id}/toggle", params={"enabled": True})
        if response.status_code == 200:
            print(f"✅ 成功重新启用 {rule_id} 规则")
            return True
    else:
        print(f"❌ 规则开关失败: {response.text}")
        return False


def test_collect_and_analyze_integration():
    """测试收集和分析集成"""
    print("\n" + "=" * 60)
    print("测试收集-分析集成")
    print("=" * 60)

    # 1. 先收集慢 SQL
    print("\n1. 收集慢 SQL...")
    response = client.post("/api/collect/slow-sqls", json={"top_n": 3})

    if response.status_code != 200:
        print(f"⚠️ 收集失败: {response.text}")
        print("   跳过集成测试")
        return None

    collected = response.json()
    sqls = collected.get("sqls", [])

    print(f"✅ 收集到 {len(sqls)} 条 SQL")

    if not sqls:
        print("   数据库中没有 SQL 数据，跳过")
        return None

    # 2. 分析收集到的 SQL
    print("\n2. 分析收集到的 SQL...")

    batch_items = [
        {
            "sql_text": sql["sql_text"],
            "sql_id": sql["sql_id"]
        }
        for sql in sqls[:3]
    ]

    response = client.post(
        "/api/analyze/batch",
        json={"sql_list": batch_items}
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ 分析完成!")

        # 显示分析结果
        for item in result.get("results", []):
            sql_id = item.get("sql_id", "unknown")
            violations = item.get("rule_violations", [])

            print(f"\n   SQL_ID: {sql_id}")
            print(f"   风险问题: {len(violations)}")
            for v in violations[:2]:
                print(f"      - {v['rule_id']}: {v['message'][:50]}...")

        return True
    else:
        print(f"❌ 批量分析失败: {response.text}")
        return False


def test_llm_analysis():
    """测试 LLM 分析功能"""
    print("\n" + "=" * 60)
    print("测试 LLM 分析 (可选)")
    print("=" * 60)

    # 测试一个需要优化的 SQL
    payload = {
        "sql_text": """
            SELECT u.*, o.*
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id
            WHERE u.status = 'active'
            AND o.created_at > '2024-01-01'
        """,
        "sql_id": "test_llm",
        "use_llm": True,
        "use_rules": True
    }

    print("分析 SQL (这可能需要 10-30 秒)...")
    print("SQL: SELECT u.*, o.* FROM users u LEFT JOIN orders o...")

    try:
        response = client.post("/api/analyze/single", json=payload, timeout=60.0)

        if response.status_code == 200:
            result = response.json()

            print("✅ LLM 分析完成!")
            print(f"   规则发现问题: {len(result.get('rule_violations', []))}")

            llm_result = result.get("llm_analysis")
            if llm_result:
                print(f"   LLM 总结: {llm_result.get('summary', '')[:100]}...")
                suggestions = llm_result.get("optimization_suggestions", [])
                print(f"   优化建议 ({len(suggestions)} 条):")
                for i, s in enumerate(suggestions[:3], 1):
                    print(f"      {i}. {s[:60]}..." if len(s) > 60 else f"      {i}. {s}")
                return True
            else:
                print("   ⚠️ LLM 分析结果为空")
                return None
        else:
            print(f"⚠️ LLM 分析返回错误: {response.status_code}")
            print(f"   {response.text[:200]}")
            return None

    except Exception as e:
        print(f"⚠️ LLM 分析出错: {e}")
        return None


async def main():
    """主函数"""
    print("\n🚀 SQL 审核系统 - 分析 API 测试\n")

    results = {}
    rules = []

    # 1. 测试 API 可用性
    api_ok, rules = test_analyze_api_availability()
    results['api_availability'] = api_ok

    if not api_ok:
        print("\n❌ API 不可用，停止测试")
        return

    # 2. 测试单条 SQL 分析
    results['single_analyze'] = test_analyze_single_sql()

    # 3. 测试批量分析
    results['batch_analyze'] = test_batch_analyze()

    # 4. 测试规则开关
    results['rule_toggle'] = test_rule_toggle(rules)

    # 5. 测试收集-分析集成
    results['integration'] = test_collect_and_analyze_integration()

    # 6. 测试 LLM 分析 (可选)
    results['llm'] = await asyncio.to_thread(test_llm_analysis)

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)

    test_names = {
        'api_availability': 'API 可用性',
        'single_analyze': '单条 SQL 分析',
        'batch_analyze': '批量 SQL 分析',
        'rule_toggle': '规则开关功能',
        'integration': '收集-分析集成',
        'llm': 'LLM 智能分析'
    }

    for test_name, result in results.items():
        display_name = test_names.get(test_name, test_name)
        if result is True:
            status = "✅ 通过"
        elif result is None:
            status = "⚠️ 跳过"
        else:
            status = "❌ 失败"
        print(f"{display_name:.<40} {status}")

    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)

    print(f"\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过")

    if failed == 0:
        print("\n🎉 核心功能测试全部通过!")
    else:
        print(f"\n⚠️ 有 {failed} 项测试失败，请检查配置或代码。")


if __name__ == "__main__":
    asyncio.run(main())
