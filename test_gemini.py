"""
测试Gemini API访问是否正常
"""
import os
import sys
import asyncio
import aiohttp
from dotenv import load_dotenv

# 设置UTF-8编码输出(Windows兼容)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 加载环境变量
load_dotenv()

async def test_gemini_api():
    """测试Gemini API连接"""

    # 获取配置
    keys_str = os.getenv("GEMINI_API_KEY", "")
    gemini_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

    if not gemini_keys:
        print("❌ 错误: 未找到GEMINI_API_KEY环境变量")
        return False

    print(f"📋 配置信息:")
    print(f"  - 模型: {gemini_model}")
    print(f"  - API Key数量: {len(gemini_keys)}")
    print(f"  - Key前缀: {gemini_keys[0][:10]}..." if gemini_keys else "")
    print()

    # 测试请求
    test_prompt = "请用一句话介绍你自己"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_keys[0]}"

    print("🚀 发送测试请求...")
    print(f"  - URL: {url[:60]}...")
    print(f"  - Prompt: {test_prompt}")
    print()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"contents": [{"parts": [{"text": test_prompt}]}]},
                timeout=30
            ) as resp:
                print(f"📡 响应状态码: {resp.status}")

                if resp.status == 200:
                    data = await resp.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    print("✅ Gemini API 访问成功!")
                    print()
                    print("📝 响应内容:")
                    print("-" * 50)
                    print(text.strip())
                    print("-" * 50)
                    return True
                elif resp.status == 429:
                    print("❌ 错误: API配额用尽 (HTTP 429)")
                    error_data = await resp.json()
                    print(f"   详情: {error_data}")
                    return False
                elif resp.status == 401 or resp.status == 403:
                    print("❌ 错误: API Key无效或无权限")
                    error_data = await resp.json()
                    print(f"   详情: {error_data}")
                    return False
                else:
                    print(f"❌ 错误: HTTP {resp.status}")
                    error_data = await resp.json()
                    print(f"   详情: {error_data}")
                    return False

    except asyncio.TimeoutError:
        print("❌ 错误: 请求超时")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Gemini API 连接测试")
    print("=" * 60)
    print()

    result = asyncio.run(test_gemini_api())

    print()
    print("=" * 60)
    if result:
        print("✅ 测试完成: Gemini API 工作正常")
    else:
        print("❌ 测试失败: 请检查API Key配置")
    print("=" * 60)
