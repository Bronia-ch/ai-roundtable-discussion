import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscussionCard } from "../src/components/DiscussionCard";
import { ParticipantSeat } from "../src/components/ParticipantSeat";
import { Transcript } from "../src/components/Transcript";
import { InsightPanel } from "../src/components/InsightPanel";

describe("DiscussionCard", () => {
  it("renders topic and sample tag", () => {
    render(
      <DiscussionCard topic="人工智能与社会不平等" status="panel_ready" isSample />,
    );
    expect(screen.getByText("人工智能与社会不平等")).toBeInTheDocument();
    expect(screen.getByText("示例讨论")).toBeInTheDocument();
  });

  it.each([
    ["draft", "/panel", "草稿"],
    ["panel_generating", "/panel", "生成阵容中"],
    ["panel_ready", "/panel", "待确认"],
    ["ready", "/studio", "已就绪"],
    ["live", "/studio", "进行中"],
    ["paused", "/studio", "已暂停"],
    ["finalizing", "/finalizing", "生成报告中"],
    ["completed", "/result", "已完成"],
    ["failed", "/failed", "错误"],
  ] as const)("routes status %s to %s with badge %s", (status, route, badge) => {
    render(<DiscussionCard topic="t" status={status} />);
    expect(screen.getByTestId("card-link").getAttribute("href")).toBe(route);
    expect(screen.getByText(badge)).toBeInTheDocument();
  });
});

describe("ParticipantSeat", () => {
  it.each([
    ["expert", "waiting", "等待"],
    ["expert", "preparing", "准备"],
    ["expert", "speaking", "发言"],
    ["host", "idle", "空闲"],
  ] as const)("renders %s %s with text label %s", (role, state, label) => {
    render(
      <ParticipantSeat
        name="张三"
        role={role}
        title="教授"
        stance="中立"
        avatarColor="#3B82F6"
        avatarEmoji="🤖"
        runtimeState={state}
      />,
    );
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe("Transcript", () => {
  it("renders only utterance text", () => {
    render(
      <Transcript
        utterances={[
          {
            id: "u1",
            turn_id: "t1",
            speaker_id: "p1",
            role: "host",
            text: "欢迎来到圆桌讨论",
            ordinal: 1,
          },
          {
            id: "u2",
            turn_id: "t2",
            speaker_id: "p2",
            role: "expert",
            text: "我认为这个观点值得商榷",
            ordinal: 2,
          },
        ]}
      />,
    );
    expect(screen.getByText("欢迎来到圆桌讨论")).toBeInTheDocument();
    expect(screen.getByText("我认为这个观点值得商榷")).toBeInTheDocument();
  });
});

describe("InsightPanel", () => {
  it("renders consensus, divergence, focus and open questions", () => {
    render(
      <InsightPanel
        focus="是否全面禁售燃油车"
        insights={[
          {
            id: "i1",
            kind: "consensus",
            text: "远程办公提升效率",
            support_count: 3,
            oppose_count: 0,
            status: "active",
            version: 1,
          },
          {
            id: "i2",
            kind: "divergence",
            text: "燃油车禁令时机",
            support_count: 2,
            oppose_count: 2,
            status: "active",
            version: 1,
          },
          {
            id: "i3",
            kind: "open_question",
            text: "基层就业如何保障",
            support_count: 0,
            oppose_count: 0,
            status: "active",
            version: 1,
          },
        ]}
      />,
    );
    expect(screen.getByText("共识")).toBeInTheDocument();
    expect(screen.getByText("分歧")).toBeInTheDocument();
    expect(screen.getByText("未解决问题")).toBeInTheDocument();
    expect(screen.getByText("远程办公提升效率")).toBeInTheDocument();
  });
});
