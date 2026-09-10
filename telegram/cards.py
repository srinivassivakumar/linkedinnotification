from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from orchestrator.models import Candidate


DIVIDER = "━━━━━━━━━━━━━━━━━━"


STATUS = {
    "p0": "🔥",
    "p1": "🟡",
    "info": "🔵",
    "event": "🟣",
    "done": "🟢",
    "attention": "⚠️",
    "blocked": "❌",
    "working": "⏳",
    "person": "👤",
    "people": "👥",
    "mail": "📨",
    "doc": "📄",
    "brain": "🧠",
    "target": "🎯",
    "time": "⏰",
}


@dataclass(frozen=True)
class DashboardSnapshot:
    p0_jobs: int = 0
    p1_jobs: int = 0
    replies: int = 0
    interviews: int = 0
    followups: int = 0
    applied_today: int = 0
    outreach_today: int = 0
    claude_status: str = "NORMAL"
    scan_age: str = "not run yet"


@dataclass(frozen=True)
class ContactPath:
    company: str
    role: str
    name: str
    title: str
    confidence: str
    why: str
    angle: str
    index: int = 1
    total: int = 1
    linkedin_url: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class ApplicationStatus:
    company: str
    role: str
    state: str = "APPLICATION"
    resume: str = "⬜"
    email: str = "⬜"
    linkedin: str = "⬜"
    referral: str = "⬜"


@dataclass(frozen=True)
class ActionRequired:
    title: str
    company: str
    role: str
    when: str
    remaining: str
    note: str


@dataclass(frozen=True)
class InterviewStatus:
    company: str
    role: str
    when: str
    remaining: str
    readiness: int
    preparation: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FollowUpStatus:
    name: str
    title: str
    initial_outreach: str
    days_since_contact: int
    reply: str
    job_still_active: bool
    recommendation: str
    index: int = 1
    total: int = 1


@dataclass(frozen=True)
class FocusItem:
    label: str
    detail: str


def keyboard(rows: list[list[dict[str, str]]]) -> dict[str, list[list[dict[str, str]]]]:
    return {"inline_keyboard": rows}


def action(text: str, callback_data: str) -> dict[str, str]:
    return {"text": text, "callback_data": callback_data[:64]}


def url_button(text: str, url: str) -> dict[str, str]:
    return {"text": text, "url": url}


def priority_for_candidate(candidate: Candidate) -> tuple[str, str]:
    intelligence = candidate.intelligence or {}
    priority = str(intelligence.get("priority") or "").upper()
    if priority in {"P0", "P1", "P2"}:
        return priority, _priority_emoji(priority)
    if candidate.score.pre_score >= 75:
        return "P0", STATUS["p0"]
    if candidate.score.pre_score >= 60:
        return "P1", STATUS["p1"]
    return "P2", STATUS["info"]


def _priority_emoji(priority: str) -> str:
    return {"P0": STATUS["p0"], "P1": STATUS["p1"], "P2": STATUS["info"]}.get(priority, STATUS["info"])


