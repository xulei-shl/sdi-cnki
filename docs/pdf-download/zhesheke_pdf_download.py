#!/usr/bin/env python3
"""
哲社科 PDF 下载脚本 - 使用 Camoufox 反检测（同步版）
"""

import sys
import time
import os
import shutil
from pathlib import Path
from camoufox.sync_api import Camoufox
from camoufox.addons import DefaultAddons

# 导入关键词处理工具
from keyword_processor import sanitize_for_playwright, diagnose_keyword_issue


def wait_for_element_or_timeout(page, selector: str, timeout: int = 30000, state: str = "visible"):
    """
    等待元素出现，带最大超时时间
    
    Args:
        page: Playwright page 对象
        selector: CSS 选择器
        timeout: 最大等待时间（毫秒）
        state: 等待状态 ("visible", "attached", "hidden", "detached")
    
    Returns:
        元素对象，如果超时则返回 None
    """
    try:
        return page.wait_for_selector(selector, timeout=timeout, state=state)
    except Exception:
        return None


def zhesheke_download(keyword: str, default_timeout: int = 30000, max_retries: int = 1, output_dir: str = None):
    """从哲社科检索并下载 PDF（使用 Camoufox）
    
    Args:
        keyword: 检索关键词
        default_timeout: 默认超时时间
        max_retries: 最大重试次数（默认1次）
        output_dir: 自定义输出目录（支持环境变量PDF_OUTPUT_DIR）
    
    Returns:
        下载文件的路径，失败返回 None
    """
    print(f"检索关键词: {keyword}")

    # 优先使用传入的output_dir，否则尝试环境变量，最后使用默认路径
    if output_dir is None:
        output_dir = os.environ.get('PDF_OUTPUT_DIR', '')
    
    if output_dir:
        target_dir = Path(output_dir)
    else:
        # 默认保存目录（兼容旧版本）
        target_dir = Path("/home/xulei/github-cc/claudebot/temps") / "scholar-pdf" / "zhesheke"
    
    target_dir.mkdir(parents=True, exist_ok=True)

    last_error = None
    should_retry = True
    
    # 重试循环
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n🔄 第 {attempt} 次重试...")
            # 重试前等待一段时间
            time.sleep(2)
        
        should_retry = False  # 重置重试标志
        
        # 使用 Camoufox 启动浏览器
    with Camoufox(
        headless=True,
        geoip=False,
        exclude_addons=[DefaultAddons.UBO]
    ) as browser:
        context = browser.new_context(
            accept_downloads=True,
            locale="zh-CN"
        )

        page = context.new_page()

        try:
            # ========== 1. 打开哲社科首页 ==========
            print("\n[1/6] 打开哲社科首页...")
            page.goto("https://www.ncpssd.org/index", timeout=30000, wait_until="domcontentloaded")
            # 等待页面加载完成或搜索框出现
            wait_for_element_or_timeout(page, "#text_search", timeout=15000)
            print("   ✓ 首页加载完成")

            # ========== 2. 输入检索词 ==========
            print("[2/6] 定位搜索框并输入关键词...")

            # 定位搜索框 #text_search
            search_box = None
            try:
                search_box = page.locator("#text_search")
                if search_box.count() > 0 and search_box.is_visible():
                    print("   ✓ 找到搜索框 #text_search")
                else:
                    search_box = None
            except:
                search_box = None

            if search_box is None:
                # 尝试其他可能的选择器
                search_selectors = [
                    "input[placeholder*='请输入检索词']",
                    "input[maxlength='200']",
                    "input[type='text']",
                    "textarea"
                ]

                for sel in search_selectors:
                    try:
                        elem = page.locator(sel).first
                        if elem.count() > 0 and elem.is_visible():
                            search_box = elem
                            print(f"   ✓ 找到搜索框: {sel}")
                            break
                    except:
                        continue

            if search_box is None:
                raise Exception("无法找到搜索框")

            # 处理关键词（移除可能导致截断的特殊字符）
            safe_keyword = sanitize_for_playwright(keyword)
            
            # 诊断关键词问题（调试用）
            diagnosis = diagnose_keyword_issue(keyword)
            if diagnosis['issues']:
                print(f"   ⚠️  关键词包含特殊字符: {diagnosis['issues']}")
                print(f"   → 处理后: {safe_keyword}")
            
            search_box.fill(safe_keyword)
            print(f"   已输入关键词: {safe_keyword}")
            # 等待输入框内容更新
            page.wait_for_timeout(500)

            # ========== 3. 执行检索 ==========
            print("[3/6] 执行检索...")

            # 记录初始页面数量
            initial_pages = len(context.pages)

            # 尝试按 Enter 键检索
            search_box.press("Enter")

            # 等待页面跳转
            page.wait_for_timeout(3000)

            # 在 Enter 后轮询检测新页面
            new_page = None
            for i in range(30):  # 最多等待15秒
                time.sleep(0.5)
                pages = context.pages
                if len(pages) > initial_pages:
                    new_page = pages[-1]
                    break
            
            # 【关键修复】切换到新 tab
            if new_page:
                page = new_page
            else:
                # 尝试点击搜索按钮
                search_button = None
                button_selectors = [
                    "#btn_search",
                    "button[type='submit']",
                    "input[type='submit']",
                    ".search-btn",
                    "a:has-text('检索')",
                    "button:has-text('检索')",
                    "input[value='检索']",
                    "input[value='搜索']"
                ]
                
                for sel in button_selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.count() > 0 and btn.is_visible():
                            search_button = btn
                            break
                    except:
                        continue
                
                if search_button:
                    search_button.click()
                    page.wait_for_timeout(3000)
                    
                    # 【关键修复】点击按钮后也需要切换到新 tab
                    pages = context.pages
                    if len(pages) > initial_pages:
                        page = pages[-1]
            
            # 等待新页面加载完成
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"   ✓ 检索结果加载完成")

            # ========== 4. 检查是否有结果 ==========
            print("[4/6] 检查检索结果...")

            # 先等待页面完全加载，JavaScript 可能需要时间渲染结果
            page.wait_for_timeout(2000)

            result_count = 0

            # 方法1（最优先）: 直接检查 lbl_numbers
            try:
                lbl_numbers = page.locator("#lbl_numbers")
                if lbl_numbers.count() > 0:
                    result_text = lbl_numbers.first.inner_text().strip()
                    if result_text:
                        # 明确检查是否为"0"，如果是则直接设置结果数为0
                        if result_text == "0":
                            result_count = 0
                            print("   哲社科检索无结果")
                            # 【无结果】返回None，让调用方决定是否尝试万方
                            return None
                        else:
                            result_count = int(result_text)
            except Exception as e:
                print(f"   方法1出错: {e}")
            
            # 方法2（备选）: 检查 lbl_pagenumber - 当方法1无法获取结果时使用
            if result_count == 0:
                try:
                    lbl_pagenumber = page.locator("#lbl_pagenumber")
                    if lbl_pagenumber.count() > 0:
                        page_text = lbl_pagenumber.first.inner_text().strip()
                        import re
                        match = re.search(r'-(\d+)', page_text)
                        if match and match.group(1) != "0":
                            result_count = int(match.group(1))
                except Exception as e:
                    print(f"   方法2出错: {e}")
            
            # 方法3（备选）: 检查标题栏文本
            if result_count == 0:
                try:
                    term_title = page.locator("#term-title, .term-title, h3.term-title")
                    if term_title.count() > 0:
                        title_text = term_title.first.inner_text()
                        if "0 条" in title_text or "0条" in title_text:
                            result_count = 0
                        else:
                            import re
                            numbers = re.findall(r'(\d+)', title_text)
                            if numbers:
                                result_count = int(numbers[0])
                            else:
                                result_count = 1
                except Exception as e:
                    print(f"   方法3出错: {e}")
            
            # 方法4（兜底）: 检查列表元素
            if result_count == 0:
                try:
                    list_items = page.locator("#ul_articlelist li")
                    if list_items.count() > 0:
                        result_count = list_items.count()
                    else:
                        julei_items = page.locator(".julei-list")
                        if julei_items.count() > 0:
                            result_count = julei_items.count()
                except Exception as e:
                    print(f"   方法4出错: {e}")

            if result_count == 0:
                print("   哲社科检索无结果")
                # 【无结果】返回None，让调用方决定是否尝试万方
                return None

            print(f"   找到 {result_count} 条结果")

            # ========== 5. 定位并点击第一条结果的下载按钮 ==========
            print("[5/6] 定位并点击第一条结果的下载按钮...")

            # 查找第一条结果中的"全文下载"按钮
            pdf_button = None
            pdf_selectors = [
                ".julei-list a:has-text('全文下载')",
                "a:has-text('全文下载')",
                "a.r100",
                "a[class*='r100']:has-text('全文下载')",
                ".article-list a:has-text('全文下载')",
                ".result-list a:has-text('全文下载')",
                "div[class*='download'] a",
                "a[href*='download']",
                "a[href*='Download']",
                "a[onclick*='download']"
            ]

            for sel in pdf_selectors:
                try:
                    elems = page.locator(sel).all()
                    if elems:
                        for elem in elems:
                            if not elem.is_visible():
                                continue
                            text = elem.inner_text().strip()
                            if text and "全文" in text:
                                pdf_button = elem
                                print(f"   ✓ 找到下载按钮: {sel}")
                                break
                    if pdf_button:
                        break
                except:
                    continue

            if pdf_button is None:
                # 尝试更宽松的匹配
                for link in page.locator("a").all():
                    try:
                        if not link.is_visible():
                            continue
                        text = link.inner_text()
                        if text and "全文" in text:
                            pdf_button = link
                            print(f"   ✓ 找到下载按钮（宽松匹配）")
                            break
                    except:
                        continue

            if pdf_button is None:
                raise Exception("无法找到 PDF 下载按钮")

            # ========== 6. 点击下载并保存文件 ==========
            print("[6/6] 点击下载按钮...")

            download_path = None
            try:
                # 使用 page.expect_download() 包装下载流程
                with page.expect_download(timeout=30000) as download_info:
                    # 点击下载按钮
                    pdf_button.click()
                    # 等待下载开始
                    page.wait_for_timeout(3000)
                
                # 获取下载信息并保存
                download = download_info.value
                suggested_filename = download.suggested_filename
                save_path = target_dir / suggested_filename
                download.save_as(str(save_path))
                download_path = save_path

            except Exception as e:
                print(f"   下载失败: {e}")
                # 不再额外检查 Downloads 目录，因为 expect_download 已经是最可靠的检测方式
                last_error = f"下载失败: {e}"
                # 设置重试标志，让循环继续
                should_retry = True

            if download_path and download_path.exists():
                size_mb = download_path.stat().st_size / 1024 / 1024
                print("\n✅ 下载成功！")
                print(f"文件路径: {download_path}")
                # print(f"文件大小: {size_mb:.2f} MB")
                return str(download_path)
            else:
                print("\n⚠️  未检测到下载文件")
                last_error = "未检测到下载文件"
                # 设置重试标志，让循环继续
                should_retry = True

        except Exception as e:
            print(f"\n❌ 执行出错: {e}")
            last_error = str(e)

            # 无结果时不重试，直接返回
            if "检索无结果" in str(e):
                return None

            # 其他错误，设置重试标志让循环继续
            import traceback
            traceback.print_exc()
            should_retry = True
    
    # 所有重试都失败
    print(f"\n❌ 下载失败，已重试 {max_retries} 次")
    print(f"最后错误: {last_error}")
    print("浏览器保持打开状态以便调试...")
    # 保持浏览器打开但不阻塞
    return None


