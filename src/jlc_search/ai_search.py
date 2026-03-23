"""AI 智能搜索模块"""

from __future__ import annotations

import os
import re

# AI 配置
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://integrate.api.nvidia.com/v1")
AI_API_KEY = os.environ.get(
    "AI_API_KEY",
    "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",
)
AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-oss-20b")

SYSTEM_PROMPT = """你是一个电子元件搜索助手。根据用户的自然语言描述，生成 SQL 查询语句。

数据库表结构：
- components 表：
  - lcsc (INTEGER): LCSC 编号
  - mfr (TEXT): 制造商型号
  - package (TEXT): 封装
  - description (TEXT): 描述
  - stock (INTEGER): 库存
  - basic (INTEGER): 是否基础库 (1=是)
  - preferred (INTEGER): 是否首选库 (1=是)
  - price (TEXT): 价格 JSON
  - datasheet (TEXT): 数据手册 URL
  - category_id (INTEGER): 类别 ID
  - extra (TEXT): 扩展信息 JSON

- categories 表：
  - id (INTEGER): 类别 ID
  - category (TEXT): 大类
  - subcategory (TEXT): 子类

常用电容值代码：104=100nF, 105=1uF, 106=10uF, 107=100uF
常用电阻值代码：1001=1K, 1002=10K, 1003=100K, 1004=1M

封装代码：0603, 0805, 0402, 1206, SOT-23, SOIC-8, LQFP-48

生成规则：
1. 只生成 SELECT 语句
2. 不要使用 JOIN（除非必要）
3. 使用 LIKE 进行模糊匹配
4. 优先搜索 mfr 和 description
5. 使用 ORDER BY basic DESC, preferred DESC, stock DESC 排序
6. 限制结果数量 LIMIT 5（用户要求少量结果时用 LIMIT 3）
7. 只返回 SQL，不要解释
8. 精确匹配优先：如果有具体型号，优先用型号搜索

示例：
用户：10K 0603 1%
SQL：SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet FROM components WHERE (mfr LIKE '%1002%' OR mfr LIKE '%10K%') AND package LIKE '%0603%' ORDER BY basic DESC, preferred DESC, stock DESC LIMIT 5

用户：100nF 电容 50V
SQL：SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet FROM components WHERE (mfr LIKE '%104%' OR description LIKE '%100nF%') AND (description LIKE '%50V%' OR extra LIKE '%50V%') ORDER BY basic DESC, preferred DESC, stock DESC LIMIT 5

用户：STM32F103C8T6
SQL：SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet FROM components WHERE mfr LIKE '%STM32F103C8T6%' ORDER BY basic DESC, preferred DESC, stock DESC LIMIT 3
"""


def generate_sql_with_ai(query: str) -> str:
    """使用 AI 生成 SQL"""
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
            max_tokens=500,
            stream=False,
        )

        response = completion.choices[0].message.content

        # 提取 SQL
        sql_match = re.search(r"(SELECT\s+.+?)(?:\s*$|\s*```)", response, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        if response.strip().upper().startswith("SELECT"):
            return response.strip()

        raise ValueError(f"无法从 AI 响应中提取 SQL: {response}")

    except Exception as e:
        print(f"AI 生成 SQL 失败: {e}")
        # 降级到简单搜索
        return f"SELECT lcsc, mfr, package, stock, basic, preferred, price, datasheet FROM components WHERE mfr LIKE '%{query}%' OR description LIKE '%{query}%' ORDER BY basic DESC, preferred DESC, stock DESC LIMIT 20"
