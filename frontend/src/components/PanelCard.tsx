interface PanelCardProps {
  name: string;
  role: "host" | "expert";
  profession: string;
  title: string;
  stance: string;
  avatarColor: string;
  avatarEmoji: string;
}

export function PanelCard({
  name,
  role,
  profession,
  title,
  stance,
  avatarColor,
  avatarEmoji,
}: PanelCardProps) {
  return (
    <div className="panel-card">
      <div className="avatar" style={{ backgroundColor: avatarColor }}>
        <span className="avatar-emoji">{avatarEmoji}</span>
        <span className="avatar-initial">{name[0]}</span>
      </div>
      <div className="panel-card-body">
        <div className="seat-name">
          <strong>{name}</strong>
          <span className="role-tag">{role === "host" ? "主持人" : "专家"}</span>
        </div>
        <div className="seat-title">{profession} · {title}</div>
        <div className="seat-stance">{stance}</div>
      </div>
    </div>
  );
}
