from __future__ import annotations

from typing import Dict, List, Optional
import json
import os

EVENT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "ah_spread": {
        "label": "A/H 价差收敛（相对价值配对）",
        "fastest_source": "港股盘中/海外风险偏好/美元利率冲击",
        "transmission_path": "H股先波动 → A股次日/随后补定价 → 价差收敛或再扩",
        "hedge_leg": "同公司 A/H 配对（多A空H或多H空A）",
        "failure_conditions": "难借券/停牌/公司行动不同步/资金单边流动导致中枢迁移",
    },
    "overseas_macro": {
        "label": "海外宏观先动 → A股风格切换后动",
        "fastest_source": "FOMC/CPI/非农 + 美债利率/美元指数",
        "transmission_path": "海外定价 → 港股/中概先反映 → A股次日风格重估",
        "hedge_leg": "港股大盘/行业ETF或股指期货的风格对冲",
        "failure_conditions": "国内政策对冲/预期提前交易/开盘跳空一次性消化",
    },
    "commodities": {
        "label": "全球商品夜盘先动 → A股资源链条补定价",
        "fastest_source": "LME/COMEX 夜盘行情 + 海外供应扰动快讯",
        "transmission_path": "海外商品先涨跌 → A股开盘定价资源链条",
        "hedge_leg": "海外商品期货/ETF或港股资源股对冲",
        "failure_conditions": "国内政策干预/库存结构不同步/汇率抵消",
    },
    "regulatory": {
        "label": "海外监管/制裁先发 → 产业链补跌或国产替代重估",
        "fastest_source": "BIS/OFAC/出口管制/实体清单公告",
        "transmission_path": "限制升级 → 供应链预期变化 → A股板块补跌或分化",
        "hedge_leg": "港股相关板块或指数对冲系统性风险",
        "failure_conditions": "细则不及预期/缓冲期/国内政策对冲/板块内部分化",
    },
}

TEMPLATE_KEYWORDS: Dict[str, List[str]] = {
    "ah_spread": ["A/H", "AH溢价", "H股", "港股通", "溢价指数"],
    "overseas_macro": ["FOMC", "CPI", "非农", "美债", "美元", "加息", "降息", "利率"],
    "commodities": ["LME", "COMEX", "铜", "铝", "锌", "金", "原油", "矿", "库存"],
    "regulatory": ["出口管制", "实体清单", "制裁", "禁运", "BIS", "OFAC", "限制"],
}

SECTOR_PROFILES: Dict[str, Dict[str, List[str]]] = {
    "半导体": {
        "triggers": ["出口管制", "制程", "EDA", "光刻", "封测", "产能", "良率", "CapEx"],
        "mapping": ["设备/材料", "制造/代工", "封测", "设计", "下游应用"],
        "verification": ["链条扩散与成交量同步", "交期/价格验证"],
    },
    "AI算力": {
        "triggers": ["算力", "GPU", "服务器", "光模块", "IDC", "液冷", "PUE", "中标"],
        "mapping": ["服务器整机", "光模块/光器件", "IDC电力/液冷", "上游关键部件"],
        "verification": ["订单→交付→回款链路", "产业链同步走强"],
    },
    "有色": {
        "triggers": ["铜", "铝", "锌", "罢工", "检修", "库存", "升贴水"],
        "mapping": ["矿山", "冶炼加工", "下游成本端"],
        "verification": ["国内期货趋势确认", "库存变化配合"],
    },
    "黄金": {
        "triggers": ["黄金", "避险", "实际利率", "央行购金", "地缘"],
        "mapping": ["金矿", "黄金冶炼/回收", "黄金零售/饰品"],
        "verification": ["金价+黄金股扩散+成交量匹配"],
    },
    "创新药": {
        "triggers": ["III期", "数据读出", "获批", "受理", "适应症", "医保", "集采", "license-out"],
        "mapping": ["核心药物公司", "产业链合作方", "主题扩散"],
        "verification": ["监管节点/商业化路径可跟踪"],
    },
    "银行地产": {
        "triggers": ["降准", "降息", "LPR", "净息差", "不良", "白名单", "收储", "保交楼"],
        "mapping": ["银行息差/资产质量", "地产融资/交付/回款"],
        "verification": ["数据兑现与政策一致"],
    },
}

ALERT_KEYWORDS: Dict[str, List[str]] = {
    "strong": [
        "立案调查",
        "行政处罚",
        "监管措施",
        "问询函",
        "停牌",
        "复牌",
        "退市风险",
        "业绩预告",
        "业绩快报",
        "重大合同",
        "中标",
        "并购重组",
        "回购",
        "增持",
        "注销",
        "出口管制",
        "实体清单",
        "制裁",
        "禁运",
    ],
    "normal": [
        "先进制程",
        "EDA",
        "光刻",
        "刻蚀",
        "薄膜",
        "量测",
        "良率",
        "稼动率",
        "CapEx",
        "算力集群",
        "GPU",
        "服务器",
        "光模块",
        "IDC",
        "液冷",
        "PUE",
        "能耗指标",
        "罢工",
        "事故",
        "检修",
        "减产",
        "库存",
        "升贴水",
        "现货紧张",
        "实际利率",
        "避险",
        "央行购金",
        "地缘冲突",
        "III期",
        "数据读出",
        "获批",
        "受理",
        "适应症",
        "医保谈判",
        "集采",
        "license-out",
        "降准",
        "降息",
        "LPR",
        "净息差",
        "不良",
        "拨备",
        "白名单",
        "收储",
        "保交楼",
        "首付比例",
        "房贷利率",
    ],
}

def load_template_overrides(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except Exception:
        return

    templates = payload.get("event_templates")
    if isinstance(templates, dict):
        EVENT_TEMPLATES.update(templates)

    keywords = payload.get("template_keywords")
    if isinstance(keywords, dict):
        TEMPLATE_KEYWORDS.update(keywords)

    sectors = payload.get("sector_profiles")
    if isinstance(sectors, dict):
        SECTOR_PROFILES.update(sectors)

    alert_keywords = payload.get("alert_keywords")
    if isinstance(alert_keywords, dict):
        for level, values in alert_keywords.items():
            if isinstance(values, list):
                ALERT_KEYWORDS[level] = values


load_template_overrides(os.getenv("EVENT_TEMPLATES_PATH", "/app/event_templates.json"))


def match_event_template(text: str) -> Optional[Dict[str, str]]:
    normalized = text.lower()
    for key, keywords in TEMPLATE_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            return EVENT_TEMPLATES[key]
    return None


def match_sectors(text: str) -> List[Dict[str, List[str]]]:
    normalized = text.lower()
    matches: List[Dict[str, List[str]]] = []
    for name, profile in SECTOR_PROFILES.items():
        if any(trigger.lower() in normalized for trigger in profile["triggers"]):
            matches.append({"name": name, **profile})
    return matches


def classify_alert_keywords(text: str) -> Dict[str, List[str]]:
    normalized = text.lower()
    strong_hits = [k for k in ALERT_KEYWORDS["strong"] if k.lower() in normalized]
    if strong_hits:
        return {"level": "strong", "keywords": strong_hits}

    normal_hits = [k for k in ALERT_KEYWORDS["normal"] if k.lower() in normalized]
    if normal_hits:
        return {"level": "normal", "keywords": normal_hits}

    return {"level": "info", "keywords": []}
