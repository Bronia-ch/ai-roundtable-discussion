# 交付打包清单（Delivery Checklist）

> 最终打包核对清单。打包动作本身**不自动执行**：待用户批准后，由用户决定使用何种打包方式（zip 命令或图形界面）；本清单只锁定「必须包含 / 必须排除 / 打包前必须验证」三类内容。

## 1. ZIP 必含项

| 项 | 路径 | 说明 |
|----|------|------|
| 根文档 | `README.md` | 环境要求、安装、启动、测试、已知边界 |
| 架构文档 | `docs/architecture.md` | 架构、bounded contexts、ER、契约、测试策略 |
| 工作流文档 | `docs/development-workflow.md` | SDD/DDD/TDD/E2E 实际流程与纠偏 |
| Prompt 日志 | `docs/prompt-log.md` | 各阶段原始 Prompt 与纠偏记录（脱敏） |
| 交付清单 | `docs/delivery-checklist.md` | 本文件 |
| 实施计划/规格 | `docs/superpowers/` | plans + specs（实施计划 6 阶段 51 任务） |
| 设计系统证据 | `docs/ui-ux-pro-max-install-evidence.md`、`design-system/` | UI UX Pro Max 安装证据与 MASTER 设计 token |
| 后端源码 | `backend/app/` | FastAPI 应用全部模块 |
| 后端测试 | `backend/tests/` | pytest 全量离线矩阵 |
| 后端依赖声明 | `backend/requirements.txt`（及同目录构建声明） | 依赖清单 |
| 后端配置模板 | `backend/.env.example` | **模板**（占位符，无真实值） |
| 数据库 Schema | `backend/app/schema.sql` | 9 表 DDL（含在 backend/app/ 内） |
| 前端源码 | `frontend/src/`、`frontend/e2e/` | React/TS 源码与 Playwright E2E |
| 前端配置 | `frontend/package.json`、`package-lock.json`、`vite.config.ts`、`playwright.config.ts`、`tsconfig*.json` | 构建/E2E 配置（锁文件保证可复现） |
| 根配置 | `.gitignore`、`.claude/settings.json` | 忽略规则与技能启用记录 |

## 2. 明确排除项（无论作业如何要求，一律不打包）

| 类 | 模式/路径 | 原因 |
|----|-----------|------|
| 密钥与环境变量 | 任何 `.env`（**含 `backend/.env`**）、`*.pem`、`*.key`、`*.p12`、`*.pfx`、`credentials*` | 密钥纪律：绝不随包分发 |
| 数据库运行文件 | `*.db`、`data/`、`backend/data/` | 运行产物；`LLM_SQLITE_PATH=:memory:` 下 E2E 无落盘 |
| 依赖目录 | `node_modules/`、`.venv/`、`backend/.venv/`、`__pycache__/` | 体积与平台相关，安装命令见 README |
| 测试报告/产物 | `test-results/`、`playwright-report/`、`.pytest_cache/`、`.vitest/`、`coverage/` | 运行产物；需展示的测试结果已记录于本会话报告 |
| 构建产物 | `frontend/dist/` | 源码交付即可重建（`npm run build`） |
| VCS 元数据 | `.git/` | 按作业要求决定是否附历史；本清单默认排除 |

> `.gitignore` 已覆盖以上绝大多数排除项（`.env`、`.env.*`、`!.env.example`、`*.db`、`test-results/`、`node_modules/`、`.venv/`、`.pytest_tmp/` 等），可作为打包工具的天然排除依据。

## 3. 打包前验证（只读命令，命令本身完整可见，仅输出文件名/计数）

```bash
# 1) 工作区状态与空白检查
git status --porcelain
git diff --check

# 2) 敏感信息扫描（只输出命中文件名与数量，绝不打印匹配内容）
git ls-files | rg -i '(^|/)\.env($|\.)|\.(pem|key|p12|pfx|crt)$|secret|credential|auth'
rg -l -e 'BEGIN [A-Z ]*PRIVATE KEY' -e 'sk-[A-Za-z0-9]{16,}' -e 'AKIA[0-9A-Z]{16}' \
      -e '(ghp|github_pat)_[A-Za-z0-9]{20,}' -e 'ANTHROPIC_(AUTH_TOKEN|API_KEY)=[^[:space:]]+' \
      -e 'LLM_API_KEY[=:][[:space:]]*[^[:space:]"]{4,}' -e 'DEEPSEEK_API_KEY[=:][[:space:]]*[^[:space:]"]{4,}' .

# 3) Git 历史扫描（所有提交，只输出文件名）
for pat in 'BEGIN [A-Z ]*PRIVATE KEY' 'sk-[A-Za-z0-9]{16,}' 'AKIA[0-9A-Z]{16}' \
           '(ghp|github_pat)_[A-Za-z0-9]{20,}' 'ANTHROPIC_(AUTH_TOKEN|API_KEY)=[^[:space:]]+' \
           'LLM_API_KEY[=:][[:space:]]*[^[:space:]"]{4,}' 'DEEPSEEK_API_KEY[=:][[:space:]]*[^[:space:]"]{4,}'; do
  git rev-list --all | while read -r r; do git grep -l -I -E "$pat" "$r" 2>/dev/null; done | sort -u
done
```

**本会话基线（2026-08-31 实测）**：三组命令均为 0 命中；`git status --porcelain` 仅列出待批准文档（README.md、backend/.env.example、docs/architecture.md、docs/development-workflow.md、docs/prompt-log.md、docs/delivery-checklist.md）。

## 4. 最终验证矩阵（打包前建议重跑）

| 层 | 命令 | 基线（本会话实测） |
|----|------|--------------------|
| 后端全量 | `cd backend; $env:SMOKE_REAL_LLM='0'; ..\.venv\Scripts\python.exe -m pytest tests -q` | 217 passed, 1 skipped（真实 smoke 恒定 SKIPPED），14.57s |
| 前端单测 | `cd frontend; npm test` | 34 passed（3 文件） |
| 前端构建 | `cd frontend; npm run build` | tsc --noEmit + vite build 成功 |
| E2E | `cd frontend; npm run e2e` | 7 passed（13.3s），webServer 自动拉起内存 SQLite + LLM 网络隔离后端 |

## 5. 提交与分发边界（本作业纪律）

- 本地交付物完成后**停止等待单独批准**：不提交、不打包 ZIP、不创建远端仓库、不 push、不发邮件。
- 获批后：`git add` 精确暂存 → 展示 `git diff --cached --stat` / `--cached --check` → 获批 → 提交；push 与打包另行批准。
- 真实 DeepSeek API 从未执行、模型 ID 未验证：任何交付说明不得将其表述为已验证。
