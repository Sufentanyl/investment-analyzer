import asyncio
import aiohttp
import random
import os

# 从环境变量或直接设置
GEMINI_API_KEY = '***REMOVED***,***REMOVED***,***REMOVED***,***REMOVED***,***REMOVED***'
GEMINI_MODEL = 'gemini-3-flash-preview'  # 正确的模型名称

async def test_gemini_basic():
    """测试基础Gemini API调用（无Function Calling）"""
    keys = [k.strip() for k in GEMINI_API_KEY.split(',')]
    key = random.choice(keys)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"

    payload = {
        "contents": [{"parts": [{"text": "你好，请简单介绍一下自己。"}]}]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=30) as resp:
            print(f"[Basic Call] HTTP {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                text = data['candidates'][0]['content']['parts'][0]['text']
                print(f"[SUCCESS] {text[:100]}...")
                return True
            elif resp.status == 429:
                print(f"[FAIL] Rate limit exceeded (HTTP 429)")
                return False
            else:
                print(f"[FAIL] Error: {resp.status}")
                return False

async def test_gemini_with_tools():
    """测试带Function Calling的Gemini API调用"""
    keys = [k.strip() for k in GEMINI_API_KEY.split(',')]
    key = random.choice(keys)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"

    tools = [
        {
            "function_declarations": [
                {
                    "name": "google_search",
                    "description": "搜索实时信息（新闻、股价、天气等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询"
                            }
                        },
                        "required": ["query"]
                    }
                }
            ]
        }
    ]

    payload = {
        "contents": [{"parts": [{"text": "今天北京天气怎么样？"}]}],
        "tools": tools
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=30) as resp:
            print(f"[Function Calling] HTTP {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                candidate = data.get('candidates', [{}])[0]
                content_parts = candidate.get('content', {}).get('parts', [])

                # Check for function call
                for part in content_parts:
                    if 'functionCall' in part:
                        function_call = part['functionCall']
                        print(f"[SUCCESS] Model requested tool: {function_call.get('name')}({function_call.get('args')})")
                        return True
                    elif 'text' in part:
                        print(f"[SUCCESS] Model responded directly: {part['text'][:100]}...")
                        return True

                print(f"[WARN] No response")
                return False
            elif resp.status == 429:
                print(f"[FAIL] Rate limit exceeded (HTTP 429)")
                return False
            else:
                error_text = await resp.text()
                print(f"[FAIL] Error: {resp.status}")
                print(f"   Details: {error_text[:200]}")
                return False

async def main():
    print("=" * 50)
    print("Gemini API Diagnostic Test")
    print("=" * 50)

    print("\n[1] Testing basic call (no tools)...")
    basic_ok = await test_gemini_basic()

    print("\n[2] Testing Function Calling (with tools)...")
    tools_ok = await test_gemini_with_tools()

    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"   Basic call: {'PASS' if basic_ok else 'FAIL'}")
    print(f"   Function Calling: {'PASS' if tools_ok else 'FAIL'}")
    print("=" * 50)

if __name__ == '__main__':
    asyncio.run(main())
