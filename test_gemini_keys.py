import os
import asyncio
import aiohttp

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')  # 从环境变量读取，勿写入真实 Key

async def check_gemini_keys():
    keys = [k.strip() for k in GEMINI_API_KEY.split(',')]
    results = []

    async with aiohttp.ClientSession() as session:
        for i, key in enumerate(keys, 1):
            try:
                url = f'https://generativelanguage.googleapis.com/v1beta/models?key={key}'
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        results.append(f'Key {i}: HTTP {resp.status} - OK')
                    elif resp.status == 429:
                        results.append(f'Key {i}: HTTP {resp.status} - RATE_LIMIT')
                    else:
                        results.append(f'Key {i}: HTTP {resp.status}')
            except Exception as e:
                results.append(f'Key {i}: ERROR - {str(e)[:30]}')

    return results

results = asyncio.run(check_gemini_keys())
for r in results:
    print(r)

working = sum(1 for r in results if 'OK' in r)
print(f'Total: {working}/{len(results)} keys working')
