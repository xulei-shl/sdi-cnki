#!/usr/bin/env python3
"""
企业微信消息推送工具

支持的消息类型：
- text: 文本消息
- markdown: Markdown消息
- markdown_v2: Markdown v2消息
- image: 图片消息
- news: 图文消息
- file: 文件消息
- voice: 语音消息
- template_card: 模板卡片消息
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

try:
    import requests
except ImportError:
    print("请安装 requests 库: pip install requests")
    sys.exit(1)

# 加载 .env 文件
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # 如果没有安装 dotenv，尝试手动加载
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


class WeComPusher:
    """企业微信消息推送类"""

    def __init__(self, webhook_url: Optional[str] = None, webhook_key: Optional[str] = None):
        """
        初始化推送器

        Args:
            webhook_url: 完整的 Webhook URL
            webhook_key: 仅 Webhook Key，会自动拼接完整 URL
        """
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

        if webhook_url:
            self.webhook_url = webhook_url
        elif webhook_key:
            self.webhook_url = f"{self.base_url}?key={webhook_key}"
        else:
            # 尝试从环境变量读取
            webhook_url = os.getenv("WEBHOOK_URL")
            if webhook_url:
                self.webhook_url = webhook_url
            else:
                key = os.getenv("WEBHOOK_KEY")
                base_url = os.getenv("WEBHOOK_BASE_URL", self.base_url)
                if key:
                    self.webhook_url = f"{base_url}?key={key}"
                else:
                    raise ValueError(
                        "请提供 Webhook URL 或 Key，"
                        "可通过参数传递或设置环境变量 WEBHOOK_URL / WEBHOOK_KEY"
                    )

    def send(self, message: Dict) -> bool:
        """
        发送消息

        Args:
            message: 消息体字典

        Returns:
            bool: 是否发送成功
        """
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(self.webhook_url, headers=headers, json=message, timeout=10)
            result = response.json()

            if result.get("errcode") == 0:
                print("消息发送成功")
                return True
            else:
                print(f"消息发送失败: {result.get('errmsg')} (errcode: {result.get('errcode')})")
                return False
        except Exception as e:
            print(f"发送请求异常: {e}")
            return False

    def send_text(
        self,
        content: str,
        mentioned_list: Optional[list] = None,
        mentioned_mobile_list: Optional[list] = None,
    ) -> bool:
        """
        发送文本消息

        Args:
            content: 文本内容，最长不超过2048个字节
            mentioned_list: userid列表，提醒指定成员
            mentioned_mobile_list: 手机号列表，提醒指定成员
        """
        message = {
            "msgtype": "text",
            "text": {"content": content},
        }

        if mentioned_list:
            message["text"]["mentioned_list"] = mentioned_list
        if mentioned_mobile_list:
            message["text"]["mentioned_mobile_list"] = mentioned_mobile_list

        return self.send(message)

    def send_markdown(self, content: str) -> bool:
        """
        发送 Markdown 消息

        Args:
            content: Markdown内容，最长不超过4096个字节
        """
        message = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        return self.send(message)

    def send_markdown_v2(self, content: str) -> bool:
        """
        发送 Markdown v2 消息

        Args:
            content: Markdown v2内容，最长不超过4096个字节
        """
        message = {
            "msgtype": "markdown_v2",
            "markdown_v2": {"content": content},
        }
        return self.send(message)

    def send_image(self, image_path: str) -> bool:
        """
        发送图片消息

        Args:
            image_path: 图片文件路径，支持JPG/PNG，最大2M
        """
        path = Path(image_path)
        if not path.exists():
            print(f"图片文件不存在: {image_path}")
            return False

        # 读取图片并计算MD5
        with open(path, "rb") as f:
            file_data = f.read()

        if len(file_data) > 2 * 1024 * 1024:
            print("图片大小不能超过2M")
            return False

        md5_hash = hashlib.md5(file_data).hexdigest()
        base64_data = base64.b64encode(file_data).decode("utf-8")

        message = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": md5_hash,
            },
        }
        return self.send(message)

    def send_news(
        self,
        title: str,
        url: str,
        description: Optional[str] = None,
        picurl: Optional[str] = None,
    ) -> bool:
        """
        发送图文消息

        Args:
            title: 标题，不超过128个字节
            url: 点击后跳转的链接
            description: 描述，不超过512个字节
            picurl: 图片链接
        """
        article = {"title": title, "url": url}
        if description:
            article["description"] = description
        if picurl:
            article["picurl"] = picurl

        message = {
            "msgtype": "news",
            "news": {"articles": [article]},
        }
        return self.send(message)

    def send_file(self, media_id: str) -> bool:
        """
        发送文件消息

        Args:
            media_id: 文件ID，通过上传接口获取
        """
        message = {
            "msgtype": "file",
            "file": {"media_id": media_id},
        }
        return self.send(message)

    def send_voice(self, media_id: str) -> bool:
        """
        发送语音消息

        Args:
            media_id: 语音文件ID，通过上传接口获取
        """
        message = {
            "msgtype": "voice",
            "voice": {"media_id": media_id},
        }
        return self.send(message)

    def upload_media(self, file_path: str, media_type: str = "file") -> Optional[str]:
        """
        上传文件/语音

        Args:
            file_path: 文件路径
            media_type: 文件类型，file 或 voice

        Returns:
            media_id: 上传成功返回media_id，失败返回None
        """
        path = Path(file_path)
        if not path.exists():
            print(f"文件不存在: {file_path}")
            return None

        # 从webhook_url中提取key
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.webhook_url)
        query_params = parse_qs(parsed.query)
        key = query_params.get("key", [None])[0]
        if not key:
            print("无法从webhook_url中提取key")
            return None

        upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type={media_type}"

        try:
            with open(path, "rb") as f:
                files = {"media": (path.name, f, "application/octet-stream")}
                response = requests.post(upload_url, files=files, timeout=30)
                result = response.json()

                if result.get("errcode") == 0:
                    print(f"文件上传成功: {path.name}")
                    return result.get("media_id")
                else:
                    print(f"文件上传失败: {result.get('errmsg')}")
                    return None
        except Exception as e:
            print(f"上传文件异常: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description="企业微信消息推送工具", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--url", help="完整的 Webhook URL")
    parser.add_argument("--key", help="Webhook Key")
    parser.add_argument("--content", "-c", help="消息内容")

    subparsers = parser.add_subparsers(dest="msgtype", help="消息类型")

    # 文本消息
    text_parser = subparsers.add_parser("text", help="发送文本消息")
    text_parser.add_argument("content", help="文本内容")
    text_parser.add_argument("--mentioned-list", help="提醒的userid列表，逗号分隔")
    text_parser.add_argument("--mentioned-mobile-list", help="提醒的手机号列表，逗号分隔")

    # Markdown消息
    md_parser = subparsers.add_parser("markdown", help="发送Markdown消息")
    md_parser.add_argument("content", help="Markdown内容")

    # Markdown v2消息
    md2_parser = subparsers.add_parser("markdown_v2", help="发送Markdown v2消息")
    md2_parser.add_argument("content", help="Markdown v2内容")

    # 图片消息
    img_parser = subparsers.add_parser("image", help="发送图片消息")
    img_parser.add_argument("path", help="图片文件路径")

    # 图文消息
    news_parser = subparsers.add_parser("news", help="发送图文消息")
    news_parser.add_argument("title", help="标题")
    news_parser.add_argument("url", help="跳转链接")
    news_parser.add_argument("--description", help="描述")
    news_parser.add_argument("--picurl", help="图片链接")

    # 文件消息
    file_parser = subparsers.add_parser("file", help="发送文件消息")
    file_parser.add_argument("path", help="文件路径")

    # 语音消息
    voice_parser = subparsers.add_parser("voice", help="发送语音消息")
    voice_parser.add_argument("path", help="语音文件路径")

    args = parser.parse_args()

    try:
        pusher = WeComPusher(webhook_url=args.url, webhook_key=args.key)
    except ValueError as e:
        print(f"错误: {e}")
        print("\n请设置环境变量或使用 --url/--key 参数")
        print(f"\n示例: {sys.argv[0]} text 'hello world' --key YOUR_KEY")
        return 1

    # 直接使用 --content 参数发送文本消息（兼容旧版本）
    if args.content and not args.msgtype:
        return 0 if pusher.send_text(args.content) else 1

    # 根据消息类型发送
    if args.msgtype == "text":
        mentioned_list = args.mentioned_list.split(",") if args.mentioned_list else None
        mentioned_mobile_list = args.mentioned_mobile_list.split(",") if args.mentioned_mobile_list else None
        return 0 if pusher.send_text(args.content, mentioned_list, mentioned_mobile_list) else 1

    elif args.msgtype == "markdown":
        return 0 if pusher.send_markdown(args.content) else 1

    elif args.msgtype == "markdown_v2":
        return 0 if pusher.send_markdown_v2(args.content) else 1

    elif args.msgtype == "image":
        return 0 if pusher.send_image(args.path) else 1

    elif args.msgtype == "news":
        return 0 if pusher.send_news(args.title, args.url, args.description, args.picurl) else 1

    elif args.msgtype == "file":
        media_id = pusher.upload_media(args.path, "file")
        if media_id:
            return 0 if pusher.send_file(media_id) else 1
        return 1

    elif args.msgtype == "voice":
        media_id = pusher.upload_media(args.path, "voice")
        if media_id:
            return 0 if pusher.send_voice(media_id) else 1
        return 1

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
