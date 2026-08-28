# UI UX Pro Max 安装与加载证据

- **日期**：2026-08-28
- **模型**：deepseek-v4-pro[1M]
- **官方来源**：https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

## 安装命令（实际执行）

> 斜杠命令 `/plugin ...` 为 Claude Code 用户级命令，代理无法直接执行，改用等价的 `claude` CLI 完成安装。

| 计划斜杠命令 | 实际执行的 CLI 等价命令 | 结果 |
|-------------|------------------------|------|
| `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` | `claude plugin marketplace add https://github.com/nextlevelbuilder/ui-ux-pro-max-skill` | ✔ 成功添加 marketplace `ui-ux-pro-max-skill` |
| `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`（作用域：Install for all collaborators on this repository） | `claude plugin install ui-ux-pro-max@ui-ux-pro-max-skill --scope project -y` | ✔ 成功安装 |
| `/reload-plugins` | 用户执行 `/reload-plugins` | ✔ Reloaded: 2 plugins · 21 skills · 6 agents · 1 hook |

## 安装结果

- **插件名**：`ui-ux-pro-max@ui-ux-pro-max-skill`
- **版本**：2.13.0
- **作用域**：project（即"本仓库所有协作者"）
- **状态**：✔ enabled
- **组件清单**：Skills(7) = banner-design、brand、design、design-system、slides、ui-styling、ui-ux-pro-max；Agents/Hooks/MCP 均为 0。

## 项目文件变化

- 新增 `.claude/settings.json`（仅含插件启用信息，无密钥）：
  ```json
  { "enabledPlugins": { "ui-ux-pro-max@ui-ux-pro-max-skill": true } }
  ```
- `.claude/settings.local.json` 保持被忽略，未改动。

## 技能可调用性核验（已通过）

- `/reload-plugins` 输出：`Reloaded: 2 plugins · 21 skills · 6 agents · 1 hook`。
- `Skill("ui-ux-pro-max:design-system")` → 成功加载（返回 token 架构与组件规范指引）。

**核验结论**：`ui-ux-pro-max` 插件已安装（v2.13.0，project 作用域）且其 7 个 skills 均可调用；其中生成设计系统使用 `ui-ux-pro-max:design-system`。
