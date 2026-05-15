#!/usr/bin/env python3
"""
CNKI PDF 下载脚本 - 使用 Camoufox 反检测（同步版）
支持会话持久化和验证码自动重试
"""

import sys
import time
import os
import json
import shutil
from pathlib import Path
from camoufox.sync_api import Camoufox
from camoufox.addons import DefaultAddons

# 导入关键词处理工具
from keyword_processor import sanitize_for_playwright, diagnose_keyword_issue


# CNKI 会话数据保存目录
SESSION_DIR = Path(__file__).parent / "cnki_session"
COOKIES_FILE = SESSION_DIR / "cookies.json"
LOCAL_STORAGE_FILE = SESSION_DIR / "local_storage.json"

# 验证码等待超时时间（秒）
CAPTCHA_WAIT_TIMEOUT = 60  # 1分钟等待用户手动验证（增加到1分钟）
# 重试间隔时间（秒）
RETRY_INTERVAL = 60  # 1分钟后重试
# 最大重试次数
MAX_RETRIES = 2


def is_captcha_page(page) -> bool:
    """
    检测页面是否显示验证码 - 精确版
    只检测真正会阻塞页面的验证码元素，避免误判
    
    Args:
        page: Playwright page 对象
    
    Returns:
        bool: 是否检测到阻塞页面的验证码
    """
    try:
        # 1. 检查 URL 是否包含验证码相关参数（最可靠）
        page_url = page.url.lower()
        if any(x in page_url for x in ['captcha', 'validate', 'verify', 'security']):
            return True
        
        # 2. 检查页面中是否有验证码相关的 iframe（最可靠）
        try:
            captcha_iframes = page.locator(
                "iframe[src*='captcha'], iframe[src*='validate'], iframe[src*='verify'], iframe[src*='yidun'], iframe[src*='geetest']"
            ).count()
            if captcha_iframes > 0:
                return True
        except:
            pass
        
        # 3. 检查特定的验证码交互元素（需要有实际可见的元素）
        captcha_selectors = [
            ".nc_wrapper",           # 阿里云滑动验证容器
            "#nc_1_n1z",             # 阿里云滑动块
            ".geetest_panel",        # 极验验证面板
            ".geetest_wrap",         # 极验容器
            ".yidun_slider",         # 网易滑动验证
            ".yidun_slider儿",        # 网易滑动验证(备选)
            ".yidun_captcha",        # 网易验证码
            "#captcha",              # 验证码元素
            ".captcha-modal",       # 验证码模态框
            ".modal-captcha",       # 验证码模态框(备选)
        ]
        
        for selector in captcha_selectors:
            try:
                elem = page.locator(selector).first
                if elem.count() > 0 and elem.is_visible():
                    # 检查元素是否真正阻塞页面（尺寸大于0）
                    bounding_box = elem.bounding_box()
                    if bounding_box and bounding_box['width'] > 50 and bounding_box['height'] > 30:
                        return True
            except:
                continue
        
        # 4. 检查页面是否有大面积覆盖层（可能是验证码遮罩）
        try:
            overlay = page.locator("div[class*='mask'], div[class*='overlay'], div[class*='cover']").all()
            for elem in overlay:
                if elem.is_visible():
                    bounding_box = elem.bounding_box()
                    # 如果遮罩覆盖了页面大部分区域
                    if bounding_box and bounding_box['width'] > 500 and bounding_box['height'] > 400:
                        # 检查是否是验证码相关的遮罩
                        style = elem.get_attribute("style") or ""
                        if "z-index" in style or "position" in style:
                            return True
        except:
            pass
        
        # 5. 保守检测：不依赖文本内容，避免误判
        # 页面上的 "请完成安全验证" 文字可能只是提示，不是真正的阻塞
        
        return False
        
    except Exception as e:
        print(f"   检测验证码时出错: {e}")
        return False


