# Impeccable Reference Index

本目录收录 `reference/` 下全部 36 个参考文件，按职责分为五大类。

---

## 🏗️ 核心流程 (Core Flows)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **shape.md** | 设计规划命令 | 通过发现性访谈产出结构化的设计 brief（ Purpose / Audience / Content / 方向 / 范围 / 状态 / 交互模型 / 内容需求 / 推荐参考），确认前不编码。craft 的前置步骤。 |
| **craft.md** | 全流程构建命令 | 将 shape 的 brief 落地为生产级代码。含 6 步：发现已有框架/设计系统 → 运行 shape → 加载参考 → (可选) 生成视觉方向 mock → 编码生产质量 → 迭代审查 → 交付。重点在多远型门控（多轮用户确认后才写码）。 |
| **teach.md** | 项目上下文发现与写入 | 自动推断并创建 `PRODUCT.md` + `DESIGN.md`。从代码库扫描出发，经战略访谈，输出品牌/产品方向与视觉规范，令所有其他命令有据可查。 |
| **extract.md** | 设计系统提取与重组 | 识别代码中复用≥3 次的模式、组件和 token，提取并迁移到设计系统，消除重复实现。 |

---

## 🎨 视觉设计 (Visual Design)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **brand.md** | 品牌设计规范（注册级别） | 当设计**本身是产品**时使用（官网、落地页、市场海报）。涵盖字体选择流程（含 reflex-reject 黑名单 + 被禁止的美学车道）、配色策略（三大选色法：Committed / Restrained / Full palette / Drenched）、排版节奏、非线性构图与品牌禁令。AI slop 测试检核：若可被直接识别为 AI 生成，即失败。 |
| **product.md** | 产品 UI 设计规范（注册级别） | 当设计**服务于产品**时使用（应用、后台、数据表、工具）。系统字体合法；单字族常足够；固定 `rem` 级字号而非 fluid；Restrained 是配色底线；状态词汇（hover/focus/active/disabled/error/success）必须标准化。 |
| **typeset.md** | 排版升级改造 | 将模糊/默认排版（Inter/系统默认/平铺式字号）替换为反映品牌的层级排版。含字体选择（品牌走 brand.md；产品走系统字体）、5 级字号系统、 fluency/fixed 尺度选择策略、weight 策略和验证清单。 |
| **typography.md** | 排版深层参考 | 字体学细节：垂直节律、模块化比例、行宽 chunk、OpenType 特性（tabular-nums、small-caps、ligatures）、字体加载策略（swap vs optional、metric-matched fallback）、Web Font Loading 防 FOUT。品牌选择也向上对齐 brand.md 的 ref→reject 逻辑。 |
| **color-and-contrast.md** | 色彩与对比深规 | 全面色彩系统。先用 OKLCH 替代 HSL；构建 tinted-Neutral（±0.005 色度）统一页面颜色感；Palette 结构（Primary/Neutral/Semantic/Surface）；60-30-10 视觉权重规则；WCAG AA/AAA 对比基准；灰/​黑禁用清单；暗色模式≠反向色；token hierarchy 二层；Alpha smell。 |
| **colorize.md** | 色彩战略引入 | 替换灰阶或单点缀色界面，按 Brand/Product 注册选择策略；引入语义色（成功/警告/错误/信息）；应用 tinted surfaces 与 hairline borders；绝对禁用 border-left≥2px 饰边；Live mode 署名 params：`color-amount` range。 |
| **polish.md** | 最终精度打磨 | 在功能完成后的最后一轮系统性检查：对齐设计系统（漂移按根因分类：缺 token / 一次实现 / 概念偏差）、信息架构与相邻功能的对齐、可访问性、交互状态完整度、空/加载/错误状态、微交互、字体细节、图标与图片、断点响应、代码整洁。含 20+ 项 Checklist。 |

---

## ✨ 视觉增强 (Visual Enhancement)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **bolder.md** | 冲击力放大 | 当用户想要"更大胆/更醒目"时使用。通过更强层级决心（尺幅跳 3-5×、极端 weight 对比）、一种更饱和色彩、更大胆的留白/不对称、打破网格、克制但戏剧化的阴影/质感，拒绝"AI slop"默认（青紫渐变、玻璃主义、渐变文字）。 |
| **quieter.md** | 视觉减噪 | 当界面过于激进/贫血时使用——降低饱和度、减少装饰、调弱运动，但不等于无聊或灰度。保留品牌调性只是在控制地产出。 |
| **distill.md** | 精简化繁 | 果断删除不必要内容：减少字号/字体/颜色/容器/层级；渐进披露； eliminates nested cards。核心：剔除功能≠变简单；"完美是没什么可加，也没什么可减"。 |
| **delight.md** | 微交互与愉悦 | 在应有欢愉感的时刻增加交互记忆点：按钮物理压感、成功打勾/五彩碎纸、空状态个性化文案、里程碑庆祝、季节性彩蛋。注意场合适配（正经工具≠游戏化）。 |
| **overdrive.md** | 超能力效果 | 对当前界面使用最具技术野心的增强：WebGL/Three.js 着色器、 并以滚动驱动动画、See View Transitions API、虚拟滚动（10 万行）、Web Workers/WASM、Web Audio API。**进阶前必须先提案→用户选方向**。效果随运变化；渐进降级不可协商。 |

---

