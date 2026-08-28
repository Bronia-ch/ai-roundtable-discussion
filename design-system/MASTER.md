# AI 圆桌演播厅 · 设计系统 MASTER

> 生成工具：`ui-ux-pro-max:design-system`（v2.13.0）。本文件是前端实现的单一设计真源；所有颜色/字体/间距必须引用 token，禁止硬编码。

## 1. 产品视觉定位与设计原则

- **定位**：中文 AI 圆桌演播厅 / 直播控制台——用户是"演播厅导播"，主持人与专家是"嘉宾"，界面需同时传达"专业直播感"与"清晰信息流"。
- **原则**：
  1. **信息优先**：发言、共识/分歧、席位状态是核心，装饰从简。
  2. **状态可读**：所有状态用"文本/图标 + 颜色"双重表达，绝不只靠颜色。
  3. **区域自治**：席位区、Transcript、洞察侧栏各自独立滚动，页面本身不依赖全页滚动。
  4. **无重叠无溢出**：普通桌面与超宽屏都不得内容重叠或横向溢出。
  5. **动效克制**：动画仅用于状态切换反馈，并尊重 `prefers-reduced-motion`。
  6. **中文优先**：文案简体中文，排版以中文字体栈为准。

## 2. 字体（中文字体栈 + 字号阶梯）

```css
--font-sans: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, -apple-system, sans-serif;
--font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
```

| Token | 字号/行高 | 用途 |
|-------|-----------|------|
| `--text-xs` | 12px / 16px | 辅助、时间戳、徽章 |
| `--text-sm` | 14px / 20px | 次要正文、状态标签 |
| `--text-base` | 16px / 24px | 正文、发言 |
| `--text-lg` | 20px / 28px | 专家姓名、面板标题 |
| `--text-xl` | 24px / 32px | 页面标题 |
| `--text-2xl` | 32px / 40px | 演播厅主题标题 |

## 3. 色彩 Token（三层结构）

### 3.1 Primitive（原始值）

```css
/* 演播厅暗色底 */
--pr-blue-950: #0B0E14;
--pr-blue-900: #12161F;
--pr-blue-800: #1A202B;
--pr-blue-700: #242B3A;
/* 文本 */
--pr-gray-50:  #F5F7FA;
--pr-gray-300: #C6CDD8;
--pr-gray-500: #8A93A5;
--pr-gray-600: #5B6472;
/* 品牌与状态 */
--pr-blue-500:  #3B82F6;
--pr-green-500: #10B981;
--pr-amber-500: #F59E0B;
--pr-red-500:   #EF4444;
--pr-violet-500:#8B5CF6;
```

### 3.2 Semantic（语义别名）

```css
--color-bg:            var(--pr-blue-950);
--color-surface:       var(--pr-blue-900);
--color-surface-raised:var(--pr-blue-800);
--color-border:        var(--pr-blue-700);
--color-text:          var(--pr-gray-50);
--color-text-secondary:var(--pr-gray-300);
--color-text-muted:    var(--pr-gray-500);

--color-primary:  var(--pr-blue-500);
--color-success:  var(--pr-green-500);
--color-warning:  var(--pr-amber-500);
--color-danger:   var(--pr-red-500);
--color-info:     var(--pr-violet-500);
```

### 3.3 Component / 状态色（组件专用）

| 语义 | 用途 | 色值 |
|------|------|------|
| `--state-waiting` | 专家等待 | `var(--pr-gray-600)` |
| `--state-preparing` | 专家准备/主持人准备 | `var(--pr-amber-500)` |
| `--state-speaking` | 专家发言/主持人发言 | `var(--pr-green-500)` |
| `--state-idle` | 主持人空闲 | `var(--pr-blue-500)` |
| `--state-live` | 讨论进行中 | `var(--pr-green-500)` |
| `--state-paused` | 讨论暂停 | `var(--pr-amber-500)` |
| `--state-finalizing` | 收尾生成报告 | `var(--pr-violet-500)` |
| `--state-completed` | 已完成 | `var(--pr-green-500)` |
| `--state-failed` | 不可恢复错误 | `var(--pr-red-500)` |
| `--state-draft/panel_generating/panel_ready/ready` | 阵容流程态 | `--color-primary` / `--color-warning` |

### 3.4 对比度

- 正文 `--color-text` 对 `--color-bg` 对比度 ≥ **12:1**（WCAG AAA）。
- 次要文本 ≥ **7:1**；muted 文本仅用于非关键辅助信息（≥ **4.5:1**）。
- 状态色仅作为"点缀/描边/图标"与文本标签搭配，不作为纯色块承载唯一信息。

## 4. 间距 / 圆角 / 阴影 / 边框

```css
/* 间距（4px 基准） */
--space-1: 4px; --space-2: 8px; --space-3: 12px;
--space-4: 16px; --space-5: 20px; --space-6: 24px; --space-8: 32px;

/* 圆角 */
--radius-sm: 6px; --radius-md: 10px; --radius-lg: 16px;

/* 阴影（暗色演播厅弱投影，仅用于悬浮层） */
--shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
--shadow-md: 0 4px 12px rgba(0,0,0,0.45);
--shadow-lg: 0 12px 32px rgba(0,0,0,0.55);

/* 边框 */
--border-width: 1px;
```