def wait_for_captcha_completion(page, timeout: int = CAPTCHA_WAIT_TIMEOUT) -> bool:
    """
    等待用户手动完成验证码验证 - 人工确认版
    检测到验证码后，等待用户手动完成并按 Y 确认
    同时保留 60 秒超时作为安全机制
    
    Args:
        page: Playwright page 对象
        timeout: 最大等待时间（秒）
    
    Returns:
        bool: 用户确认或验证码已消失
    """
    # 先检查是否真的存在验证码
    if not is_captcha_page(page):
        print("   页面无验证码")
        return True
    
    print(f"\n⚠️  检测到验证码")
    print(f"   请在浏览器中完成验证")
    print(f"   ========================================")
    print(f"   手动完成后，在此处输入 Y 并回车继续...")
    print(f"   或者等待 {timeout} 秒自动超时")
    print(f"   ========================================")
    
    start_time = time.time()
    check_interval = 2  # 每2秒检查一次验证码是否消失
    
    # 使用线程来同时监听用户输入和验证码状态
    import threading
    user_confirmed = threading.Event()
    
    def listen_for_input():
        try:
            user_input = input("   >> ").strip().upper()
            if user_input == 'Y' or user_input == 'YES' or user_input == '':
                user_confirmed.set()
        except:
            pass
    
    # 启动输入监听线程
    input_thread = threading.Thread(target=listen_for_input, daemon=True)
    input_thread.start()
    
    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed
        
        # 检查用户是否确认
        if user_confirmed.is_set():
            print(f"\n✅ 用户确认验证码已完成!")
            time.sleep(2)  # 额外等待确保页面加载完成
            return True
        
        # 实时检测验证码是否消失
        if not is_captcha_page(page):
            print(f"\n✅ 验证码已自动消失! (耗时: {elapsed} 秒)")
            time.sleep(2)  # 额外等待确保页面加载完成
            return True
        
        print(f"   等待验证码完成... {remaining} 秒 remaining...  (输入 Y 确认完成)", end="\r")
        time.sleep(check_interval)
    
    # 超时后再次检查
    if not is_captcha_page(page):
        print(f"\n✅ 验证码已通过!")
        return True
    
    # 超时后也检查用户是否确认
    if user_confirmed.is_set():
        print(f"\n✅ 用户确认验证码已完成!")
        return True
    
    print(f"\n⏰ 验证码等待超时 (已等待 {timeout} 秒)")
    return False


def save_session(context, page):
    """
    保存浏览器会话（cookies 和 localStorage）
    
    Args:
        context: Playwright browser context
        page: Playwright page 对象
    """
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # 保存 cookies
        cookies = context.cookies()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False)
        print(f"   ✓ Cookies 已保存: {COOKIES_FILE}")
        
        # 保存 localStorage
        try:
            local_storage = page.evaluate("""
                () => {
                    let items = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        items[key] = localStorage.getItem(key);
                    }
                    return items;
                }
            """)
            with open(LOCAL_STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(local_storage, f, ensure_ascii=False)
            print(f"   ✓ LocalStorage 已保存: {LOCAL_STORAGE_FILE}")
        except Exception as e:
            print(f"   ⚠️ LocalStorage 保存失败: {e}")
            
        return True
    except Exception as e:
        print(f"   ❌ 会话保存失败: {e}")
        return False


def load_session(context, page):
    """
    加载保存的浏览器会话
    
    Args:
        context: Playwright browser context
        page: Playwright page 对象
    
    Returns:
        bool: 是否成功加载会话
    """
    try:
        if not COOKIES_FILE.exists():
            print("   没有找到保存的会话")
            return False
        
        # 加载 cookies
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"   ✓ Cookies 已加载")
        
        # 加载 localStorage
        if LOCAL_STORAGE_FILE.exists():
            try:
                with open(LOCAL_STORAGE_FILE, 'r', encoding='utf-8') as f:
                    local_storage = json.load(f)
                page.evaluate(f"""
                    (items) => {{
                        for (let key in items) {{
                            localStorage.setItem(key, items[key]);
                        }}
                    }}
                """, local_storage)
                print(f"   ✓ LocalStorage 已加载")
            except Exception as e:
                print(f"   ⚠️ LocalStorage 加载失败: {e}")
        
        return True
    except Exception as e:
        print(f"   ❌ 会话加载失败: {e}")
        return False


