"""
连接测试脚本
验证 Oracle 和 LLM API 连接
"""

import asyncio
import os
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from app.config import settings


def test_oracle_connection():
    """测试 Oracle 连接"""
    print("=" * 60)
    print("测试 Oracle 连接")
    print("=" * 60)
    print(f"主机: {settings.oracle.host}")
    print(f"端口: {settings.oracle.port}")
    print(f"服务名: {settings.oracle.service_name}")
    print(f"用户名: {settings.oracle.username}")
    print()

    try:
        from app.oracle.client import OracleClient, OracleConnectionError

        client = OracleClient()
        result = client.initialize()

        if result:
            print("✅ Oracle 连接成功!")
            print()

            # 测试简单查询
            print("测试查询...")
            results = client.execute("SELECT * FROM v$version")
            if results:
                print(f"✅ 查询成功! Oracle 版本信息:")
                for row in results[:3]:
                    print(f"   {row}")

            # 测试 v$sql 访问
            print()
            print("测试 v$sql 访问...")
            results = client.execute(
                """
                SELECT COUNT(*) as total_sqls,
                       SUM(CASE WHEN cpu_time > 10000000 THEN 1 ELSE 0 END) as slow_sqls
                FROM v$sql
                WHERE rownum <= 1000
                """
            )
            if results:
                total, slow = results[0]
                print(f"✅ v$sql 访问成功!")
                print(f"   总SQL数: {total}, 慢SQL数: {slow}")

            client.close()
            return True

    except OracleConnectionError as e:
        print(f"❌ Oracle 连接失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_llm_connection():
    """测试 LLM API 连接"""
    print()
    print("=" * 60)
    print("测试 LLM API 连接")
    print("=" * 60)
    print(f"Base URL: {settings.llm.base_url}")
    print(f"模型: {settings.llm.model_name}")
    print(f"API Key: {settings.llm.api_key[:10]}..." if settings.llm.api_key else "无 API Key")
    print()

    try:
        import httpx

        # 测试 API 连接
        headers = {
            "Authorization": f"Bearer {settings.llm.api_key}",
            "Content-Type": "application/json"
        }

        # 尝试获取模型列表
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{settings.llm.base_url}/models",
                    headers=headers
                )
                if response.status_code == 200:
                    print("✅ API 连接成功! 可以获取模型列表")
                else:
                    print(f"⚠️ 获取模型列表返回状态码: {response.status_code}")
                    print(f"   响应: {response.text[:200]}")
            except Exception as e:
                print(f"⚠️ 无法获取模型列表: {e}")

        # 测试实际调用
        print()
        print("测试实际 LLM 调用...")

        payload = {
            "model": settings.llm.model_name,
            "messages": [
                {"role": "system", "content": "你是一个 SQL 优化专家。"},
                {"role": "user", "content": "请分析以下 SQL 的潜在性能问题：SELECT * FROM users WHERE status = 'active'"}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.llm.base_url}/chat/completions",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print("✅ LLM 调用成功!")
                print()
                print("回复预览:")
                print("-" * 40)
                if content:
                    print(content[:300] + "..." if len(content) > 300 else content)
                else:
                    print("(空响应)")
                    print(f"完整响应: {data}")
                print("-" * 40)
                return True
            else:
                print(f"❌ LLM 调用失败，状态码: {response.status_code}")
                print(f"响应: {response.text[:500]}")
                return False

    except Exception as e:
        print(f"❌ LLM 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    print("\n🚀 SQL 审核系统 - 连接测试\n")

    # 测试 Oracle
    oracle_ok = test_oracle_connection()

    # 测试 LLM
    llm_ok = await test_llm_connection()

    # 总结
    print()
    print("=" * 60)
    print("测试结果总结")
    print("=" * 60)
    print(f"Oracle 连接: {'✅ 通过' if oracle_ok else '❌ 失败'}")
    print(f"LLM API 连接: {'✅ 通过' if llm_ok else '❌ 失败'}")
    print()

    if oracle_ok and llm_ok:
        print("🎉 所有连接测试通过! 可以开始开发 Phase 2。")
    elif oracle_ok:
        print("⚠️ Oracle 连接正常，但 LLM API 有问题。可以继续开发，但 AI 分析功能可能受限。")
    elif llm_ok:
        print("⚠️ LLM API 正常，但 Oracle 连接有问题。请检查数据库配置。")
    else:
        print("❌ 连接都失败，请检查配置。")


if __name__ == "__main__":
    asyncio.run(main())
