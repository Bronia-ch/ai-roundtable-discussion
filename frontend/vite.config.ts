import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // T0.2 最小同源代理：/sessions 前缀（含 POST/GET 与后续 SSE 子路径）转发到真实后端，
    // 不改写路径；浏览器始终访问前端同源地址 localhost:5173
    proxy: {
      "/sessions": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
