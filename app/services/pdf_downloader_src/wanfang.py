#!/usr/bin/env python3
"""
万方 PDF 下载脚本 - 原样复刻自 docs/pdf-download/wanfang_pdf_download.py
改动：支持外部浏览器注入（page 参数），退出条件化清理
"""

import sys
import time
import os
import shutil
from pathlib import Path

from .keyword_processor import sanitize_for_playwright, diagnose_keyword_issue


def wanfang_download(keyword: str, output_dir: str = None, page=None):
    """从万方检索并下载 PDF（使用 Camoufox）
    
    Args:
        keyword: 检索关键词
        output_dir: 自定义输出目录
        page: 外部浏览器页面（None 时自建 Camoufox）
    
    Returns:
        下载文件的路径，失败返回 None
    """
    print(f"检索关键词: {keyword}")
    print(f"关键词长度: {len(keyword)}")

    if output_dir is None:
        output_dir = os.environ.get('PDF_OUTPUT_DIR', '')

    if output_dir:
        target_dir = Path(output_dir)
    else:
        target_dir = Path.home() / ".cache" / "scholar-pdf" / "wanfang"

    target_dir.mkdir(parents=True, exist_ok=True)

    own_browser = page is None
    result_path = None

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
        # ========== 1. 打开万方首页 ==========
        print("\n[1/7] 打开万方首页...")
        page.goto("https://www.wanfangdata.com.cn/", timeout=30000, wait_until="domcontentloaded")
        time.sleep(2.5)

        # ========== 2. 输入检索词 ==========
        print("[2/7] 定位搜索框并输入关键词...")

        search_box = None
        search_selectors = [
            "#search-input",
            "input#search-input",
            "input[placeholder*='在']",
            "input[placeholder*='检索']",
            "textarea#search-input",
            "input[type='text'][class*='search']"
        ]

        for sel in search_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    search_box = elem
                    break
            except:
                continue

        if search_box is None:
            try:
                elem = page.get_by_role("textbox").first
                if elem.count() > 0 and elem.is_visible():
                    search_box = elem
            except:
                pass

        if search_box is None:
            for elem in page.locator("input[type='text']").all() + page.locator("textarea").all():
                try:
                    if elem.is_visible():
                        search_box = elem
                        break
                except:
                    continue

        if search_box is None:
            raise Exception("无法找到搜索框")

        safe_keyword = sanitize_for_playwright(keyword)
        print(f"   原始关键词: '{keyword}'")
        print(f"   处理后关键词: '{safe_keyword}'")

        diagnosis = diagnose_keyword_issue(keyword)
        if diagnosis['issues']:
            print(f"   ⚠️  关键词包含特殊字符: {diagnosis['issues']}")

        search_box.fill(safe_keyword)
        time.sleep(1)
        actual_value = search_box.input_value()
        print(f"   搜索框实际内容: '{actual_value}'")
        print(f"   已输入关键词: {safe_keyword}")

        # ========== 3. 执行检索 ==========
        print("[3/7] 执行检索...")

        search_button = None
        button_selectors = [
            "button:has-text('搜论文')",
            "button:has-text('搜索')",
            "button:has-text('检索')",
            "[class*='search'] button",
            ".search-btn"
        ]

        for sel in button_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    search_button = elem
                    break
            except:
                continue

        if search_button:
            try:
                search_button.click(timeout=5000)
            except Exception as click_err:
                print(f"   点击按钮失败，尝试按 Enter 键: {click_err}")
                search_box.press("Enter")
        else:
            search_box.press("Enter")

        print("   等待检索结果...")
        time.sleep(8)

        # ========== 4. 处理检索结果 ==========
        print("[4/7] 处理检索结果...")

        no_result_tip = page.locator("text=没有检索到数据").count() > 0
        if no_result_tip:
            raise Exception("检索无结果：请检查输入的内容是否正确")

        results = None
        result_selectors = [
            ".search-result-item",
            "[class*='result']",
            ".list-item",
            "div[class*='item']"
        ]

        for sel in result_selectors:
            try:
                elem = page.locator(sel)
                if elem.count() > 0:
                    results = elem
                    break
            except:
                continue

        if results is None or results.count() == 0:
            no_result_tip = page.locator("text=没有检索到数据").count() > 0
            no_result_alt = page.locator("text=温馨提示").count() > 0
            if no_result_tip or no_result_alt:
                raise Exception("检索无结果：请检查输入的内容是否正确")

            print("   未找到结果，尝试点击展开更多...")
            expand_button = None
            expand_selectors = [
                "text=展开更多", "a:has-text('展开更多')",
                "button:has-text('展开更多')", "div:has-text('展')"
            ]
            for sel in expand_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        expand_button = elem
                        break
                except:
                    continue
            if expand_button:
                expand_button.click()
                time.sleep(3)

        for sel in result_selectors:
            try:
                elem = page.locator(sel)
                if elem.count() > 0:
                    results = elem
                    break
            except:
                continue

        if results is None or results.count() == 0:
            no_result_tip = page.locator("text=没有检索到数据").count() > 0
            no_result_alt = page.locator("text=温馨提示").count() > 0
            if no_result_tip or no_result_alt:
                raise Exception("检索无结果：请检查输入的内容是否正确")
            raise Exception("未找到检索结果")

        print(f"   找到 {results.count()} 条结果")

        # ========== 5. 点击下载按钮 ==========
        print("[5/7] 定位并点击第一条结果的下载按钮...")

        pdf_button = None
        pdf_selectors = [
            ".button-list .wf-list-button:has-text('下载')",
            ".button-area .wf-list-button:has-text('下载')",
            "div.wf-list-button:has-text('下载')"
        ]

        for sel in pdf_selectors:
            try:
                for elem in page.locator(sel).all():
                    if not elem.is_visible():
                        continue
                    text = elem.inner_text().strip()
                    if text and "下载" in text:
                        pdf_button = elem
                        break
                if pdf_button:
                    break
            except:
                continue

        if pdf_button is None:
            for link in page.locator("div.wf-list-button").all():
                try:
                    if not link.is_visible():
                        continue
                    text = link.inner_text()
                    if text and "下载" in text and len(text.strip()) < 20:
                        pdf_button = link
                        break
                except:
                    continue

        if pdf_button is None:
            all_buttons = page.locator("div.wf-list-button").all()
            button_texts = []
            for btn in all_buttons:
                try:
                    if btn.is_visible():
                        text = btn.inner_text().strip()
                        if text:
                            button_texts.append(text)
                except:
                    pass
            print(f"   可用按钮: {button_texts}")
            print("\n⚠️ 该文献没有 PDF 下载")
            result_path = None
            return result_path

        print("[6/7] 点击下载按钮...")

        with page.context.expect_page(timeout=30000) as new_page_info:
            pdf_button.click()

        download_page = new_page_info.value
        download_page.wait_for_load_state("domcontentloaded")
        print("   已打开下载页面（新tab）")
        time.sleep(3)

        # ========== 7. 点击"点击此处"链接 ==========
        print("[7/7] 在下载页面点击'点击此处'链接...")
        print("   等待页面加载 (10秒)...")
        time.sleep(10)

        click_here_link = None
        click_here_selectors = [
            "a#doDownload", "a[id='doDownload']",
            "a:has(#doDownload)", "a:has-text('点击此处')", "#doDownload"
        ]

        for sel in click_here_selectors:
            try:
                elem = download_page.locator(sel).first
                if elem.count() > 0:
                    if elem.is_visible():
                        click_here_link = elem
                        print(f"   找到链接: {sel}")
                        break
                    else:
                        print(f"   找到元素但不可见: {sel}")
            except Exception as e:
                print(f"   选择器 {sel} 错误: {e}")
                continue

        if click_here_link is None:
            print("   等待更长时间后重试...")
            time.sleep(5)
            for sel in click_here_selectors:
                try:
                    elem = download_page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        click_here_link = elem
                        print(f"   找到链接: {sel}")
                        break
                except:
                    continue

        if click_here_link is None:
            print("   页面标题:", download_page.title())
            print("   错误: 未能找到'点击此处'链接")

        try:
            with download_page.expect_download(timeout=60000) as download_info:
                if click_here_link:
                    print("   找到'点击此处'链接，点击...")
                    click_here_link.click()
                    time.sleep(3)
                else:
                    print("   未找到'点击此处'链接，尝试其他方式...")
                    time.sleep(5)

            download = download_info.value
            suggested_filename = download.suggested_filename
            save_path = target_dir / suggested_filename
            download.save_as(str(save_path))
            result_path = str(save_path)

        except Exception as e:
            print(f"   下载等待超时: {e}")
            print("   尝试检查下载目录...")
            downloads_dir = Path.home() / "Downloads"
            for i in range(30):
                pdf_files = sorted(
                    downloads_dir.glob("*.pdf"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if pdf_files:
                    latest_pdf = pdf_files[0]
                    age = time.time() - latest_pdf.stat().st_mtime
                    if age < 120:
                        final_path = target_dir / latest_pdf.name
                        shutil.move(str(latest_pdf), str(final_path))
                        result_path = str(final_path)
                        break
                time.sleep(1)
                print(f"   等待中... ({i+1}/30)", end="\r")

        if result_path and Path(result_path).exists():
            size_mb = Path(result_path).stat().st_size / 1024 / 1024
            print("\n✅ 下载成功！")
            print(f"文件路径: {result_path}")
        else:
            print("\n⚠️  未检测到下载文件")
            result_path = None

    except Exception as e:
        if "检索无结果" in str(e):
            print(f"\n⚠️ 检索无结果：请检查输入的内容是否正确")
            result_path = None
        else:
            print(f"\n❌ 执行出错: {e}")
            import traceback
            traceback.print_exc()
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

    return result_path


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "AI4S背景下的知识创新服务应用模式、平台系统与微服务设计研究"
    wanfang_download(keyword)
