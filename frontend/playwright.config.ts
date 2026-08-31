import { defineConfig } from "@playwright/test";

const backendPort = 8010;
const frontendPort = 5180;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  use: {
    browserName: "chromium",
    channel: "msedge",
    baseURL: `http://localhost:${frontendPort}`,
  },
  webServer: [
    // 后端：项目虚拟环境解释器 + uvicorn（内存 SQLite，每次 E2E 全新库）
    {
      // cmd.exe 无法解析以 ".." + 正斜杠开头的命令路径（会把 ".." 当作命令名），
      // venv 解释器必须用 Windows 反斜杠；uvicorn 参数（--app-dir）由 python 处理，正斜杠兼容
      command:
        `..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port ${backendPort}`,
      url: `http://127.0.0.1:${backendPort}/healthz`,
      timeout: 60000,
      reuseExistingServer: false, // 8000 被占用必须明确失败，不复用来源不明的后端
      env: {
        LLM_SQLITE_PATH: ":memory:", // 独立 E2E SQLite：不写入开发库 ./data/app.db
        SMOKE_REAL_LLM: "0",
        LLM_FAKE: "1", // 离线 FakeLLMProvider：全流程不依赖真实 LLM
        // 双保险：即使误触 LLM 路径也只能本机失败，绝不请求真实 DeepSeek
        LLM_BASE_URL: "http://127.0.0.1:9/v1",
        LLM_API_KEY: "",
        LLM_MODEL: "e2e-no-network",
      },
    },
    // 前端：保留原有 npm run dev 行为
    {
      command: `npm run dev -- --port ${frontendPort} --strictPort`,
      url: `http://localhost:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 60000,
      env: {
        VITE_API_TARGET: `http://127.0.0.1:${backendPort}`,
      },
    },
  ],
});