def main():
    """处理命令行参数，支持包含中文引号的关键词
    
    用法:
        python zhesheke_pdf_download.py "关键词" [重试次数]
        python zhesheke_pdf_download.py "五年后的图书馆：清华大学图书馆"十五五"努力方向" 2
    """
    
    if len(sys.argv) > 1:
        # 检查是否需要合并所有参数（处理中文引号导致的参数分割）
        # 尝试将所有非数字参数合并作为关键词
        keyword_parts = []
        max_retries = 1
        
        for i, arg in enumerate(sys.argv[1:], 1):
            # 尝试将参数解析为整数（用于重试次数）
            try:
                # 如果参数可以转换为整数，可能是重试次数
                # 但要排除纯数字的关键词（如 "123"）
                if arg.isdigit() and len(arg) <= 2:  # 假设重试次数不会超过99
                    max_retries = int(arg)
                else:
                    keyword_parts.append(arg)
            except ValueError:
                keyword_parts.append(arg)
        
        # 合并关键词部分
        original_keyword = ' '.join(keyword_parts)
        
        # 诊断原始参数列表（当有多个参数时）
        if len(sys.argv) > 2:
            print(f"   ⚠️ 检测到多个参数，原始输入可能被分割")
            print(f"   原始参数: {sys.argv[1:]}")
            print(f"   合并后关键词: {original_keyword}")
            print(f"   重试次数: {max_retries}")
        
        keyword = original_keyword if original_keyword else "AI4S背景下的知识创新服务应用模式、平台系统与微服务设计研究"
    else:
        keyword = "AI4S背景下的知识创新服务应用模式、平台系统与微服务设计研究"
        max_retries = 1
    
    zhesheke_download(keyword, max_retries=max_retries)


if __name__ == "__main__":
    main()