def wait_for_element_or_handle_captcha(page, element_selector: str, timeout: int = 15) -> bool:
    """
    等待目标元素出现，如果未出现则检查并处理验证码
    这是更智能的等待逻辑：优先等待目标元素，而非先检查验证码
    
    Args:
        page: Playwright page 对象
        element_selector: 目标元素的选择器
        timeout: 等待目标元素超时时间（秒）
    
    Returns:
        bool: 目标元素是否出现
    """
    try:
        # 先尝试等待目标元素出现
        element = page.locator(element_selector).first
        element.wait_for(timeout=timeout * 1000, state="visible")
        print(f"   目标元素已出现")
        return True
    except Exception:
        # 目标元素未出现，检查是否有验证码
        if is_captcha_page(page):
            print(f"   目标元素未出现，检测到验证码")
            return wait_for_captcha_completion(page, CAPTCHA_WAIT_TIMEOUT)
        else:
            # 没有验证码但元素也未出现，可能是页面还在加载
            print(f"   目标元素未出现，等待页面加载...")
            time.sleep(3)
            try:
                element = page.locator(element_selector).first
                element.wait_for(timeout=10000, state="visible")
                return True
            except:
                return is_captcha_page(page) and wait_for_captcha_completion(page, CAPTCHA_WAIT_TIMEOUT)


