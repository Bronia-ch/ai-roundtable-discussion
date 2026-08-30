import { useEffect } from "react";
import { useSessionEvents } from "../store/useSessionEvents";
import type { SessionEventsDeps } from "../store/useSessionEvents";

export interface ResultDeps extends SessionEventsDeps {}

/** 后端 discussion_reports.raw_json 的已验证结构（engine._validate_report 契约）。 */
interface Report {
  summary: string;
  key_consensus?: string[] | string;
  main_divergence?: string[] | string;
  unresolved_questions?: string[] | string;
  suggested_actions?: string[] | string;
}

const asList = (v: string[] | string | undefined): string[] =>
  Array.isArray(v) ? v : typeof v === "string" ? [v] : [];

export function Result({ sessionId, deps }: { sessionId: string; deps?: ResultDeps }) {
  const state = useSessionEvents(sessionId, deps);
  // 成功快照（hydrated 且会话对齐）才视为已加载会话；失败/404 结束加载但 sessionId 仍 null → 不匹配
  const isLoadedSession = state.hydrated && state.sessionId === sessionId;

  // 刷新一致性：先门禁，避免初始 draft 在快照返回前把 #/result?id=… 误重定向
  useEffect(() => {
    if (!isLoadedSession) return;
    if (
      state.status === "draft" ||
      state.status === "panel_generating" ||
      state.status === "panel_ready"
    ) {
      window.location.hash = `#/panel?id=${sessionId}`;
    } else if (state.status === "ready" || state.status === "live" || state.status === "paused") {
      window.location.hash = `#/studio?id=${sessionId}`;
    }
  }, [isLoadedSession, state.status, sessionId]);

  // 防御性校验：仅解析结果是非数组对象且 summary 为 string 才视为可用报告；
  // null / 数组 / {} / 非法 JSON 一律走「报告暂不可用」兜底
  let report: Report | null = null;
  let parseFailed = false;
  if (typeof state.summary === "string") {
    try {
      const parsed: unknown = JSON.parse(state.summary);
      if (
        parsed !== null &&
        typeof parsed === "object" &&
        !Array.isArray(parsed) &&
        typeof (parsed as Record<string, unknown>).summary === "string"
      ) {
        report = parsed as Report;
      } else {
        parseFailed = true;
      }
    } catch {
      parseFailed = true;
    }
  }

  // 单一错误展示（Result 无命令 → 仅后端错误码）
  const errorText = state.errorCode ?? null;

  // 快照加载中：只判断 !state.hydrated（快照返回前 / 404 前），只显示加载提示
  if (!state.hydrated) {
    return (
      <div className="page result">
        <h1>讨论结果</h1>
        <p className="empty" data-testid="result-loading">加载结果中…</p>
      </div>
    );
  }

  // 失败/404（hydrated 但会话未对齐）：统一错误分支，仅显示错误码；不显示不可用/进行中提示
  if (!isLoadedSession) {
    return (
      <div className="page result">
        <h1>讨论结果</h1>
        <p className="error" data-testid="result-error">
          {errorText ?? "加载失败"}
        </p>
      </div>
    );
  }

  // finalizing：报告生成中；若滞留错误码（如 report_generation_failed）同时显示，不吞错误
  if (state.status === "finalizing") {
    return (
      <div className="page result">
        <h1>讨论结果</h1>
        {errorText && (
          <p className="error" data-testid="result-error">
            {errorText}
          </p>
        )}
        <p className="empty" data-testid="result-loading">报告生成中…</p>
      </div>
    );
  }

  // failed：明确失败状态与错误码（后端码优先，兜底文案）
  if (state.status === "failed") {
    return (
      <div className="page result">
        <h1>讨论结果</h1>
        <p className="error" data-testid="result-error">
          {errorText ?? "讨论失败，请重新开始"}
        </p>
      </div>
    );
  }

  // 未完成（跳转 effect 会重定向，此为渲染兜底）
  const inProgress = ["draft", "panel_generating", "panel_ready", "ready", "live", "paused"].includes(
    state.status,
  );

  return (
    <div className="page result">
      <h1>讨论结果</h1>
      {errorText && (
        <p className="error" data-testid="result-error">
          {errorText}
        </p>
      )}
      {inProgress ? (
        <p className="empty" data-testid="result-loading">讨论尚未结束，返回演播厅继续</p>
      ) : !report || parseFailed ? (
        <p className="empty" data-testid="result-unavailable">报告暂不可用</p>
      ) : (
        <>
          <section className="result-section">
            <h2>摘要</h2>
            <p>{report.summary}</p>
          </section>
          <section className="result-section">
            <h2>关键共识</h2>
            <ul>{asList(report.key_consensus).map((c, i) => <li key={i}>{c}</li>)}</ul>
          </section>
          <section className="result-section">
            <h2>主要分歧</h2>
            <ul>{asList(report.main_divergence).map((d, i) => <li key={i}>{d}</li>)}</ul>
          </section>
          <section className="result-section">
            <h2>未解决问题</h2>
            <ul>{asList(report.unresolved_questions).map((q, i) => <li key={i}>{q}</li>)}</ul>
          </section>
          <section className="result-section">
            <h2>建议行动</h2>
            <ul>{asList(report.suggested_actions).map((a, i) => <li key={i}>{a}</li>)}</ul>
          </section>
          <section className="result-section">
            <h2>原始 JSON</h2>
            <pre className="json">{state.summary}</pre>
          </section>
        </>
      )}
    </div>
  );
}
