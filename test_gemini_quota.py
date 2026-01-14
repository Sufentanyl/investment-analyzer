import asyncio
import aiohttp
import random

GEMINI_API_KEY = '***REMOVED***,***REMOVED***,***REMOVED***,***REMOVED***,***REMOVED***'
GEMINI_MODEL = 'gemini-3-flash-preview'

async def test_single_key(key, index):
    """测试单个key的配额"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"

    payload = {
        "contents": [{"parts": [{"text": "Hello"}]}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return (index, "[OK] Working", 200)
                elif resp.status == 429:
                    error_detail = await resp.text()
                    return (index, f"[FAIL] 429 RATE_LIMIT", resp.status, error_detail[:100])
                else:
                    error_detail = await resp.text()
                    return (index, f"[FAIL] HTTP {resp.status}", resp.status, error_detail[:100])
    except Exception as e:
        return (index, f"[ERROR] {str(e)[:50]}", 0)

async def main():
    print("=" * 70)
    print(f"Testing Gemini Model: {GEMINI_MODEL}")
    print("=" * 70)

    keys = [k.strip() for k in GEMINI_API_KEY.split(',')]

    print(f"\nTotal keys to test: {len(keys)}\n")

    # 测试所有key
    tasks = [test_single_key(key, i+1) for i, key in enumerate(keys)]
    results = await asyncio.gather(*tasks)

    # 显示结果
    print("\n" + "=" * 70)
    print("Test Results:")
    print("=" * 70)

    working = 0
    rate_limited = 0
    failed = 0

    for result in results:
        index = result[0]
        status = result[1]

        print(f"Key {index}: {status}")

        if "OK" in status:
            working += 1
        elif "429" in status:
            rate_limited += 1
        else:
            failed += 1

    print("\n" + "=" * 70)
    print(f"Summary: {working} Working | {rate_limited} Rate Limited | {failed} Failed")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(main())
