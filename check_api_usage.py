#!/usr/bin/env python3
"""
API 使用情况查询脚本
支持: Gemini, Qwen, DeepSeek
"""

import asyncio
import aiohttp
import os
from datetime import datetime
import pytz

async def check_gemini_usage(api_keys):
    """查询 Gemini API 使用情况"""
    print("\n🔍 查询 Gemini API 使用情况...")

    results = []
    for i, key in enumerate(api_keys[:3], 1):  # 只检查前3个key
        try:
            # Gemini没有直接的使用情况API，我们通过简单请求测试
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m['name'] for m in data.get('models', []) if 'preview' not in m['name'].lower()]
                        results.append(f"  ✅ Key #{i}: 可用 (支持 {len(models)} 个模型)")
                    elif resp.status == 429:
                        results.append(f"  ⚠️  Key #{i}: 配额用尽 (HTTP 429)")
                    else:
                        text = await resp.text()
                        results.append(f"  ❌ Key #{i}: 错误 (HTTP {resp.status})")
        except Exception as e:
            results.append(f"  ❌ Key #{i}: {str(e)}")

    return "\n".join(results)

async def check_qwen_usage(api_key):
    """查询 Qwen API 使用情况"""
    print("\n🔍 查询 Qwen API 使用情况...")

    try:
        url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "qwen-max",
            "input": {
                "messages": [{"role": "user", "content": "hi"}]
            },
            "parameters": {
                "result_format": "message",
                "max_tokens": 10
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    # 检查响应头中的配额信息
                    remaining = resp.headers.get('X-Qwsl-Remaining', '未知')
                    return f"  ✅ Qwen API: 正常工作\n  📊 剩余配额: {remaining}"
                elif resp.status == 429:
                    return "  ⚠️  Qwen API: 配额用尽 (HTTP 429)"
                else:
                    text = await resp.text()
                    return f"  ❌ Qwen API: 错误 (HTTP {resp.status})"
    except Exception as e:
        return f"  ❌ Qwen API: {str(e)}"

async def check_deepseek_usage(api_key):
    """查询 DeepSeek API 使用情况"""
    print("\n🔍 查询 DeepSeek API 使用情况...")

    try:
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    usage = data.get('usage', {})
                    if usage:
                        return f"  ✅ DeepSeek API: 正常工作\n  📊 本次调用: {usage.get('total_tokens', 0)} tokens"
                    else:
                        return "  ✅ DeepSeek API: 正常工作"
                elif resp.status == 429:
                    return "  ⚠️  DeepSeek API: 配额用尽 (HTTP 429)"
                else:
                    text = await resp.text()
                    return f"  ❌ DeepSeek API: 错误 (HTTP {resp.status})"
    except Exception as e:
        return f"  ❌ DeepSeek API: {str(e)}"

async def check_all_apis():
    """检查所有API使用情况"""

    # 从环境变量读取API Keys
    gemini_keys_str = os.getenv("GEMINI_API_KEY", "")
    gemini_keys = [k.strip() for k in gemini_keys_str.split(',') if k.strip()]

    qwen_key = os.getenv("QWEN_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")

    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

    print("=" * 60)
    print(f"📊 API 使用情况查询")
    print(f"⏰ 查询时间: {now}")
    print("=" * 60)

    results = {}

    # 检查 Gemini
    if gemini_keys:
        results['gemini'] = await check_gemini_usage(gemini_keys)
    else:
        results['gemini'] = "  ❌ 未配置 GEMINI_API_KEY"

    # 检查 Qwen
    if qwen_key:
        results['qwen'] = await check_qwen_usage(qwen_key)
    else:
        results['qwen'] = "  ❌ 未配置 QWEN_API_KEY"

    # 检查 DeepSeek
    if deepseek_key:
        results['deepseek'] = await check_deepseek_usage(deepseek_key)
    else:
        results['deepseek'] = "  ❌ 未配置 DEEPSEEK_API_KEY"

    # 打印结果
    print("\n🤖 Gemini API:")
    print(results['gemini'])

    print("\n🧠 Qwen API:")
    print(results['qwen'])

    print("\n🔮 DeepSeek API:")
    print(results['deepseek'])

    print("\n" + "=" * 60)

    return results

async def format_for_telegram():
    """格式化为Telegram消息"""
    gemini_keys_str = os.getenv("GEMINI_API_KEY", "")
    gemini_keys = [k.strip() for k in gemini_keys_str.split(',') if k.strip()]

    qwen_key = os.getenv("QWEN_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")

    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

    msg = f"📊 **API 使用情况**\n\n"
    msg += f"⏰ 查询时间: {now}\n\n"

    # Gemini
    msg += "🤖 **Gemini API**\n"
    if gemini_keys:
        working_count = 0
        for i, key in enumerate(gemini_keys[:5], 1):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            working_count += 1
                        elif resp.status == 429:
                            pass
            except:
                pass

        if working_count > 0:
            msg += f"✅ 可用: {working_count}/{len(gemini_keys[:5])} Keys\n"
        else:
            msg += f"❌ 所有 Keys 配额用尽\n"
    else:
        msg += "❌ 未配置\n"

    # Qwen
    msg += "\n🧠 **Qwen API**\n"
    if qwen_key:
        msg += "✅ 已配置\n"
    else:
        msg += "❌ 未配置\n"

    # DeepSeek
    msg += "\n🔮 **DeepSeek API**\n"
    if deepseek_key:
        msg += "✅ 已配置\n"
    else:
        msg += "❌ 未配置\n"

    return msg

if __name__ == "__main__":
    asyncio.run(check_all_apis())