## 🔧 质量、模式与规范 (Quality, Patterns & Standards)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **audit.md** | 技术质量扫描 | 按 5 个维度给代码做系统性检查并出报告：可访问性、性能、主题覆盖度、响应式、反 AI 模式。195 项可操作修复建议；输出 0-20 分健康总分，P0-P3 优先级排序。不可修复的报告，只记录。 |
| **critique.md** | 综合设计评审 | 双重评估：① LLM 从代码+视觉横截面做整体设计批评；② `impeccable detect` CLI 扫描 27 类模式 + 浏览器浏览器覆盖（Human tab）。输出 Nielsen 10 启发式 + AI slop 双重定论 + 角色 Persona Red Flags + 持久化快照，接续 `/impeccable polish`。 |
| **heuristics-scoring.md** | Nielsen 10 启发式评分参考 | 每个启发式 0-4 分打分规则，含具体检查项和分数释义。同含 P0-P3 问题严重度定义。总分满分 40；28-35 Good；20-27 Acceptable；12-19 Poor；0-11 Critical。 |
| **personas.md** | Persona 测试参考 | 覆盖 5 个用户原型：Alex（高效号使用者）、Jordan（首次出门）、Sam（无障碍依赖）、Riley（边缘痛测试器）、Casey（分心移动用户）。每种列出"红旗"触发点；按界面类型推荐适用组合。若 `GEMINI.md` 含 Design Context，可生成项目特定 Persona。 |
| **cognitive-load.md** | 认知负荷评估清单 | 识别并修复认知过载：内在/外部/迁移三类负荷；8项清单检核；工作记忆上限 ≤4 项；常见违规 8 类（选项墙、记忆桥、信息噪声地板、不一致模式等）。 |
| **interaction-design.md** | 交互状态规范 | 8 种交互态（默认/悬停/焦点/按下/禁用/加载/错误/成功）的设计规则；正确 focus ring 写法（`:focus-visible`）；表单 label、placeholder、验证时机；Modal `inert` 用法；Popover API；CSS Anchor Positioning；下拉菜单防范 overflow-clip 陷阱；`z-index` 语义尺度；破坏性操作用撤销，不用确认。 |
| **document.md** | 生成 DESIGN.md | 按 Google Stitch DESIGN.md 格式（YAML frontmatter + 6 节 markdown）自动提取既有颜色/字体/组件 token，经用户质询定性语言后生成正式 `DESIGN.md` + `.impeccable/design.json` 侧车文件（含 tonal ramp、motion token、组件 HTML/CSS snippet）。含 seed-mode（绿色项目 5 题访谈建雏形）。 |
| **harden.md** | 防御性加固 | 让界面扛得住真实用户输入、语言、网络与错误：文本溢出与换行（`truncate`/`line-clamp`/`word-wrap`、Flex→`min-width: 0`）、i18n 文本膨胀（+30% space）、RTL、CJK 字符编码、API 错误分状态处理（400/401/403/404/429/500）、空/加载/大数据集/并发操作/权限丢失/离线：数百行示例。含手动/自动化测试策略。 |
| **responsive-design.md** | 响应式设计标准 | 移动优先写法（`min-width` 累进），断点由内容决定而非设备 ID；Pointer/hover media query 做输入方法检测；`env(safe-area-inset-*)` 做 notch 适配；`srcset`/`picture` 元素权威写法；导航/表格三阶段响应策略；建议真机实测（Cheap Android 揭示性能问题）。 |

---

## 🤖 Live Mode & 生产指导 (Live Mode & Production Guidance)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **live.md** | Live picker 协议全程参考 | ~620 行包含完整交互协议：启动 → 轮询 → 三变体生成（身份识别→模式→三轴规划→squint 测试）→ 参数声明（range/steps/toggle）→ 接受（碳化→持久化）→ 丢弃 → 挂起/恢复 → 终止清理 → CSP 首次设置 → 中断恢复命令。从策略层到技术实现层完整覆盖。 |
| **motion-design.md** | 运动设计深度指南 | 100 毫秒/200 毫秒/300 毫秒/500 毫秒时域规则；ease-out-quart/quint/expo；premium motion material（blur/filter/mask/shadow/clip-path；transform/opacity 并非排他）；stagger calc；prefers-reduced-motion；感知性能 80 毫秒阈值；Intersection Observer 关键帧绑定实践参考（`polish.md` 蹭略，detail 放此见 26 fps→108 全量）。 |

---

## 📐 布局与空间 (Layout & Space)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **spatial-design.md** | 空间设计底层知识 | 4pt 基点网格（非 8pt 粗粒度）；命名原则：`--space-sm` 而非 `--spacing-8`；自调节网格 `repeat(auto-fit, minmax(280px,1fr))`；容器查询（组件级自适应）；squint 测试；层级工具维度（大小/字重/色彩/位置/空间）；键盘焦点目标区设计（44px 可达，视觉可采用辅助类）。 |

---

## ✍️ Copy & 内容 (UX Writing)

| 文件 | 主要作用 | 一句话含义 |
|------|---------|------------|
| **ux-writing.md** | UX 文案标准 | 按钮标签动词 + 宾语（禁用 OK/Submit/Yes/No）；错误消息三要素公式（what/why/howto）；空状态三件套；声线 vs 语气（成功：开心；错误：同理心；加载： reassurance）；可访问性文件命名（链接文本 ↗ 可脱读；图 alt 描述所载信息）；翻译空间预留（德语+30%）。 |
