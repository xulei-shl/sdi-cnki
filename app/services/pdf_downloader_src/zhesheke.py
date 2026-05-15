#!/usr/bin/env python3
"""
哲社科 PDF 下载脚本 - 原样复刻自 docs/pdf-download/zhesheke_pdf_download.py
改动：支持外部浏览器注入（page 参数），退出条件化清理
"""

import sys
import time
import os
import shutil
from pathlib import Path

from .keyword_processor import sanitize_for_playwright, diagnose_keyword_issue


def wait_for_element_or_timeout(page, selector: str, timeout: int = 30000, state: str = "visible"):
    try:
        return page.wait_for_selector(selector, timeout=timeout, state=state)
    except Exception:
        return None


def zhesheke_download(keyword: str, default_timeout: int = 30000, max_retries: int = 1,
                      output_dir: str = None, page=None):
    """从哲社科检索并下载 PDF（使用 Camoufox）
    
    Args:
        keyword: 检索关键词
        default_timeout: 默认超时时间
        max_retries: 最大重试次数（默认1次）
        output_dir: 自定义输出目录（支持环境变量PDF_OUTPUT_DIR）
        page: 外部浏览器页面（None 时自建 Camoufox）
    
    Returns:
        下载文件的路径，失败返回 None
    """
    print(f"检索关键词: {keyword}")

    if output_dir is None:
        output_dir = os.environ.get('PDF_OUTPUT_DIR', '')

    if output_dir:
        target_dir = Path(output_dir)
    else:
        target_dir = Path.home() / ".cache" / "scholar-pdf" / "zhesheke"

    target_dir.mkdir(parents=True, exist_ok=True)

    own_browser = page is None
    result_path = None
    last_error = None
    should_retry = True

    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n🔄 第 {attempt} 次重试...")
            time.sleep(2)

        should_retry = False

        if own_browser:
            from camoufox.sync_api import Camoufox
            from camoufox.addons import DefaultAddons
            _browser_ctx = Camoufox(headless=True, geoip=False, exclude_addons=[DefaultAddons.UBO])
            browser = _browser_ctx.__enter__()
            context = browser.new_context(accept_downloads=True, locale="zh-CN")
            page = context.new_page()
        else:
            context = page.context

        try:
            # ========== 1. 打开哲社科首页 ==========
            print("\n[1/6] 打开哲社科首页...")
            page.goto("https://www.ncpssd.org/index", timeout=30000, wait_until="domcontentloaded")
            wait_for_element_or_timeout(page, "#text_search", timeout=15000)
            print("   ✓ 首页加载完成")

            # ========== 2. 输入检索词 ==========
            print("[2/6] 定位搜索框并输入关键词...")

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

            safe_keyword = sanitize_for_playwright(keyword)
            diagnosis = diagnose_keyword_issue(keyword)
            if diagnosis['issues']:
                print(f"   ⚠️  关键词包含特殊字符: {diagnosis['issues']}")
                print(f"   → 处理后: {safe_keyword}")

            search_box.fill(safe_keyword)
            print(f"   已输入关键词: {safe_keyword}")
            page.wait_for_timeout(500)

            # ========== 3. 执行检索 ==========
            print("[3/6] 执行检索...")

            initial_pages = len(context.pages)
            search_box.press("Enter")
            page.wait_for_timeout(3000)

            new_page = None
            for i in range(30):
                time.sleep(0.5)
                pages = context.pages
                if len(pages) > initial_pages:
                    new_page = pages[-1]
                    break

            if new_page:
                page = new_page
            else:
                search_button = None
                button_selectors = [
                    "#btn_search", "button[type='submit']", "input[type='submit']",
                    ".search-btn", "a:has-text('检索')", "button:has-text('检索')",
                    "input[value='检索']", "input[value='搜索']"
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
                    pages = context.pages
                    if len(pages) > initial_pages:
                        page = pages[-1]

            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"   ✓ 检索结果加载完成")

            # ========== 4. 检查是否有结果 ==========
            print("[4/6] 检查检索结果...")
            page.wait_for_timeout(2000)

            result_count = 0
            try:
                lbl_numbers = page.locator("#lbl_numbers")
                if lbl_numbers.count() > 0:
                    result_text = lbl_numbers.first.inner_text().strip()
                    if result_text:
                        if result_text == "0":
                            result_count = 0
                            print("   哲社科检索无结果")
                            result_path = None
                            break
                        else:
                            result_count = int(result_text)
            except Exception as e:
                print(f"   方法1出错: {e}")

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
                result_path = None
                break

            print(f"   找到 {result_count} 条结果")

            # ========== 5. 定位并点击第一条结果的下载按钮 ==========
            print("[5/6] 定位并点击第一条结果的下载按钮...")

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

            try:
                with page.expect_download(timeout=30000) as download_info:
                    pdf_button.click()
                    page.wait_for_timeout(3000)

                download = download_info.value
                suggested_filename = download.suggested_filename
                save_path = target_dir / suggested_filename
                download.save_as(str(save_path))
                result_path = str(save_path)

            except Exception as e:
                print(f"   下载失败: {e}")
                last_error = f"下载失败: {e}"
                should_retry = True
                result_path = None

            if result_path and Path(result_path).exists():
                size_mb = Path(result_path).stat().st_size / 1024 / 1024
                print("\n✅ 下载成功！")
                print(f"文件路径: {result_path}")
                break
            else:
                print("\n⚠️  未检测到下载文件")
                last_error = "未检测到下载文件"
                should_retry = True
                result_path = None

        except Exception as e:
            print(f"\n❌ 执行出错: {e}")
            last_error = str(e)
            if "检索无结果" in str(e):
                result_path = None
                break
            import traceback
            traceback.print_exc()
            should_retry = True
            result_path = None

        finally:
            if own_browser:
                try:
                    page.close()
                except:
                    pass
                try:
                    context.close()
                except:
                    pass
                try:
                    _browser_ctx.__exit__(None, None, None)
                except:
                    pass

    if own_browser:
        pass  # already cleaned up in finally

    if result_path is None:
        print(f"\n❌ 下载失败，已重试 {max_retries} 次")
        if last_error:
            print(f"最后错误: {last_error}")

    return result_path


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "AI4S背景下的知识创新服务应用模式、平台系统与微服务设计研究"
    zhesheke_download(keyword)
