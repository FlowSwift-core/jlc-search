"""AI 智能搜索模块 - 语义理解版"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

# AI 配置
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://integrate.api.nvidia.com/v1")
AI_API_KEY = os.environ.get(
    "AI_API_KEY",
    "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",
)
AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-oss-120b")


@dataclass
class SearchIntent:
    """搜索意图解析结果"""

    parsed_query: str  # 标准化查询
    category: str | None  # 类别过滤
    subcategory: str | None  # 子类过滤
    mfr_pattern: str | None  # 型号匹配
    package: str | None  # 封装过滤
    strict_filters: dict  # 严格过滤条件
    sql: str  # 生成的 SQL


SYSTEM_PROMPT = """你是一个电子元件搜索意图解析器。分析用户的自然语言查询，输出 JSON 结构。

数据库表结构：
- components: lcsc, mfr, package, description, stock, basic, preferred, price, datasheet, category_id, extra
- categories: id, category, subcategory

常见类别（必须使用这些精确名称）：
- Resistors (电阻)
- Capacitors (电容)
- Diodes (二极管)
- Transistors (晶体管)
- Connectors (连接器): USB Connectors, Pin Headers, FPC Connectors
- Optoelectronics (光电): Light Emitting Diodes (LED)
- Crystals (晶振)
- Embedded Processors & Controllers (嵌入式处理器): ST Microelectronics, Microchip, etc.
- Power Management ICs (电源管理)
- Analog ICs (模拟IC): Operational Amplifier, Comparators
- Sensors (传感器)
- IoT/Communication Modules (通信模块)

电阻值代码：1001=1K, 1002=10K, 1003=100K, 1004=1M
电容值代码：104=100nF, 105=1uF, 106=10uF, 107=100uF

输出格式（严格 JSON）：
{
    "parsed_query": "English description only (no Chinese)",
    "category": "category name or null",
    "subcategory": "subcategory name or null",
    "mfr_pattern": "matching pattern or null",
    "package": "package or null",
    "strict_filters": {
        "must_be_category": true/false,
        "is_ic": true/false
    }
}

重要规则：
1. parsed_query 必须是英文！数据库内容全是英文
2. 类别必须准确！搜索"连接器"必须 category=Connectors
3. 搜索 LED 时 category=Optoelectronics, subcategory=Light Emitting Diodes
4. 型号使用精确匹配：STM32F103C8T6 -> mfr_pattern="STM32F103C8T6"
5. 电阻值用代码：10K -> mfr_pattern="1002"
6. 颜色用大写：RED, GREEN, BLUE
7. 不要猜测，不确定的字段设为 null

示例：
用户：USB-C 连接器
输出：{"parsed_query":"USB Type-C Connector","category":"Connectors","subcategory":"USB Connectors","mfr_pattern":"USB","package":null,"strict_filters":{"must_be_category":true,"is_ic":false}}

用户：10K 0603 电阻
输出：{"parsed_query":"10K 0603 Resistor","category":"Resistors","subcategory":"Chip Resistor - Surface Mount","mfr_pattern":"1002","package":"0603","strict_filters":{"must_be_category":true,"is_ic":false}}

用户：STM32F103C8T6
输出：{"parsed_query":"STM32F103C8T6 ARM Microcontroller","category":"Embedded Processors & Controllers","subcategory":"ST Microelectronics","mfr_pattern":"STM32F103C8T6","package":null,"strict_filters":{"must_be_category":false,"is_ic":true}}

用户：LED 红色 0805
输出：{"parsed_query":"Red LED 0805","category":"Optoelectronics","subcategory":"Light Emitting Diodes (LED)","mfr_pattern":"0805R","package":"0805","strict_filters":{"must_be_category":true,"is_ic":false}}

用户：100nF 电容
输出：{"parsed_query":"100nF MLCC Capacitor","category":"Capacitors","subcategory":"Multilayer Ceramic Capacitors","mfr_pattern":"104","package":null,"strict_filters":{"must_be_category":true,"is_ic":false}}

