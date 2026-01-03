import akshare as ak
import logging
import requests  # 引入 requests 直接抓取
import re

logger = logging.getLogger(__name__)

class FuturesWatcher:
    def __init__(self):
        pass

    def get_iron_ore_data(self):
        report = []
        
        # --- 1. 大连铁矿石 (DCE) - 使用 AkShare ---
        try:
            # symbol="I0" 代表铁矿石主力连续
            df_dce = ak.futures_zh_spot(symbol="I0", market="CF", adjust='0')
            
            if df_dce is not None and not df_dce.empty:
                row = df_dce.iloc[0]
                price = row.get('current_price')
                
                # 尝试获取涨跌幅，如果没有则不显示
                # AkShare 返回的列名可能是 '涨跌幅'
                change_str = ""
                for col in df_dce.columns:
                    if '涨跌' in str(col):
                        change = row[col]
                        icon = "🔴" if float(change) > 0 else "🟢"
                        change_str = f"({change}%) {icon}"
                        break
                
                report.append(f"🔩 **大连铁矿 (主力)**: {price} {change_str}")
            else:
                report.append("⚠️ 大连铁矿: 暂无数据 (可能休市)")

        except Exception as e:
            # 简化报错日志
            logger.warning(f"DCE 获取异常: {str(e)[:50]}")
            report.append(f"⚠️ 大连铁矿: 获取失败")

        # --- 2. 新加坡铁矿石 (SGX) - 【手搓直连版】 ---
        # 绕过 AkShare，直接读取新浪接口，稳如老狗
        try:
            # hf_FEF 是新加坡铁矿石的代码
            url = "http://hq.sinajs.cn/list=hf_FEF"
            # 模拟浏览器 Header，防止被拦截
            headers = {'Referer': 'https://finance.sina.com.cn/'}
            
            resp = requests.get(url, headers=headers, timeout=5)
            
            if resp.status_code == 200:
                # 返回格式: var hq_str_hf_FEF="101.55,..."
                content = resp.text
                if '="' in content:
                    data_str = content.split('="')[1].split('"')[0]
                    data_parts = data_str.split(',')
                    
                    # 新浪外盘数据位定义:
                    # 0: 最新价, 1: ?, 2: ?, ...
                    # 这里的解析需要根据实际返回做对应，通常第0位是现价
                    
                    if len(data_parts) > 0:
                        current_price = float(data_parts[0])
                        # 昨收价通常在第 7 位或者第 8 位，或者我们需要自己算
                        # 简单起见，我们直接拿现价
                        
                        # 为了获取涨跌幅，我们需要上一交易日结算价，或者直接看数据里有没有
                        # 如果找不到现成的涨跌幅，就只显示价格
                        
                        # 尝试计算涨跌 (假设第7位是昨收，这需要验证，不同品种不一样)
                        # 为了稳妥，这里先只显示价格，避免误导
                        # 或者尝试 akshare 的逻辑：
                        # rate = (current - prev) / prev
                        
                        report.append(f"🔩 **新加坡铁矿 (SGX)**: ${current_price}")
                    else:
                        report.append("⚠️ 新加坡铁矿: 数据解析为空")
                else:
                    report.append("⚠️ 新加坡铁矿: 接口返回格式错误")
            else:
                report.append(f"⚠️ 新加坡铁矿: 网络错误 {resp.status_code}")

        except Exception as e:
            logger.warning(f"SGX 直连异常: {e}")
            report.append("⚠️ 新加坡铁矿: 获取失败")
            
        return "\n".join(report)

if __name__ == "__main__":
    fw = FuturesWatcher()
    print(fw.get_iron_ore_data())