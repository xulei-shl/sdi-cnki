# Ubuntu 部署说明（生产环境）

## 验证环境

| 项目 | 版本 |
|------|------|
| OS | Ubuntu 24.04 |
| Python | 3.12.3（pyenv 虚拟环境） |
| Node.js | 24.14.1 |
| Playwright | 1.58.0 |
| Camoufox | 0.4.11 |
| Firefox | 146.0.1（Playwright 内置） |

## 更新已有部署（从 Git 拉取新代码后）

根据变更类型选择对应的更新流程：

### 场景 A：仅前端设计 / 前端代码变更

```bash
git pull
npm install
npm run build
systemctl restart sdi-cnki-frontend
systemctl status sdi-cnki-frontend --no-pager
```

> 前端更新**不涉及后端**，无需重启后端服务，无需数据库迁移。

### 场景 B：仅后端代码变更（无数据库变更）

```bash
git pull
systemctl restart sdi-cnki-backend
systemctl status sdi-cnki-backend --no-pager
```

> 纯后端逻辑修改（如新增 API、修改 Worker 逻辑、调整配置等），**只需重启后端**。若新增了 Python 依赖，先执行 `pip install -r requirements.txt`。

### 场景 C：后端代码变更 + 数据库变更

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
systemctl restart sdi-cnki-backend
systemctl status sdi-cnki-backend --no-pager
```

> `alembic upgrade head` 是增量迁移，仅应用尚未运行过的迁移脚本，不会丢失数据。迁移脚本位于 `alembic/versions/` 下。若同时涉及前端变更，可在**重启后端前**追加执行场景 A 的构建步骤。

### 场景 D：全量更新（不确定变更范围）

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
npm install
npm run build
systemctl restart sdi-cnki-backend sdi-cnki-frontend
systemctl status sdi-cnki-backend sdi-cnki-frontend --no-pager
```

> 不确定本次 commit 变更范围时，走全量流程最安全。各步骤均为幂等操作，不会对未变更的模块造成影响。

### 各场景速查表

| 场景 | pip install | alembic upgrade | npm install + build | 重启后端 | 重启前端 |
|------|:-----------:|:---------------:|:-------------------:|:--------:|:--------:|
| A：仅前端 | — | — | ✅ | — | ✅ |
| B：仅后端（无 DB 变更） | 按需 | — | — | ✅ | — |
| C：后端 + DB 变更 | ✅ | ✅ | 按需 | ✅ | 按需 |
| D：全量更新 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 重启与运行中任务恢复（重要）

> 后端 4 个 worker（cnki/llm/download/export）与 uvicorn **同进程**运行（`auto_start_workers`）。
> 任何后端重启都会**中断正在执行的任务**：队列行停留在 `running`、任务实例停留在
> `downloading`/`analyzing`。新启动的 worker 只拾取 `pending`/`retrying` 的任务，**不会自动接管**
> 残留行——需等超时回收（下载默认 6 小时，`DOWNLOAD_TIMEOUT_SEC`）才会被标记失败并回退实例。
> 因此**重启前请先检查是否有任务在运行**，重启后按需恢复。

**1. 重启前检查**

```bash
cd /opt/sdi-cnki
python3 -c "
import sqlite3
conn = sqlite3.connect('file:data/cnki_service.db?mode=ro', uri=True)
print('运行中的任务:', conn.execute(\"SELECT id, task_key, started_at FROM task_queue WHERE status='running'\").fetchall())
print('下载中的实例:', conn.execute(\"SELECT id, instance_no, status FROM task_instances WHERE status IN ('downloading','download_queued')\").fetchall())
conn.close()
"
```

有运行中任务时：能等则**等任务完成后再重启**；必须立即重启时数据也安全（每批已落库），
重启后按第 3 步恢复即可。

**2. 重启**

按上方场景 A/B/C/D 执行 `systemctl restart sdi-cnki-backend`（及对应前端步骤）。

**3. 重启后恢复被中断的任务**

以下以下载任务为例（其他队列同理，替换 `download_` 前缀）。先查出残留的队列行 id：

```bash
cd /opt/sdi-cnki
python3 -c "
import sqlite3
conn = sqlite3.connect('file:data/cnki_service.db?mode=ro', uri=True)
print(conn.execute(\"SELECT id, status, task_key FROM task_queue WHERE status='running'\").fetchall())
conn.close()
"
```

- **方式一：自动续跑（推荐）**——把残留 `running` 行重置为 `pending`，worker 会在下一个轮询
  周期（≤5 秒）自动拾取并**断点续传**恢复：