## 5. 布局网格

| 断点 | 宽度 | 布局 |
|------|------|------|
| 普通桌面 | ≥ 1280px | 演播厅三栏：席位区(顶) / Transcript(中) / 洞察侧栏(右) |
| 超宽屏 | ≥ 1920px | 三栏加宽，最大内容宽 `--content-max: 1680px` 居中，不无限拉伸 |

- 全局容器：`max-width: var(--content-max); margin-inline: auto; padding: var(--space-6);`
- **禁止**：页面 body 出现横向滚动条、任意区域 `overflow-x` 未受控。

## 6. 页面布局

### 6.1 首页（讨论列表）
- 顶部：标题 + "新建讨论"主按钮。
- 主体：讨论卡片网格（每卡：主题、人数、状态徽章、创建时间；示例讨论显示"示例讨论"标签）。
- 空状态：无讨论时居中提示 + 新建入口。

### 6.2 阵容确认页
- 主题输入 + 人数选择（默认 4，范围 2–6）。
- 主持人卡片（1）+ 专家卡片（N）：姓名/职业/Title/立场/头像标识（颜色+首字母+emoji）。
- "重新生成"（整组）+ "确认阵容并进入演播厅"（确认前禁用进入）。

### 6.3 演播厅（核心）
```
┌─────────────────────────────────────────────┐
│ 席位区（主持 + 专家，独立横向/纵向滚动）      │
├──────────────────────────┬──────────────────┤
│ Transcript（独立滚动）    │ 洞察侧栏（独立滚动）│
│                          │ 共识/分歧/焦点/未解决│
├──────────────────────────┴──────────────────┤
│ 控制条：开始/暂停/继续/结束 + 当前关注点      │
└─────────────────────────────────────────────┘
```

### 6.4 结果页
- 只读：中文摘要、关键共识、主要分歧、未解决问题、建议行动。
- 原始 JSON（`--font-mono` 展示，独立滚动）。

## 7. 主持人与专家席位（ParticipantSeat）

- 头像标识：**颜色 + 首字母 + emoji**（MVP 不生成真实头像图片）。
- 席位卡片含：角色徽章（主持/专家）、姓名、Title、立场摘要、状态标签。
- 状态标签 = 图标 + 文本（等待/准备/发言/空闲），颜色仅作辅助。

## 8. 状态规范

### 8.1 角色状态

| 状态 | 图标 | 文本 | 颜色 token |
|------|------|------|-----------|
| 专家 waiting | ○ | 等待 | `--state-waiting` |
| 专家 preparing | ◐ | 准备 | `--state-preparing` |
| 专家 speaking | ● | 发言 | `--state-speaking` |
| 主持 idle | ○ | 空闲 | `--state-idle` |
| 主持 preparing | ◐ | 准备 | `--state-preparing` |
| 主持 speaking | ● | 发言 | `--state-speaking` |

### 8.2 讨论 9 态

| 状态 | 徽章文本 | 颜色 token | 路由 |
|------|---------|-----------|------|
| draft | 草稿 | gray | 阵容 |
| panel_generating | 生成阵容中 | warning | 阵容 |
| panel_ready | 待确认 | primary | 阵容 |
| ready | 已就绪 | primary | 演播厅 |
| live | 进行中 | live | 演播厅 |
| paused | 已暂停 | paused | 演播厅 |
| finalizing | 生成报告中 | finalizing | 结果 |
| completed | 已完成 | completed | 结果 |
| failed | 错误 | failed | 错误 |

## 9. 独立滚动区域

- Transcript、洞察侧栏、席位区、结果 JSON 区：`overflow: auto;`，各自独立滚动。
- 页面 body **不**依赖全页滚动；视口高度内完成布局。

## 10. 键盘焦点

- 所有可交互元素：`:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }`。
- 焦点环清晰、不与背景色冲突（主色对暗色底对比充分）。

## 11. 状态呈现（空/错/加载/降级）

- **加载态**：骨架屏或 spinner + 文本（如"生成阵容中…"），不得空白。
- **空状态**：图标 + 一句话说明 + 行动按钮。
- **错误态**：公开安全摘要 + 可恢复重试入口（不显示异常栈）。
- **降级态**：如"降级调度中"徽章，明确说明当前为降级运行。

## 12. `prefers-reduced-motion`

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```
- 动画仅用于状态切换的短暂过渡；`reduce` 时全部禁用。

## 13. 明确反模式（禁止）

1. **状态只靠颜色**——必须同时有图标/文本标签。
2. **全页滚动**——页面不能依赖整页滚动。
3. **横向溢出 / 内容重叠**——普通与超宽屏都禁止。
4. **硬编码颜色/字体/间距**——必须引用 token。
5. **真实头像图片**——用颜色+首字母+emoji。
6. **暴露模型思维链**——"当前关注点"只展示公开短摘要。
7. **在 Transcript 混入内部事件**——Transcript 只显示实际发言。
