#!/usr/bin/env python3
"""手动触发持仓股票走势分析"""
import sys
import asyncio
sys.path.insert(0, '/app/src')

from main import AdvancedInvestmentAnalyzer
from datetime import datetime

async def main():
    print(f"[{datetime.now()}] 开始持仓股票走势分析...")

    analyzer = AdvancedInvestmentAnalyzer()
    my_positions = analyzer.llm_analyzer.config.get('my_positions', [])

    print(f"发现持仓: {my_positions}")

    if not my_positions:
        print("❌ 没有持仓股票")
        return

    # 调用分析（注意：方法在 llm_analyzer 中）
    results = await analyzer.llm_analyzer.analyze_holdings_trend(my_positions)

    print(f"\n✅ 分析完成！共分析 {len(results)} 只股票：\n")

    for r in results:
        print(f"📊 {r['code']} - {r['trend']} (信心度: {r['confidence']:.1%})")
        print(f"   当前价格: {r['current_price']:.2f}元")
        print(f"   5日涨跌: {r['change_5d']:+.2f}%")
        print(f"   支撑位: {r.get('support', 'N/A')} | 压力位: {r.get('resistance', 'N/A')}")
        print(f"   分析: {r['reason']}")
        print()

    print("数据已保存到数据库，Dashboard 应该能显示了！")

if __name__ == '__main__':
    asyncio.run(main())