```bash
cd /opt/sdi-cnki
python3 -c "
import asyncio
from app.database import async_session_factory
from app.task_queue.crud import TaskQueueService
async def main():
    async with async_session_factory() as db:
        await TaskQueueService(db).retry_failed(<队列行 id>)
        print('已重置为 pending，worker 将自动续跑')
asyncio.run(main())
"
```

  > 断点续传语义：已下载成功（`completed`）的记录自动跳过；已标记失败（`failed`）的记录
  > **不会由批量任务重试**（避免重跑先卡在失败记录上），可在结果页表格行级点“下载”按钮单独重试。

- **方式二：手动重新触发**——把残留行标记失败并回退实例到审核态，由用户在页面重新点“下载”：

```bash
cd /opt/sdi-cnki
python3 -c "
import asyncio
from sqlalchemy import select
from app.database import async_session_factory
from app.models.task_queue import TaskQueueItem
from app.models.task_instance import TaskInstance
async def main():
    async with async_session_factory() as db:
        row = (await db.execute(select(TaskQueueItem).where(TaskQueueItem.id == <队列行 id>))).scalar_one()
        row.status = 'failed'
        row.error_message = '手动恢复：服务重启中断，请重新触发'
        inst_no = (row.task_key or '').removeprefix('download_')
        inst = (await db.execute(select(TaskInstance).where(TaskInstance.instance_no == inst_no))).scalar_one_or_none()
        if inst and inst.status in ('downloading', 'download_queued'):
            inst.status = 'analyzing_completed'
        await db.commit()
        print('已恢复为可重新触发状态')
asyncio.run(main())
"
```

**4. 恢复后验证**

```bash
curl -s http://localhost:8456/api/v1/health     # 预期 {"status":"ok"}
journalctl -u sdi-cnki-backend -n 30 --no-pager | grep 'Download progress'   # 续跑后有进度事件
```

> 提示：结果页“下载进度”条刷新后会自动从数据库恢复真实累计进度（成功/失败/总计），
> 无需等待第一条 SSE 事件；中断期间已下载的记录不会重复下载。

## 前置检查

```bash
# 确认所需端口可用
ss -tlnp | grep -E '(:8456|:8848)' && echo "⚠️ 端口被占用" || echo "✅ 端口可用"
```

若 8456 被占用，需同步修改以下文件中的端口号：

| 文件 | 字段 |
|------|------|
| `vite.config.ts` | `server.proxy./api.target` |
| `run.py` | `uvicorn.run(port=...)` |
| systemd service 文件 | `ExecStart` 中的 `--port` |

## 安装步骤

```bash
# 1. Python 依赖（使用项目对应的 Python 解释器）
pip install -r requirements.txt

# 2. Playwright Firefox（Camoufox 底层使用 Firefox，非 Chromium）
playwright install firefox
playwright install firefox --with-deps   # 首次安装系统共享库

# 3. 验证浏览器可启动
python -c "from camoufox.sync_api import NewBrowser; print('camoufox OK')"

# 4. 前端依赖 & 构建
npm install
npm run build

# 5. 确认数据目录
mkdir -p data

# 6. 初始化数据库（首次启动自动创建表 & 默认管理员）
python -c "
import asyncio
from app.database import init_db, engine
async def s():
    await init_db()
    print('DB ready')
    await engine.dispose()
asyncio.run(s())
"

# 默认管理员账号：admin / admin123（由 init_db() 自动创建，仅空库时执行一次）
```

## 防火墙

```bash
ufw --force enable
ufw allow 8456/tcp comment 'SDI-CNKI Backend API'
ufw allow 8848/tcp comment 'SDI-CNKI Frontend'
ufw status verbose
```

## systemd 服务（生产自启动）

### 1. 后端服务 `/etc/systemd/system/sdi-cnki-backend.service`

```ini
[Unit]
Description=SDI-CNKI Backend (FastAPI + Workers)
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/sdi-cnki
ExecStart=/path/to/python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8456
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/path/to/python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin

[Install]
WantedBy=multi-user.target
```

> `ExecStart` 中的 `python3.12` 路径请替换为实际 Python 解释器路径（可通过 `which python3.12` 查看）。  
> `auto_start_workers: true`（默认）使 4 个 Worker（cnki/llm/download/export）随 uvicorn 进程内嵌自动运行。

### 2. 前端服务 `/etc/systemd/system/sdi-cnki-frontend.service`

```ini
[Unit]
Description=SDI-CNKI Frontend (Vite)
After=network.target sdi-cnki-backend.service
BindsTo=sdi-cnki-backend.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/sdi-cnki
ExecStart=/usr/local/bin/npx vite --port 8848 --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin

[Install]
WantedBy=multi-user.target
```

> 前端自动反向代理 `/api` 请求到 `http://localhost:8456`，由 `vite.config.ts` 配置。

