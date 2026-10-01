# code/ — Jev Search 核心代码归档

本目录的文件**原样复制**自 [Jev Search](https://github.com/superagents-lab/jev-search)（作者 Search1API，MIT），
未做任何修改，仅用于配合上一级 [`../ANALYSIS.md`](../ANALYSIS.md)（《Jev Search 的 Jev 用法分析报告》）阅读。

- 分析结论、调用点清单、设计手法、风险点与**图书语义检索落地建议**：见 [`../ANALYSIS.md`](../ANALYSIS.md)。
- 原项目说明（部署、provider、数据与限制）：见 [`docs/README.md`](docs/README.md)。
- 许可与署名：见 [`LICENSE`](LICENSE)（原始版权归 Search1API，MIT）。

## 从这里开始读

想理解 Jev 是怎么被使用的，按这个顺序看四个文件即可：

1. `src/lib/typesafe.ts` —— Jev 客户端、`noul`/`choice` 两类问题、三家 provider 的方言归一与降级换家。
2. `src/lib/sources.ts` —— 声明式信源表：每个源的 `ask.{question,yes,no}` 就是喂给 Jev 的判断标准。
3. `src/lib/candidates.ts` —— 代码如何构造有界候选，让模型只做"挑选"而不是"生成"。
4. `src/lib/pipeline.ts` —— 编排：投机搜索、车道并行、`intent → found → lane → done` 事件协议与分侧计时。

`test/pipeline.test.ts` 与 `test/typesafe.test.ts` 展示了**不依赖任何 API key** 的测试方式（stub `fetch`，按收到的 `questions` 生成答案）。

## 注意

这些文件不能在本目录独立构建：它们 import `@/lib/...`，依赖原项目的 `tsconfig.json` / `vitest.config.ts` 路径别名与依赖树。
要在本地运行，请 clone 原仓库后按 `docs/README.md` 的 `pnpm install` / `pnpm test` 步骤操作。