def cnki_download(keyword: str, output_dir: str = None, reuse_session: bool = True) -> str | None:
    """
    从 CNKI 检索并下载 PDF（使用 Camoufox）

    流程：
    1. 搜索 → 可能触发验证码
    2. 验证码 → 等待用户确认（60秒超时）→ 返回 "CAPTCHA_TIMEOUT"
    3. 正常 → 点击结果 → 下载 → 保存会话 → 关闭

    Args:
        keyword: 检索关键词
        output_dir: 自定义输出目录（支持环境变量PDF_OUTPUT_DIR）
        reuse_session: 是否复用已有会话（默认 True）

    Returns:
        str: 下载文件路径
        None: 其他错误
        "CAPTCHA_TIMEOUT": 验证码超时（调用方应重试）
    """
    print(f"检索关键词: {keyword}")
    print(f"会话复用: {'启用' if reuse_session else '禁用'}")

    # 优先使用传入的output_dir，否则尝试环境变量，最后使用默认路径
    if output_dir is None:
        output_dir = os.environ.get('PDF_OUTPUT_DIR', '')
    
    if output_dir:
        target_dir = Path(output_dir)
    else:
        # 默认保存目录（兼容旧版本）
        target_dir = Path(__file__).parent.parent / "temps" / "scholar-pdf" / "cnki"
    
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"保存目录: {target_dir}")

    # 确保会话目录存在
    if reuse_session:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    # 网络重试次数
    max_retries = 3

    with Camoufox(
        headless=True,
        geoip=False,
        humanize=False,
        os="linux",
        exclude_addons=[DefaultAddons.UBO]
    ) as browser:
        context = browser.new_context(
            accept_downloads=True,
            locale="zh-CN"
        )

        page = context.new_page()

        try:
            # ========== 1. 打开 CNKI 首页 ==========
            print("\n[1/7] 打开 CNKI 首页...")
            
            # 多次尝试打开首页（网络不稳定时重试）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    page.goto("https://www.cnki.net/", timeout=60000, wait_until="domcontentloaded")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"   网络超时，{10*(attempt+1)}秒后重试... ({attempt+1}/{max_retries})")
                        time.sleep(10 * (attempt + 1))
                    else:
                        raise e
            
            time.sleep(3)

            # 尝试加载保存的会话
            if reuse_session:
                print("   尝试加载保存的会话...")
                load_session(context, page)
                # 刷新页面让 cookies 生效
                for attempt in range(max_retries):
                    try:
                        page.goto("https://www.cnki.net/", timeout=60000, wait_until="domcontentloaded")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"   网络超时，{10*(attempt+1)}秒后重试... ({attempt+1}/{max_retries})")
                            time.sleep(10 * (attempt + 1))
                        else:
                            raise e
                time.sleep(2)

            # ========== 2. 输入检索词 ==========
            print("[2/7] 定位搜索框并输入关键词...")

            search_box = None
            selectors = [
                "textarea#txt_SearchText",
                "input[name='txt_search']",
                "textarea[placeholder*='检索']",
                "input[placeholder*='检索']"
            ]

            for sel in selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        search_box = elem
                        break
                except:
                    continue

            if search_box is None:
                for elem in page.locator("textarea").all() + page.locator("input[type='text']").all():
                    try:
                        if elem.is_visible():
                            search_box = elem
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
            time.sleep(1)
            print(f"   已输入关键词: {safe_keyword}")

            # ========== 3. 执行检索 ==========
            print("[3/7] 执行检索...")

            search_box.press("Enter")
            time.sleep(3)

            if "cnki.net" in page.url and ("search" not in page.url and "kns" not in page.url):
                print("   Enter 没反应，尝试点击检索按钮...")
                for btn_text in ["检索", "搜索", "Search"]:
                    try:
                        btn = page.locator(f"button:has-text('{btn_text}')").first
                        if btn.count() > 0 and btn.is_visible():
                            btn.click()
                            time.sleep(3)
                            break
                    except:
                        continue

            # ========== 3.5 检测验证码（搜索结果页面）==========
            print("   检查搜索结果...")
            
            # 使用智能等待：先尝试等待搜索结果，如果失败再检查验证码
            result_selectors = [
                "table.result-table-list",
                ".result-table-list",
                "td.name a",
                "a.fz14",
            ]
            
            search_results_found = False
            for selector in result_selectors:
                if wait_for_element_or_handle_captcha(page, selector, timeout=10):
                    search_results_found = True
                    print(f"   搜索结果已加载")
                    break
            
            if not search_results_found:
                # 最后的备选：等待网络空闲
                page.wait_for_load_state("networkidle", timeout=15000)
            
            time.sleep(2)
            
            # 再次检查是否有验证码（可能是结果加载后才出现的）
            if is_captcha_page(page):
                print("   检测到验证码（搜索结果加载后）")
                if not wait_for_captcha_completion(page, CAPTCHA_WAIT_TIMEOUT):
                    print("\n⚠️  验证码超时")
                    return "CAPTCHA_TIMEOUT"

            # ========== 4. 点击第一条结果的题名 ==========
            print("[4/7] 定位并点击第一条结果的题名...")

            # 等待页面稳定（使用更宽松的等待条件）
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as e:
                print(f"   等待 DOM 加载超时: {e}")
            # 额外等待确保搜索结果完全渲染
            time.sleep(3)
            
            # 注意：搜索完成后不保存会话，等下载成功后再保存

            title_link = None
            title_selectors = [
                "a.fz14",
                "td.name a",
                ".result-table-list td a[target='_blank']",
                "table.result-table-list a[target='_blank']",
                ".list-item a",
                ".result-table-list a",
                "a[class*='fz']",
                "td.name > a",
            ]

            for sel in title_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        title_link = elem
                        print(f"   通过选择器找到: {sel}")
                        break
                except Exception as e:
                    print(f"   选择器 {sel} 失败: {e}")
                    continue

            if title_link is None:
                print("   尝试遍历所有链接...")
                all_links = page.locator("a").all()
                print(f"   页面共有 {len(all_links)} 个链接")
                for link in all_links:
                    try:
                        if not link.is_visible():
                            continue
                        text = link.inner_text()
                        href = link.get_attribute("href") or ""
                        if text and len(text.strip()) > 5 and "pdf" not in text.lower() and "下载" not in text and "kns.cnki.net" in href:
                            title_link = link
                            print(f"   找到候选链接: {text[:40]}...")
                            break
                    except Exception as e:
                        continue

            if title_link is None:
                page.screenshot(path=str(target_dir / "debug_search.png"))
                print(f"   调试截图: {target_dir / 'debug_search.png'}")
                raise Exception("无法找到结果链接")

            title_text = title_link.inner_text().strip()
            print(f"   找到题名: {title_text[:60]}...")

            # 获取链接的 href 属性（备用）
            title_href = title_link.get_attribute("href")
            print(f"   获取到链接: {title_href[:60]}..." if title_href else "   无法获取链接")

            # 方法1: 优先尝试点击（使用 dispatch_event 避免元素被遮挡的问题）
            detail_page = None
            try:
                print("   尝试点击链接...")
                initial_pages = len(context.pages)

                with context.expect_page(timeout=15000) as page_info:
                    # 使用 dispatch_event 触发 JavaScript 点击事件
                    title_link.dispatch_event("click")

                detail_page = page_info.value
                print("   点击成功，新页面已打开")
            except Exception as click_error:
                print(f"   点击失败: {click_error}")
                
                # 方法2: 如果点击失败，使用直接导航方案
                if title_href and "kns.cnki.net" in title_href:
                    print("   尝试直接导航到详情页...")
                    try:
                        detail_page = context.new_page()
                        detail_page.goto(title_href, timeout=60000, wait_until="domcontentloaded")
                        time.sleep(3)
                        print("   直接导航成功")
                    except nav_error:
                        print(f"   直接导航也失败: {nav_error}")
                        raise Exception(f"点击和直接导航都失败: {click_error}, {nav_error}")
                else:
                    raise click_error

            if detail_page is None:
                raise Exception("无法打开详情页")
            detail_page.bring_to_front()
            time.sleep(3)

            # 使用智能等待：先尝试等待详情页内容出现
            detail_selectors = [
                "a:has-text('PDF下载')",
                "a:has-text('PDF')",
                "button:has-text('PDF下载')",
                "button:has-text('PDF')",
                ".btn-download",
                ".pdf a",
                "a[href*='pdf']",
                ".detail",
                ".article",
                "h1",
                "h2",
            ]

            detail_loaded = False
            for selector in detail_selectors:
                try:
                    elem = detail_page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        detail_loaded = True
                        print(f"   详情页已加载 (找到: {selector})")
                        break
                except:
                    continue

            if not detail_loaded:
                # 等待页面 DOM 加载完成
                try:
                    detail_page.wait_for_load_state("domcontentloaded", timeout=10000)
                except:
                    pass
                time.sleep(2)

                # 再次尝试检测
                for selector in detail_selectors:
                    try:
                        elem = detail_page.locator(selector).first
                        if elem.count() > 0 and elem.is_visible():
                            detail_loaded = True
                            print(f"   详情页已加载 (找到: {selector})")
                            break
                    except:
                        continue
            
            # 详情页加载后再次检查验证码
            if is_captcha_page(detail_page):
                print("   检测到验证码（详情页加载后）")
                if not wait_for_captcha_completion(detail_page, CAPTCHA_WAIT_TIMEOUT):
                    print("\n⚠️  验证码超时")
                    return "CAPTCHA_TIMEOUT"

            # ========== 5. 点击 PDF 下载按钮 ==========
            print("[5/7] 定位 PDF 下载按钮...")
            time.sleep(2)

            pdf_button = None
            pdf_selectors = [
                'a:has-text("PDF下载")',
                'a:has-text("PDF")',
                'button:has-text("PDF下载")',
                'button:has-text("PDF")',
            ]

            for sel in pdf_selectors:
                try:
                    elem = detail_page.locator(sel).first
                    if elem.count() > 0 and elem.is_visible():
                        pdf_button = elem
                        break
                except:
                    continue

            if pdf_button is None:
                for link in detail_page.locator("a").all() + detail_page.locator("button").all():
                    try:
                        if not link.is_visible():
                            continue
                        text = link.inner_text()
                        if text and "PDF" in text:
                            pdf_button = link
                            break
                    except:
                        continue

            if pdf_button is None:
                detail_page.screenshot(path=str(target_dir / "debug_detail.png"))
                print(f"   已保存调试截图: {target_dir / 'debug_detail.png'}")
                raise Exception("无法找到 PDF 下载按钮")

            print("[6/7] 点击下载按钮...")

            pdf_href = pdf_button.get_attribute("href")
            print(f"   获取到 href: {pdf_href[:60]}..." if pdf_href else "   无 href")

            download_path = None
            
            # 记录点击前的页面数量
            initial_page_count = len(context.pages)
            
            # 尝试监听下载事件
            try:
                with detail_page.expect_download(timeout=60000) as download_info:
                    # 点击下载按钮
                    pdf_button.click()
                    
                    # 等待可能的弹窗或新页面
                    time.sleep(2)
                    
                    # 检查是否有新页面打开（弹窗或登录页面）
                    current_page_count = len(context.pages)
                    if current_page_count > initial_page_count:
                        print(f"   检测到新页面打开 ({current_page_count - initial_page_count} 个)")
                        # 切换到最新的页面
                        new_page = context.pages[-1]
                        new_page.bring_to_front()
                        time.sleep(2)
                        
                        # 检查新页面是否有登录提示
                        has_login = new_page.locator("text=登录").count() > 0
                        if has_login:
                            print("   新页面检测到登录提示，尝试 IP 登录...")
                            # 尝试多种 IP 登录方式
                            ip_login_selectors = [
                                "text=IP登录",
                                "text=IP 登录",
                                "button:has-text('IP登录')",
                                "button:has-text('IP 登录')",
                                ".ecp_IPLogin",
                                "a:has-text('IP登录')",
                            ]
                            for selector in ip_login_selectors:
                                try:
                                    ip_login = new_page.locator(selector).first
                                    if ip_login.count() > 0 and ip_login.is_visible():
                                        ip_login.click()
                                        print("   已点击 IP 登录按钮")
                                        time.sleep(5)
                                        break
                                except:
                                    continue
                            
                            # IP 登录后，等待下载开始或关闭弹窗
                            time.sleep(3)
                            
                            # 如果弹窗关闭了，尝试切回详情页继续监听下载
                            if len(context.pages) < current_page_count:
                                detail_page.bring_to_front()
                    else:
                        # 没有新页面，检查当前页面是否有登录弹窗/模态框
                        has_login = detail_page.locator("text=登录").count() > 0
                        if has_login:
                            print("   检测到登录提示，尝试 IP 登录...")
                            ip_login_selectors = [
                                "text=IP登录",
                                "text=IP 登录",
                                "button:has-text('IP登录')",
                                "button:has-text('IP 登录')",
                                ".ecp_IPLogin",
                                "a:has-text('IP登录')",
                            ]
                            for selector in ip_login_selectors:
                                try:
                                    ip_login = detail_page.locator(selector).first
                                    if ip_login.count() > 0 and ip_login.is_visible():
                                        ip_login.click()
                                        print("   已点击 IP 登录按钮")
                                        time.sleep(5)
                                        break
                                except:
                                    continue
                
                download = download_info.value
                suggested_filename = download.suggested_filename
                save_path = target_dir / suggested_filename
                download.save_as(str(save_path))
                download_path = save_path

            except Exception as e:
                print(f"   下载等待超时: {e}")
                print("   尝试使用 href 直接下载...")
                
                # 备选方案：使用 href URL 直接下载
                if pdf_href and pdf_href.startswith("http"):
                    try:
                        import requests
                        # 获取 cookies 用于认证
                        cookies = context.cookies()
                        cookie_dict = {c['name']: c['value'] for c in cookies}
                        
                        # 发送请求下载 PDF
                        response = requests.get(pdf_href, cookies=cookie_dict, timeout=60, stream=True)
                        if response.status_code == 200:
                            # 从 Content-Disposition 获取文件名
                            content_disposition = response.headers.get('Content-Disposition', '')
                            if 'filename=' in content_disposition:
                                import urllib.parse
                                filename = urllib.parse.unquote(content_disposition.split('filename=')[1].strip('"'))
                            else:
                                # 使用默认文件名
                                filename = f"{keyword[:20]}.pdf"
                            
                            save_path = target_dir / filename
                            with open(save_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            download_path = save_path
                            print(f"   通过 href 直接下载成功: {filename}")
                        else:
                            print(f"   href 下载失败，状态码: {response.status_code}")
                    except Exception as download_error:
                        print(f"   href 直接下载失败: {download_error}")
                
                if download_path is None:
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
                                download_path = final_path
                                break
                        time.sleep(1)
                        print(f"   等待中... ({i+1}/30)", end="\r")

            if download_path and download_path.exists():
                size_mb = download_path.stat().st_size / 1024 / 1024
                print("\n✅ 下载成功！")
                print(f"文件路径: {download_path}")
                print(f"文件大小: {size_mb:.2f} MB")

                # 保存会话（供下次使用）
                if reuse_session:
                    print("\n保存会话...")
                    save_session(context, page)

                return str(download_path)
            else:
                print("\n⚠️  未检测到下载文件")
                return None

        except Exception as e:
            print(f"\n❌ 执行出错: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path=str(target_dir / "error.png"))
                print(f"   错误截图已保存: {target_dir / 'error.png'}")
            except:
                pass
            return None

        finally:
            print("\n正在关闭浏览器...")


def main():
    """
    处理命令行参数，支持验证码超时重试

    流程：
    1. 搜索 → 可能触发验证码
    2. 验证码超时 → 关闭浏览器 → 等待60秒 → 重试（最多2次）
    3. 其他错误 → 直接结束
    4. 成功 → 结束
    """
    # 解析参数
    reuse_session = True
    output_dir = None

    # 处理可选参数
    for arg in sys.argv[2:]:
        if arg == "--no-session":
            reuse_session = False
        elif arg.startswith("--output="):
            output_dir = arg.split("=", 1)[1]

    # 获取关键词（第一个参数）
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
    else:
        keyword = "数智时代图书馆学本科专业知识体系与人才培养模式探索"

    # 重试计数
    retry_count = 0

    while retry_count <= MAX_RETRIES:
        # 调用下载函数
        result = cnki_download(keyword, output_dir=output_dir, reuse_session=reuse_session)

        # 检查结果
        if result == "CAPTCHA_TIMEOUT":
            # 验证码超时，重试
            retry_count += 1
            if retry_count <= MAX_RETRIES:
                print(f"\n🔄 验证码超时，第 {retry_count} 次重试...")
                print(f"   等待 {RETRY_INTERVAL} 秒后重新启动浏览器...")
                time.sleep(RETRY_INTERVAL)
            else:
                print("\n❌ 达到最大重试次数，下载失败")
                return
        elif result:
            # 下载成功
            print(f"\n✅ 下载完成: {result}")
            return
        else:
            # 其他错误，不重试
            print("\n❌ 下载失败（非验证码原因）")
            return

    print("\n❌ 所有重试次数已用完，下载失败")


if __name__ == "__main__":
    main()