def _age(candidate: Candidate) -> str:
    posted_at = candidate.job.posted_at
    if not posted_at:
        return "freshness unknown"
    delta = datetime.now(timezone.utc) - posted_at
    hours = max(0, int(delta.total_seconds() // 3600))
    if hours < 1:
        return "just now"
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _experience_label(candidate: Candidate) -> str:
    raw = candidate.job.raw or {}
    for key in ("experience", "experience_range", "years"):
        value = raw.get(key)
        if value:
            return str(value)
    return "0-3 yrs target"


def _status_for_term(candidate: Candidate, term: str) -> str:
    matched = {item.lower() for item in candidate.score.matched_terms}
    lower = term.lower()
    if lower in matched:
        return "✅"
    if lower in {"kubernetes", "aws", "terraform", "mlops"}:
        return "🟡"
    return "⚠️"


def candidate_card(candidate: Candidate) -> str:
    job = candidate.job
    score = candidate.score
    priority, icon = priority_for_candidate(candidate)
    terms = score.matched_terms[:5] or ["Python", "Linux", "Docker"]
    term_lines = [f"{_status_for_term(candidate, term)} {term.title()}" for term in terms]
    warnings = score.warnings or candidate.filter_warnings
    human_path = "Recruiter found ⬜\nEmployee found ⬜"
    if (candidate.intelligence or {}).get("human_path"):
        human_path = "Recruiter found ✅\nEmployee found ✅"
    application = "Resume        ❌\nOutreach      ❌"
    reason = (candidate.intelligence or {}).get("reason") or "Strong deterministic fit. Human review required."

    return "\n".join(
        [
            f"{icon} {priority} JOB · {score.pre_score}/100",
            DIVIDER,
            "",
            job.company.upper(),
            job.title,
            "",
            f"📍 {job.location or 'Location unknown'}",
            f"🕐 {_age(candidate)}",
            f"💼 {_experience_label(candidate)}",
            "",
            *term_lines,
            "",
            "👥 Human Path",
            human_path,
            "",
            "📦 Application",
            application,
            "",
            f"💡 {reason}",
            *(["", "⚠️ " + "; ".join(warnings[:3])] if warnings else []),
        ]
    )


def inline_buttons(candidate: Candidate) -> dict[str, list[list[dict[str, str]]]]:
    key = candidate.job_key
    return keyboard(
        [
            [action("🚀 PREPARE APPLICATION", f"prepare:{key}")],
            [url_button("🌐 OPEN JOB", candidate.job.url), action("❌ SKIP", f"skip:{key}")],
            [action("🧠 WHY SCORE?", f"why:{key}"), action("📋 FULL JD", f"jd:{key}")],
            [action("👥 HUMAN PATH", f"people:{key}")],
        ]
    )


def home_card(snapshot: DashboardSnapshot) -> str:
    return "\n".join(
        [
            "🤖 SRI CAREER AGENT",
            DIVIDER,
            "",
            f"🔥 P0 Jobs          {snapshot.p0_jobs}",
            f"🟡 P1 Jobs          {snapshot.p1_jobs}",
            "",
            f"📨 Replies          {snapshot.replies}",
            f"🎯 Interviews       {snapshot.interviews}",
            f"⏰ Follow-ups       {snapshot.followups}",
            "",
            "Today",
            f"Applied             {snapshot.applied_today}",
            f"Outreach            {snapshot.outreach_today}",
            "",
            f"🧠 Claude: 🟢 {snapshot.claude_status}",
            f"🔄 Scan: {snapshot.scan_age}",
        ]
    )


def home_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("🔥 JOBS", "nav:jobs"), action("📨 INBOX", "nav:inbox")],
            [action("👥 NETWORK", "nav:network"), action("🎯 INTERVIEWS", "nav:interviews")],
            [action("📄 PIPELINE", "nav:pipeline"), action("⏰ FOLLOW-UPS", "nav:followups")],
            [action("📊 STATS", "nav:stats"), action("⚙️ MORE", "nav:more")],
        ]
    )


def job_queue_card(candidates: list[Candidate]) -> str:
    buckets = {"P0": 0, "P1": 0, "P2": 0}
    ranked = sorted(candidates, key=lambda item: item.score.pre_score, reverse=True)
    for candidate in ranked:
        priority, _ = priority_for_candidate(candidate)
        buckets[priority] = buckets.get(priority, 0) + 1
    next_candidate = ranked[0] if ranked else None
    lines = [
        "🔥 JOB QUEUE",
        DIVIDER,
        "",
        f"P0  {buckets.get('P0', 0)}",
        f"P1  {buckets.get('P1', 0)}",
        f"P2  {buckets.get('P2', 0)}",
    ]
    if next_candidate:
        terms = " + ".join(next_candidate.score.matched_terms[:3]) or "Deterministic fit"
        lines.extend(
            [
                "",
                "Next recommended:",
                "",
                next_candidate.job.company,
                next_candidate.job.title,
                f"{next_candidate.score.pre_score}/100 · {next_candidate.job.location or 'Location unknown'} · {_age(next_candidate)}",
                "",
                "Why:",
                terms,
                "Fresh posting / review-ready",
            ]
        )
    else:
        lines.extend(["", "No review-ready jobs yet."])
    return "\n".join(lines)


