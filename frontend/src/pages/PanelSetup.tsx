import { PanelCard } from "../components/PanelCard";

const HOST = {
  name: "周明远",
  role: "host" as const,
  profession: "科技评论员",
  title: "资深主编",
  stance: "中立理性",
  avatarColor: "#5B8DEF",
  avatarEmoji: "🎙️",
};

const EXPERTS = [
  { name: "林晓", role: "expert" as const, profession: "经济学家", title: "教授", stance: "担忧：AI 红利集中于资本方", avatarColor: "#E4572E", avatarEmoji: "📉" },
  { name: "陈曦", role: "expert" as const, profession: "AI 研究员", title: "实验室主任", stance: "乐观：AI 可普惠化", avatarColor: "#2EA66E", avatarEmoji: "🤖" },
  { name: "王芳", role: "expert" as const, profession: "社会学学者", title: "副教授", stance: "警惕：数字鸿沟扩大", avatarColor: "#8E44AD", avatarEmoji: "🧭" },
  { name: "赵铁柱", role: "expert" as const, profession: "一线工人代表", title: "工会委员", stance: "关注：就业冲击与再培训", avatarColor: "#B7791F", avatarEmoji: "🔧" },
];

export function PanelSetup() {
  return (
    <div className="page panel-setup">
      <h1>阵容确认</h1>
      <div className="setup-form">
        <label>
          讨论主题
          <input type="text" placeholder="输入讨论主题" />
        </label>
        <label>
          专家人数
          <select defaultValue={4}>
            {[2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n} 人
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="panel-list">
        <PanelCard {...HOST} />
        {EXPERTS.map((e) => (
          <PanelCard key={e.name} {...e} />
        ))}
      </div>
      <div className="actions">
        <button className="btn">重新生成</button>
        <button className="btn btn-primary">确认阵容并进入演播厅</button>
      </div>
    </div>
  );
}