### 3. 启用并启动

```bash
cp sdi-cnki-backend.service sdi-cnki-frontend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sdi-cnki-backend sdi-cnki-frontend
systemctl status sdi-cnki-backend sdi-cnki-frontend --no-pager
```

### 4. 验证

```bash
# 后端健康检查
curl -s http://localhost:8456/api/v1/health
# 预期输出: {"status":"ok"}

# 前端可达性
curl -s -o /dev/null -w "%{http_code}" http://localhost:8848/
# 预期输出: 200

# 日志查看
journalctl -u sdi-cnki-backend -n 50 --no-pager
journalctl -u sdi-cnki-frontend -n 50 --no-pager
```

## 服务端口说明

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| 后端 API | **8456** | 避让系统上可能运行的 chromadb（8000）等服务 |
| 前端 UI | **8848** | Vite 开发服务器，内置 `/api` 反代至后端 8456 |
| API 文档 | `{host}:8456/docs` | Swagger UI |
| 管理后台 | `http://{host}:8848` | 默认账号 `admin` / `admin123` |

> 若部署在远程服务器，请确保防火墙已放行上述端口。

## 与现有部署手册的关键差异

> 对照 `docs/deploy/部署运维手册.md`，Ubuntu 实测需要调整以下事项：

| 手册中原写法 | Ubuntu 实测需改为 | 原因 |
|---|---|---|
| `playwright install chromium` | `playwright install firefox` | Camoufox 基于 Firefox |
| `playwright install chromium --with-deps` | `playwright install firefox --with-deps` | 同上 |
| 后端端口 8000 | **8456** | 避免与常见服务端口冲突 |

## CNKI 搜索测试结果

2026-05-18 在 headless 模式下对 `app/services/cnki/` 全套功能进行验证，**7/7 全部通过**：

| 参数 | 检索结果数 | 导出 | 耗时 |
|---|---|---|---|
| 基础搜索「新青年」 | 9,742 | 10 | 17s |
| 核心期刊 `core_only` | 2,812 | 10 | 16s |
| 年份范围 2024–2025 | 1,197 | 10 | 18s |
| 时间范围 `year` | 537 | 10 | 19s |
| 同义词扩展 `synonym_extend` | 9,742 | 10 | 17s |
| 起始年份 2024 | 1,296 | 10 | 16s |
| 截止年份 2023 | 8,440 | 10 | 17s |

覆盖模块：`browser.py`（Camoufox 启动 / Cookie 持久化 / headless）、`interactor.py`（高级检索表单 / 翻页 / 勾选 / Excel+TXT 导出 / 合并）。

## PDF 下载测试结果

2026-05-18 在 headless 模式下对 `app/services/pdf_downloader/` 三级调度进行验证，**2/2 全部通过**：

| 题名 | 命中来源 | 耗时 | 文件名校验 |
|---|---|---|---|
| 生成式AI视域下的历史文献数字阅读推广研究 | 哲舍科（首级命中） | 16s | ✅ |
| 叙事即旅行:基于世界3理论的文化遗产数字叙事框架与实现路径 | CNKI（三级命中，前两级降级） | 57s | ✅ |

三级调度链路：哲舍科 → 万方 → CNKI，按优先级依次降级，任一来源匹配即停止。覆盖模块：`pdf_downloader.py`（调度编排）、`zhesheke.py`（首级检索+PDF 下载）、`wanfang.py`（次级检索+下载判定）、`cnki.py`（末级会话复用+IP 登录+PDF 下载）。

前置条件：后端全部服务正常运行（同 CNKI 搜索测试），无需额外配置。

## 常见问题

- **`ModuleNotFoundError: No module named 'app'`** → 在项目根目录执行，或设置 `PYTHONPATH=/opt/sdi-cnki`
- **`playwright install firefox` 后仍报浏览器缺失** → 执行 `playwright install firefox --with-deps` 安装系统共享库
- **Camoufox 初始化 TypeError** → `browser.py` 已内置 fallback 到标准 Playwright Firefox，无需干预
- **`No module named 'sqlalchemy'` 等缺失包错误** → 确认 `pip install -r requirements.txt` 使用的 Python 解释器与 systemd `ExecStart` 中的路径一致
- **端口 8000 被占用** → 该项目默认使用 **8456** 端口，若仍需调整请同步修改 `vite.config.ts`、`run.py` 和 systemd service 文件
- **前端白屏 / API 请求 502** → 检查 vite 日志中反向代理目标地址是否指向正确的后端端口
- **`src/lib/` 目录缺失导致前端构建失败** → 如果从旧版仓库克隆，需确保 `src/lib/http.ts`、`src/lib/utils.ts`、`src/lib/sse.ts` 三个文件存在
