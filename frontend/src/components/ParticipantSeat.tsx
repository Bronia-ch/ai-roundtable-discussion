const STATE_LABELS: Record<string, string> = {
  waiting: "等待",
  preparing: "准备",
  speaking: "发言",
  idle: "空闲",
};

interface ParticipantSeatProps {
  name: string;
  role: "host" | "expert";
  title: string;
  stance: string;
  avatarColor: string;
  avatarEmoji: string;
  /** 后端 runtime_state 值域；未知值回退「等待」。 */
  runtimeState: string;
}

export function ParticipantSeat({
  name,
  role,
  title,
  stance,
  avatarColor,
  avatarEmoji,
  runtimeState,
}: ParticipantSeatProps) {
  return (
    <div className="participant-seat" data-state={runtimeState}>
      <div className="avatar" style={{ backgroundColor: avatarColor }}>
        <span className="avatar-emoji">{avatarEmoji}</span>
        <span className="avatar-initial">{name[0]}</span>
      </div>
      <div className="seat-body">
        <div className="seat-name">
          <strong>{name}</strong>
          <span className="role-tag">{role === "host" ? "主持人" : "专家"}</span>
        </div>
        <div className="seat-title">{title}</div>
        <div className="seat-stance">{stance}</div>
        <div className="state-label">
          <span className="state-dot" aria-hidden="true" />
          {STATE_LABELS[runtimeState] ?? "等待"}
        </div>
      </div>
    </div>
  );
}