用户：0.1uF 电容
输出：{"parsed_query":"100nF (0.1uF) MLCC Capacitor","category":"Capacitors","subcategory":"Multilayer Ceramic Capacitors","mfr_pattern":"104","package":null,"strict_filters":{"must_be_category":true,"is_ic":false}}
"""


def parse_intent(query: str) -> SearchIntent:
    """使用 AI 解析搜索意图"""
    try:
        from openai import OpenAI

        client = OpenAI(base_url=AI_BASE_URL, api_key=AI_API_KEY)

        completion = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
            max_tokens=300,
            stream=False,
        )

        response = completion.choices[0].message.content

        # 清理响应，提取 JSON
        # 移除 markdown 代码块
        response = re.sub(r"```json?\s*", "", response)
        response = re.sub(r"```\s*$", "", response)

        # 尝试找到 JSON 对象
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group()
            # 清理 JSON 字符串
            json_str = json_str.strip()
            # 修复常见的 JSON 格式问题
            json_str = re.sub(r",\s*}", "}", json_str)  # 移除尾逗号
            json_str = re.sub(r",\s*]", "]", json_str)
            intent_data = json.loads(json_str)
        else:
            raise ValueError(f"无法从响应中提取 JSON: {response}")

        # 构建 SQL
        sql = _build_sql(intent_data)

        return SearchIntent(
            parsed_query=intent_data.get("parsed_query", query),
            category=intent_data.get("category"),
            subcategory=intent_data.get("subcategory"),
            mfr_pattern=intent_data.get("mfr_pattern"),
            package=intent_data.get("package"),
            strict_filters=intent_data.get("strict_filters", {}),
            sql=sql,
        )

    except Exception as e:
        print(f"AI 意图解析失败: {e}")
        # 降级到简单搜索
        return SearchIntent(
            parsed_query=query,
            category=None,
            subcategory=None,
            mfr_pattern=query,
            package=None,
            strict_filters={},
            sql=f"SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet, extra FROM components WHERE mfr LIKE '%{query}%' OR description LIKE '%{query}%' ORDER BY basic DESC, preferred DESC, stock DESC LIMIT 5",
        )


def _build_sql(intent: dict) -> str:
    """根据意图构建 SQL"""
    conditions = []
    params = []

    # 型号匹配
    mfr_pattern = intent.get("mfr_pattern")
    if mfr_pattern:
        conditions.append(f"mfr LIKE '%{mfr_pattern}%'")

    # 封装匹配
    package = intent.get("package")
    if package:
        conditions.append(f"package LIKE '%{package}%'")

    # 类别匹配（通过 JOIN）
    category = intent.get("category")
    subcategory = intent.get("subcategory")
    strict_filters = intent.get("strict_filters", {})
    must_be_category = strict_filters.get("must_be_category", False)

    # 构建基础 SQL
    if category and must_be_category:
        # 需要 JOIN categories 表
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT c.lcsc, c.mfr, c.package, c.stock, c.basic, c.preferred, c.price, c.datasheet, c.extra
            FROM components c
            LEFT JOIN categories cat ON c.category_id = cat.id
            WHERE {where_clause}
            AND (cat.category LIKE '%{category}%' OR cat.subcategory LIKE '%{category}%')
        """
        if subcategory:
            sql += f" AND cat.subcategory LIKE '%{subcategory}%'"
    else:
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet, extra
            FROM components
            WHERE {where_clause}
        """

    sql += "\nORDER BY basic DESC, preferred DESC, stock DESC LIMIT 5"

    return sql.strip()


def generate_sql_with_ai(query: str) -> tuple[str, SearchIntent]:
    """使用 AI 生成 SQL（返回 SQL 和意图）"""
    intent = parse_intent(query)
    return intent.sql, intent
