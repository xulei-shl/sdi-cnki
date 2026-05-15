#!/usr/bin/env python3
"""
关键词处理工具 - 用于处理搜索关键词中的特殊字符

解决的问题：
1. 中文引号（""）可能导致搜索框内容被截断
2. 特殊符号导致JavaScript解析错误
3. 其他可能导致输入被截断的字符

使用方法：
    from keyword_processor import process_keyword
    
    # 在爬虫脚本中调用
    keyword = "基于机器学习的"从0到1"型技术融合预测方法研究"
    safe_keyword = process_keyword(keyword)
    search_box.fill(safe_keyword)
"""

import re
from typing import Optional


# 需要替换的特殊字符映射表
SPECIAL_CHAR_REPLACEMENTS = {
    # 中文引号 -> 英文引号或空格
    '"': '"',  # 左双引号
    '"': '"',  # 右双引号
    ''': "'",  # 左单引号
    ''': "'",  # 右单引号
    
    # 特殊符号 -> 空字符或替换
    '«': '',   # 左角引号
    '»': '',   # 右角引号
    '‹': '',   # 左单角引号
    '›': '',   # 右单角引号
    
    # 常见数学符号
    '×': '*',
    '÷': '/',
    '−': '-',
    '–': '-',  # en dash
    '—': '-',  # em dash
    
    # 全角空格等
    '\u3000': ' ',  # 全角空格
    '\u200b': '',   # 零宽空格
}


def process_keyword(keyword: str, strip_quotes: bool = True, 
                   remove_special: bool = False, max_length: Optional[int] = None) -> str:
    """
    处理关键词，使其适合搜索框输入
    
    Args:
        keyword: 原始关键词
        strip_quotes: 是否移除引号（默认True，因为引号常导致截断）
        remove_special: 是否移除所有特殊字符（默认False，保留基本标点）
        max_length: 最大长度限制
    
    Returns:
        处理后的安全关键词
    """
    if not keyword:
        return ""
    
    result = keyword
    
    # 1. 替换特殊字符
    if strip_quotes:
        # 移除可能导致问题的引号
        result = result.replace('"', '').replace('"', '')
        result = result.replace(''', '').replace(''', '')
        result = result.replace('«', '').replace('»', '')
        result = result.replace('‹', '').replace('›', '')
    
    if remove_special:
        # 移除所有非字母数字和基本标点的字符
        result = re.sub(r'[^\w\s\u4e00-\u9fff\-_.,;:!?。，；：！？]', '', result)
    
    # 2. 规范化空白字符
    result = re.sub(r'\s+', ' ', result)  # 多个空格合并为一个
    result = result.strip()  # 去除首尾空白
    
    # 3. 限制最大长度
    if max_length and len(result) > max_length:
        result = result[:max_length]
    
    return result


def sanitize_for_playwright(keyword: str) -> str:
    """
    为 Playwright fill() 方法特别处理关键词
    某些字符在使用 fill() 时可能导致问题
    
    Args:
        keyword: 原始关键词
    
    Returns:
        适合 Playwright fill() 的安全字符串
    """
    # 移除零宽字符
    keyword = keyword.replace('\u200b', '')  # 零宽空格
    keyword = keyword.replace('\u200c', '')  # 零宽非连接符
    keyword = keyword.replace('\u200d', '')  # 零宽连接符
    keyword = keyword.replace('\ufeff', '')  # BOM
    
    # 移除可能导致 JavaScript 截断的特殊引号
    keyword = keyword.replace('"', '')
    keyword = keyword.replace('"', '')
    keyword = keyword.replace(''', '')
    keyword = keyword.replace(''', '')
    
    # 规范化空白
    keyword = re.sub(r'[\u3000\u200b]+', ' ', keyword)
    keyword = keyword.strip()
    
    return keyword


def test_fill_input(page, selector: str, keyword: str, **kwargs) -> bool:
    """
    测试使用 fill() 方法输入关键词，如果失败则尝试替代方法
    
    Args:
        page: Playwright page 对象
        selector: CSS 选择器
        keyword: 关键词
        **kwargs: 传递给 fill() 的其他参数
    
    Returns:
        是否成功
    """
    from playwright.sync_api import TimeoutError
    
    try:
        page.fill(selector, keyword, **kwargs)
        return True
    except TimeoutError:
        # 如果 fill 失败，尝试使用 eval 或其他方法
        return False


def diagnose_keyword_issue(keyword: str) -> dict:
    """
    诊断关键词中可能导致问题的字符
    
    Args:
        keyword: 关键词
    
    Returns:
        诊断结果字典
    """
    issues = []
    char_analysis = {}
    
    # 检查特殊字符
    problem_chars = {
        '"': '中文左双引号',
        '"': '中文右双引号',
        ''': '中文左单引号',
        ''': '中文右单引号',
        '«': '左角引号',
        '»': '右角引号',
        '\u200b': '零宽空格',
        '\u200c': '零宽非连接符',
        '\u200d': '零宽连接符',
        '\u3000': '全角空格',
        '\ufeff': 'BOM字符',
    }
    
    for char, desc in problem_chars.items():
        count = keyword.count(char)
        if count > 0:
            issues.append(f"发现 {count} 个「{desc}」")
            char_analysis[repr(char)] = count
    
    return {
        "original": keyword,
        "length": len(keyword),
        "issues": issues,
        "char_analysis": char_analysis,
        "processed": process_keyword(keyword),
        "sanitized": sanitize_for_playwright(keyword)
    }


# CLI 测试入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
    else:
        keyword = '基于机器学习的"从0到1"型技术融合预测方法研究'
    
    print(f"原始关键词: {keyword}")
    print("-" * 50)
    
    result = diagnose_keyword_issue(keyword)
    
    print(f"关键词长度: {result['length']}")
    print(f"发现的问题: {result['issues'] if result['issues'] else '无'}")
    print("-" * 50)
    print(f"处理后 (process_keyword): {result['processed']}")
    print(f"处理后 (sanitize): {result['sanitized']}")