def job_queue_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("🔥 REVIEW P0", "jobs:review:p0")],
            [action("🟡 REVIEW P1", "jobs:review:p1")],
            [action("💾 SAVED", "jobs:saved"), action("✅ APPLIED", "jobs:applied")],
        ]
    )


def review_nav_buttons(candidate: Candidate) -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("⬅️ PREVIOUS", f"job:prev:{candidate.job_key}"), action("NEXT ➡️", f"job:next:{candidate.job_key}")],
            [action("🚀 PREPARE APPLICATION", f"prepare:{candidate.job_key}")],
            [url_button("🌐 OPEN JOB", candidate.job.url), action("❌ SKIP", f"skip:{candidate.job_key}")],
        ]
    )


def human_path_card(path: ContactPath) -> str:
    return "\n".join(
        [
            "👥 HUMAN PATH",
            DIVIDER,
            "",
            f"{path.company} · {path.role}",
            "",
            "⭐ BEST CONTACT",
            "",
            path.name,
            path.title,
            f"Confidence: {path.confidence.upper()}",
            "",
            "Why this person?",
            path.why,
            "",
            "Recommended angle:",
            path.angle,
            "",
            f"{path.index} / {path.total} potential contacts",
        ]
    )


def human_path_buttons(path: ContactPath) -> dict[str, list[list[dict[str, str]]]]:
    open_button = url_button("💼 OPEN LINKEDIN", path.linkedin_url) if path.linkedin_url else action("💼 OPEN LINKEDIN", "people:linkedin")
    email_button = url_button("✉️ EMAIL", f"mailto:{path.email}") if path.email else action("✉️ EMAIL", "people:email")
    return keyboard(
        [
            [action("💬 CREATE MESSAGE", "people:create-message")],
            [open_button],
            [email_button, action("✅ CONTACTED", "people:contacted")],
            [action("⏭ NEXT PERSON", "people:next")],
        ]
    )


def application_card(status: ApplicationStatus) -> str:
    return "\n".join(
        [
            f"📦 {status.state}",
            DIVIDER,
            "",
            status.company,
            status.role,
            "",
            f"Resume       {status.resume}",
            f"Email        {status.email}",
            f"LinkedIn     {status.linkedin}",
            f"Referral     {status.referral}",
        ]
    )


def application_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("📄 RESUME", "app:resume"), action("✉️ EMAIL", "app:email")],
            [action("💼 LINKEDIN", "app:linkedin"), action("🤝 REFERRAL", "app:referral")],
            [action("🌐 APPLY", "app:apply")],
            [action("✅ MARK APPLIED", "app:mark-applied")],
        ]
    )


def generated_message_buttons(prefix: str = "draft") -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("✏️ EDIT", f"{prefix}:edit"), action("🔄 REGENERATE", f"{prefix}:regenerate")],
            [action("📋 COPY", f"{prefix}:copy"), action("📨 OPEN GMAIL", f"{prefix}:gmail")],
            [action("✅ MARK SENT", f"{prefix}:sent")],
        ]
    )


def action_required_card(event: ActionRequired) -> str:
    return "\n".join(
        [
            "🚨 ACTION REQUIRED",
            DIVIDER,
            "",
            f"🎯 {event.title.upper()}",
            "",
            event.company,
            event.role,
            "",
            f"📅 {event.when}",
            f"⏱ {event.remaining}",
            "",
            event.note,
        ]
    )


