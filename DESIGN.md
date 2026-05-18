---
name: SDI-CNKI
description: CNKI 学术定题服务系统 - 智能文献追踪平台
colors:
  primary: "#292524"
  neutral-bg: "#fcfaef"
  foreground: "#1c1917"
  border: "#e7e5e4"
typography:
  display:
    fontFamily: "Plus Jakarta Sans, sans-serif"
    fontWeight: 700
  body:
    fontFamily: "Plus Jakarta Sans, sans-serif"
rounded:
  md: "8px"
---

# Design System: SDI-CNKI

## 1. Overview

**Creative North Star: "The Academic Pulse" (学术脉动)**

本系统追求一种“温暖且专业”的学术生产力氛围。它拒绝了传统 SaaS 软件冷冰冰的蓝白调，转而使用类似 Notion 的微暖纸张感背景，配合石砾深灰的深沉色调，旨在为学术工作者提供一个宁静、专注且可靠的工作环境。

**Key Characteristics:**
- **Warm Canvas**: 使用 `#fcfaef` 缓解视觉疲劳。
- **Precision Strokes**: 线条简洁有力，符合学术严谨性。
- **Restrained Motion**: 交互响应迅速而不突兀。

## 2. Colors

### Primary
- **Stone Deep Gray** (#292524): 用于品牌标识、主要操作按钮和关键导航项，传达稳重与高权威感。

### Neutral
- **Warm Paper** (#fcfaef): 级细微背景色，建立系统基调。
- **Stone Ink** (#1c1917): 文本主体色。

## 3. Typography

**Display & Body Font:** Plus Jakarta Sans

### Hierarchy
- **Logo Wordmark**: Bold (700), Letter-spacing (-0.02em).
- **Heading**: Semi-bold (600).
- **Body**: Regular (400).

## 4. Components

### Sidebar
- **Logo Area**: H-14 height, contains `logo.svg`.
- **Nav Items**: 8px rounded, subtle Stone-800 focus state.

## 6. Do's and Don'ts

### Do:
- 保持界面呼吸感，间距遵循 4px/8px 律动。
- 使用 OKLCH 调整色彩深度。

### Don't:
- 禁止使用纯黑 (#000) 或纯蓝色的默认样式。
- 禁止在核心 UI 中使用毛玻璃效果（Glassmorphism）。
