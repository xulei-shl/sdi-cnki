#!/usr/bin/env python3
"""
文本标准化工具 - 用于PDF文件名与标题匹配验证

功能：
1. 将文本标准化，移除所有空格、标点符号、特殊字符
2. 计算两个文本的相似度
3. 判断标题与文件名是否匹配
"""

import re
import unicodedata
from typing import Tuple


# 中文标点符号映射表（用于移除）
CHINESE_PUNCTUATION = {
    '，': '', '。': '', '！': '', '？': '', '；': '',
    '：': '', '"': '', '"': '', ''': '', ''': '',
    '（': '', '）': '', '【': '', '】': '', '《': '',
    '》': '', '〈': '', '〉': '', '「': '', '」': '',
    '『': '', '』': '', '〔': '', '〕': '', '【': '',
    '】': '', '·': '', '—': '', '–': '', '…': '',
    '‖': '', '—': '', '～': '', '丶': '', '、': '',
    '／': '', '／': '', '｜': '', '﹑': '', '﹒': '',
    '﹕': '', '﹖': '', '﹣': '', '﹝': '', '﹞': '',
    '﹟': '', '﹠': '', '﹡': '', '﹢': '', '﹣': '',
    '﹤': '', '﹥': '', '﹦': '', '﹨': '', '﹩': '',
    '﹪': '', '﹫': '', '﹬': '', '﹭': '', '﹮': '',
    '﹯': '', 'ﹰ': '', 'ﹱ': '', 'ﹲ': '', 'ﹴ': '',
    '﹵': '', 'ﹶ': '', 'ﹷ': '', 'ﹸ': '', 'ﹹ': '',
    'ﹺ': '', 'ﹻ': '', 'ﹼ': '', 'ﹽ': '', 'ﹾ': '',
    'ﹿ': '', '金星': '', '金星': '',
}

# 英文标点符号
ENGLISH_PUNCTUATION = {
    ',', '.', '!', '?', ';', ':', '"', '"', "'", "'",
    '(', ')', '[', ']', '{', '}', '<', '>', '/', '\\',
    '|', '-', '_', '+', '=', '*', '&', '^', '%', '$',
    '#', '@', '!', '~', '`', '…',
}


def normalize_text(text: str) -> str:
    """
    将文本标准化，移除所有空格、标点符号、特殊字符
    
    处理步骤：
    1. Unicode规范化（NFC）
    2. 转换为全角转半角
    3. 移除所有空格（包含全角空格）
    4. 移除所有标点符号（中英文）
    5. 移除零宽字符
    6. 转为小写
    
    Args:
        text: 原始文本
        
    Returns:
        标准化后的文本
    """
    if not text:
        return ""
    
    # Unicode规范化
    text = unicodedata.normalize('NFC', text)
    
    # 全角转半角
    text = _fullwidth_to_halfwidth(text)
    
    # 移除中文标点
    for ch, replacement in CHINESE_PUNCTUATION.items():
        text = text.replace(ch, replacement)
    
    # 移除英文标点
    for p in ENGLISH_PUNCTUATION:
        text = text.replace(p, '')
    
    # 移除零宽字符
    text = text.replace('\u200b', '')  # 零宽空格
    text = text.replace('\u200c', '')  # 零宽非连接符
    text = text.replace('\u200d', '')  # 零宽连接符
    text = text.replace('\ufeff', '')  # BOM
    
    # 移除所有空格（包含全角空格）
    text = re.sub(r'[\s\u3000]+', '', text)
    
    # 转为小写
    text = text.lower()
    
    return text


def _fullwidth_to_halfwidth(text: str) -> str:
    """全角转半角"""
    result = []
    for char in text:
        inside_code = ord(char)
        # 全角字符范围：0xFF01-0xFF5E
        if inside_code == 0x3000:  # 全角空格
            inside_code = 0x0020
        elif 0xFF01 <= inside_code <= 0xFF5E:
            inside_code -= 0xFEE0
        result.append(chr(inside_code))
    return ''.join(result)


def extract_filename_key(filename: str) -> str:
    """
    从文件名提取关键信息用于匹配
    
    处理步骤：
    1. 移除.pdf后缀
    2. 从右往左找到第一个_，去掉_及其后面的内容（如作者信息）
    3. 标准化处理
    
    Args:
        filename: PDF文件名
        
    Returns:
        提取后的关键文本
    """
    name = filename
    
    if name.lower().endswith('.pdf'):
        name = name[:-4]
    
    last_underscore_idx = name.rfind('_')
    if last_underscore_idx > 0:
        name = name[:last_underscore_idx]
    
    return normalize_text(name)