def action_required_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("✍️ DRAFT REPLY", "action:draft-reply"), action("🎯 PREP INTERVIEW", "action:prep-interview")],
            [action("📨 VIEW EMAIL", "action:view-email"), action("📅 CALENDAR", "action:calendar")],
        ]
    )


def interview_mode_card(status: InterviewStatus) -> str:
    prep = status.preparation or {
        "Company research": "⬜",
        "JD mapping": "⬜",
        "Technical Qs": "⬜",
        "STAR stories": "⬜",
        "Weak areas": "⬜",
        "Questions to ask": "⬜",
    }
    lines = [
        "🎯 INTERVIEW MODE",
        DIVIDER,
        "",
        status.company.upper(),
        status.role,
        "",
        f"📅 {status.when}",
        f"⏱ {status.remaining}",
        "",
        "PREPARATION",
        "",
    ]
    lines.extend(f"{name:<22} {mark}" for name, mark in prep.items())
    lines.extend(["", f"Readiness: {status.readiness}%"])
    return "\n".join(lines)


def interview_mode_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("⚡ QUICK PREP", "interview:quick"), action("💻 TECHNICAL Qs", "interview:technical")],
            [action("⭐ STAR STORIES", "interview:star"), action("🏢 COMPANY", "interview:company")],
            [action("❓ QUESTIONS TO ASK", "interview:questions"), action("📄 SUBMITTED RESUME", "interview:resume")],
            [action("🎤 MOCK INTERVIEW", "interview:mock")],
        ]
    )


def follow_up_card(status: FollowUpStatus) -> str:
    active = "✅" if status.job_still_active else "❌"
    return "\n".join(
        [
            f"⏰ FOLLOW-UP · {status.index}/{status.total}",
            DIVIDER,
            "",
            status.name,
            status.title,
            "",
            "Initial outreach:",
            status.initial_outreach,
            "",
            "Days since contact:",
            str(status.days_since_contact),
            "",
            "Reply:",
            status.reply,
            "",
            f"Job still active: {active}",
            "",
            "Claude:",
            status.recommendation,
        ]
    )


def follow_up_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("✍️ GENERATE FOLLOW-UP", "followup:generate")],
            [action("✅ ALREADY SENT", "followup:sent"), action("⏭ SKIP", "followup:skip")],
            [action("🛑 STOP CONTACTING", "followup:stop")],
        ]
    )


def focus_card(items: list[FocusItem], recommendation: str) -> str:
    lines = ["🎯 WHAT SHOULD I DO NOW?", DIVIDER, ""]
    for index, item in enumerate(items[:5], start=1):
        lines.extend([f"{index}. {item.label}", f"   {item.detail}", ""])
    lines.extend(["Claude recommendation:", recommendation])
    return "\n".join(lines)


def focus_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("📨 HANDLE REPLY", "focus:reply")],
            [action("🔥 PREP P0 JOB", "focus:prep-p0"), action("⏰ FOLLOW-UP", "focus:followup")],
        ]
    )


def today_card(snapshot: DashboardSnapshot, interview: str | None = None) -> str:
    lines = [
        "☀️ TODAY",
        DIVIDER,
        "",
        "🔥 Review",
        f"{snapshot.p0_jobs} P0 jobs",
        "",
        "📨 Respond",
        f"{snapshot.replies} recruiter replies",
        "",
        "⏰ Follow-up",
        f"{snapshot.followups} contacts",
    ]
    if interview:
        lines.extend(["", "🎯 Interview", interview])
    lines.extend(["", "📄 Applications", "Prepared but not submitted", "", f"Estimated actions: {snapshot.p0_jobs + snapshot.replies + snapshot.followups + snapshot.interviews}"])
    return "\n".join(lines)


def today_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard([[action("▶️ START TODAY", "today:start")]])


