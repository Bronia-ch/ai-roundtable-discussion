import uuid

import aiosqlite

# 5 组示例讨论：主题 + 主持人 + 4 位立场互斥的专家
# 字段顺序：(姓名, 职业, Title, 立场, 头像颜色, 头像 emoji)
SAMPLES = [
    {
        "topic": "人工智能是否会加剧社会不平等",
        "host": ("周明远", "科技评论员", "资深主编", "中立理性", "#5B8DEF", "🎙️"),
        "experts": [
            ("林晓", "经济学家", "教授", "担忧：AI 红利集中于资本方", "#E4572E", "📉"),
            ("陈曦", "AI 研究员", "实验室主任", "乐观：AI 可普惠化", "#2EA66E", "🤖"),
            ("王芳", "社会学学者", "副教授", "警惕：数字鸿沟扩大", "#8E44AD", "🧭"),
            ("赵铁柱", "一线工人代表", "工会委员", "关注：就业冲击与再培训", "#B7791F", "🔧"),
        ],
    },
    {
        "topic": "远程办公是未来主流还是过渡方案",
        "host": ("苏婷", "管理顾问", "高级合伙人", "中立客观", "#5B8DEF", "🎙️"),
        "experts": [
            ("李强", "企业 HR 总监", "人力资源负责人", "支持：弹性办公提效", "#2EA66E", "💼"),
            ("张伟", "软件工程师", "高级工程师", "享受但担忧协作效率", "#E4572E", "💻"),
            ("陈静", "房地产分析师", "研究总监", "担忧：写字楼空置", "#8E44AD", "🏢"),
            ("刘洋", "心理咨询师", "执业咨询师", "关注：员工孤独感", "#B7791F", "🧠"),
        ],
    },
    {
        "topic": "是否应该全面禁止燃油车",
        "host": ("高翔", "交通政策研究员", "研究员", "中立", "#5B8DEF", "🎙️"),
        "experts": [
            ("赵敏", "新能源车企高管", "副总裁", "支持：加速禁售燃油车", "#2EA66E", "🔋"),
            ("王磊", "石油行业分析师", "首席分析师", "担忧：能源转型阵痛", "#E4572E", "🛢️"),
            ("孙倩", "环保组织负责人", "理事长", "支持：加速减排", "#8E44AD", "🌿"),
            ("钱军", "二手车从业者", "行业协会理事", "担忧：基层就业冲击", "#B7791F", "🚗"),
        ],
    },
    {
        "topic": "短视频对青少年的影响利大于弊吗",
        "host": ("周蓉", "教育学者", "教授", "中立", "#5B8DEF", "🎙️"),
        "experts": [
            ("吴桐", "中学教师", "年级主任", "担忧：沉迷与注意力下降", "#E4572E", "📵"),
            ("郑爽", "短视频运营", "内容负责人", "强调：信息普惠与表达", "#2EA66E", "📱"),
            ("冯丽", "儿童心理专家", "主任医师", "担忧：价值观与认知", "#8E44AD", "🧒"),
            ("蒋涛", "大学生", "学生会主席", "认为：利大于弊", "#B7791F", "🎓"),
        ],
    },
    {
        "topic": "加密货币是泡沫还是未来货币",
        "host": ("何明", "金融评论员", "资深评论员", "中立审慎", "#5B8DEF", "🎙️"),
        "experts": [
            ("罗成", "区块链创业者", "创始人", "看好：未来货币形态", "#2EA66E", "⛓️"),
            ("林芳", "金融学者", "研究员", "质疑：货币属性缺失", "#E4572E", "🏦"),
            ("唐宇", "风险投资人", "合伙人", "看好：底层技术价值", "#8E44AD", "📈"),
            ("郭强", "普通投资者", "投资者", "警惕：泡沫与风险", "#B7791F", "⚠️"),
        ],
    },
]


async def run(conn: aiosqlite.Connection) -> None:
    """幂等写入 5 组示例讨论（is_sample=1、状态 panel_ready）。"""
    for s in SAMPLES:
        sid = "sample_" + uuid.uuid5(uuid.NAMESPACE_URL, s["topic"]).hex[:8]
        await conn.execute(
            "INSERT OR IGNORE INTO sessions "
            "(id, topic, expert_count, status, is_sample) VALUES (?, ?, ?, ?, 1)",
            (sid, s["topic"], 4, "panel_ready"),
        )
        cnt = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) FROM participants WHERE session_id=?", (sid,)
                )
            ).fetchone()
        )[0]
        if cnt:
            continue
        hname, hprof, htitle, hstance, hcol, hem = s["host"]
        await conn.execute(
            "INSERT INTO participants "
            "(id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order, runtime_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid + "_host", sid, "host", hname, hprof, htitle, hstance, hcol, hem, 0, "idle"),
        )
        for i, (n, p, t, st, c, e) in enumerate(s["experts"], start=1):
            await conn.execute(
                "INSERT INTO participants "
                "(id, session_id, role, name, profession, title, stance, avatar_color, avatar_emoji, sort_order, runtime_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid + "_e" + str(i), sid, "expert", n, p, t, st, c, e, i, "waiting"),
            )
    await conn.commit()