def calculate_similarity(text1: str, text2: str) -> float:
    """
    计算两个文本的相似度（基于字符重合率）
    
    Args:
        text1: 文本1
        text2: 文本2
        
    Returns:
        相似度（0-1之间）
    """
    normalized1 = normalize_text(text1)
    normalized2 = normalize_text(text2)
    
    if not normalized1 or not normalized2:
        return 0.0
    
    # 计算字符集合的重合率
    set1 = set(normalized1)
    set2 = set(normalized2)
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def is_match(title: str, filename: str, threshold: float = 0) -> Tuple[bool, str]:
    """
    判断标题与文件名是否匹配
    
    匹配规则：
    - 完全匹配：标准化后的标题与文件名完全相同
    - 前端匹配：标准化后的标题是标准化后的文件名的前缀
    - 截断匹配：标准化后的文件名是标准化后的标题的前缀（CNKI下载的文件名被截断情况）
    - 公共子串匹配：标题和文件名有足够长的公共子串（处理中间截断差异）
    - 相似度匹配：相似度大于等于阈值（仅当threshold > 0时启用）
    
    Args:
        title: 文章标题
        filename: PDF文件名
        threshold: 相似度阈值（0表示只支持完全匹配和前端匹配）
        
    Returns:
        (是否匹配, 匹配原因/不匹配原因)
    """
    if not title or not filename:
        return False, "标题或文件名为空"
    
    # 标准化处理
    normalized_title = normalize_text(title)
    normalized_filename = extract_filename_key(filename)
    
    # 完全匹配
    if normalized_title == normalized_filename:
        return True, "完全匹配"
    
    # 前端匹配：标准化后的标题是标准化后的文件名的前缀
    if normalized_filename.startswith(normalized_title):
        return True, f"前端匹配（检索词是PDF文件名的前缀）"
    
    # 截断匹配：标准化后的文件名是标准化后的标题的前缀
    # （处理CNKI下载时文件名被截断的情况，如"技术迭代驱动下美国高校图书馆数...2025_ACRL"）
    if normalized_title.startswith(normalized_filename):
        return True, f"截断匹配（PDF文件名是标题的截断版本）"
    
    # 公共子串匹配：检查标题和文件名是否有足够长的公共子串
    # 处理"与启示" vs "与启12025"这类中间截断差异
    min_len = min(len(normalized_title), len(normalized_filename))
    if min_len >= 20:
        common_len = longest_common_substring_length(normalized_title, normalized_filename)
        if common_len >= min_len * 0.5:
            return True, f"公共子串匹配（公共长度{common_len}/{min_len}，{common_len/min_len:.0%}）"
    
    # 如果设置了阈值，尝试相似度匹配
    if threshold > 0:
        similarity = calculate_similarity(title, filename)
        if similarity >= threshold:
            return True, f"相似度匹配 ({similarity:.2%})"
    
    # 不匹配，提供诊断信息
    reason = f"不匹配 - 标题标准化: '{normalized_title[:30]}...' vs 文件名: '{normalized_filename[:30]}...'"
    return False, reason


def longest_common_substring_length(s1: str, s2: str) -> int:
    """
    计算两个字符串的最长公共子串长度（简化版，贪心匹配）
    
    Args:
        s1: 字符串1
        s2: 字符串2
        
    Returns:
        最长公共子串长度
    """
    if not s1 or not s2:
        return 0
    
    max_len = 0
    # 从较短字符串的开始位置尝试匹配
    for start in range(len(s2)):
        for length in range(min(len(s2) - start, len(s1)), 0, -1):
            substring = s2[start:start + length]
            if substring in s1 and length > max_len:
                max_len = length
        if max_len >= len(s2) - start:
            break
    
    return max_len


def diagnose_text(text: str) -> dict:
    """
    诊断文本中的特殊字符
    
    Args:
        text: 待诊断的文本
        
    Returns:
        诊断结果字典
    """
    issues = []
    
    # 检查特殊字符
    problem_chars = {
        '\u200b': '零宽空格',
        '\u200c': '零宽非连接符',
        '\u200d': '零宽连接符',
        '\ufeff': 'BOM字符',
        '\u3000': '全角空格',
    }
    
    for char, desc in problem_chars.items():
        if char in text:
            count = text.count(char)
            issues.append(f"发现 {count} 个「{desc}」")
    
    # 检查标点符号数量
    punctuation_count = sum(1 for c in text if c in CHINESE_PUNCTUATION or c in ENGLISH_PUNCTUATION)
    
    return {
        "original": text,
        "length": len(text),
        "normalized": normalize_text(text),
        "issues": issues,
        "punctuation_count": punctuation_count,
    }


# CLI测试入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        title = sys.argv[1]
        filename = sys.argv[2] if len(sys.argv) > 2 else "测试文件.pdf"
    else:
        title = "分级阅读的历史逻辑、本土特质与实践路径"
        filename = "分级阅读的历史逻辑本土特质与实践路径.pdf"
    
    print(f"标题: {title}")
    print(f"文件名: {filename}")
    print("-" * 50)
    
    # 诊断
    print("标题诊断:")
    title_diag = diagnose_text(title)
    print(f"  原始长度: {title_diag['length']}")
    print(f"  标准化: {title_diag['normalized']}")
    print(f"  问题: {title_diag['issues'] if title_diag['issues'] else '无'}")
    print(f"  标点数: {title_diag['punctuation_count']}")
    
    print("\n文件名诊断:")
    filename_diag = diagnose_text(filename)
    print(f"  原始: {filename}")
    print(f"  标准化: {filename_diag['normalized']}")
    
    print("-" * 50)
    
    # 匹配测试
    is_matched, reason = is_match(title, filename)
    print(f"匹配结果: {is_matched}")
    print(f"原因: {reason}")
    
    # 相似度
    similarity = calculate_similarity(title, filename)
    print(f"相似度: {similarity:.2%}")