def settings_card() -> str:
    return "\n".join(
        [
            "⚙️ SETTINGS",
            DIVIDER,
            "",
            "Job preferences",
            "Claude mode",
            "Notifications",
            "Scan frequency",
            "Outreach rules",
            "Follow-up rules",
            "Evidence bank",
            "Integrations",
            "System status",
        ]
    )


def settings_buttons() -> dict[str, list[list[dict[str, str]]]]:
    return keyboard(
        [
            [action("🎯 JOB PREFERENCES", "settings:jobs"), action("🧠 CLAUDE", "settings:claude")],
            [action("🔔 NOTIFICATIONS", "settings:notifications"), action("🔄 SCANS", "settings:scans")],
            [action("📚 EVIDENCE BANK", "settings:evidence"), action("🔌 INTEGRATIONS", "settings:integrations")],
            [action("🩺 SYSTEM HEALTH", "settings:health")],
        ]
    )


def compact_notification_card(priority: str, count: int, best_title: str, best_company: str, score: int) -> str:
    icon = _priority_emoji(priority.upper())
    return "\n".join(
        [
            f"{icon} {count} new {priority.upper()} jobs found",
            "",
            "Best:",
            f"{best_title} @ {best_company}",
            f"Score: {score}",
        ]
    )


def compact_notification_buttons(priority: str) -> dict[str, list[list[dict[str, str]]]]:
    return keyboard([[action(f"REVIEW {priority.upper()} JOBS", f"jobs:review:{priority.lower()}")]])


def demo_dashboard_messages(candidates: list[Candidate]) -> list[tuple[str, dict[str, Any]]]:
    ranked = sorted(candidates, key=lambda item: item.score.pre_score, reverse=True)
    p0 = sum(1 for item in ranked if priority_for_candidate(item)[0] == "P0")
    p1 = sum(1 for item in ranked if priority_for_candidate(item)[0] == "P1")
    top = ranked[0] if ranked else None
    snapshot = DashboardSnapshot(
        p0_jobs=p0,
        p1_jobs=p1,
        replies=1,
        interviews=1,
        followups=2,
        applied_today=3,
        outreach_today=5,
        scan_age="18m ago",
    )
    messages: list[tuple[str, dict[str, Any]]] = [
        (home_card(snapshot), home_buttons()),
        (job_queue_card(ranked), job_queue_buttons()),
        (today_card(snapshot, "Red Hat · Tomorrow 3 PM"), today_buttons()),
        (
            focus_card(
                [
                    FocusItem("Reply to recruiter", "Waiting 42m"),
                    FocusItem("Review best P0 job", "Fresh posting · high score"),
                    FocusItem("Follow up with Priya", "Due today"),
                ],
                "Handle the recruiter reply first, then prepare the best P0 job.",
            ),
            focus_buttons(),
        ),
    ]
    if top:
        messages.insert(2, (candidate_card(top), inline_buttons(top)))
        messages.append(
            (
                human_path_card(
                    ContactPath(
                        company=top.job.company,
                        role=top.job.title,
                        name="Priya Sharma",
                        title="Technical Recruiter",
                        confidence="high",
                        why="Likely recruiter or contact for engineering roles in India.",
                        angle="Python, Docker, Linux, and practical AI/Data project experience.",
                        index=1,
                        total=5,
                    )
                ),
                human_path_buttons(
                    ContactPath(
                        company=top.job.company,
                        role=top.job.title,
                        name="Priya Sharma",
                        title="Technical Recruiter",
                        confidence="high",
                        why="Likely recruiter or contact for engineering roles in India.",
                        angle="Python, Docker, Linux, and practical AI/Data project experience.",
                        index=1,
                        total=5,
                    )
                ),
            )
        )
        messages.append(
            (
                application_card(
                    ApplicationStatus(company=top.job.company, role=top.job.title, state="APPLICATION READY", resume="✅", email="✅", linkedin="✅", referral="✅")
                ),
                application_buttons(),
            )
        )
    messages.append((settings_card(), settings_buttons()))
    return messages
