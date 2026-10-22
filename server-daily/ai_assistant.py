"""Privacy-minimizing natural-language queries for the SMSG ledger."""
import json
import os
import re
import urllib.error
import urllib.request


INTENTS = (
    "member_count", "attendance_absent", "attendance_ranking",
    "handicap_ranking", "meal_summary", "meal_balance",
    "game_count", "upcoming_games", "unsupported",
)

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "months": {"type": ["integer", "null"]},
        "year": {"type": ["integer", "null"]},
        "limit": {"type": "integer"},
        "order": {"type": "string", "enum": ["high", "low"]},
    },
    "required": ["intent", "months", "year", "limit", "order"],
    "additionalProperties": False,
}


def classify_question(question, today):
    """Classify clearly supported questions deterministically, otherwise ask the model."""
    normalized = re.sub(r"\s+", "", question).lower()
    limit_match = re.search(r"(\d{1,2})\s*(?:명|개(?!월)|위)", question)
    limit = max(1, min(20, int(limit_match.group(1)))) if limit_match else 10
    period_match = re.search(r"최근\s*(\d{1,2})\s*개월", question)
    months = max(1, min(12, int(period_match.group(1)))) if period_match else None
    year_match = re.search(r"(20\d{2})\s*년", question)
    year = int(year_match.group(1)) if year_match else None
    absent_terms = ("미참석", "불참", "참석안한", "참석하지않", "참석기록이없는", "참석기록없는", "결과기록이없는")
    if any(term in normalized for term in absent_terms):
        intent = "attendance_absent"
    elif "참석" in normalized and any(term in normalized for term in ("순위", "순", "많", "적", "횟수", "랭킹")):
        intent = "attendance_ranking"
    elif "핸디" in normalized and any(term in normalized for term in ("순위", "순", "낮", "높", "랭킹")):
        intent = "handicap_ranking"
    elif any(term in normalized for term in ("회원수", "몇명", "멤버수")):
        intent = "member_count"
    elif any(term in normalized for term in ("잔액", "남은돈", "얼마있")):
        intent = "meal_balance"
    elif "식대" in normalized and any(term in normalized for term in ("수입", "지출", "정산", "합계")):
        intent = "meal_summary"
    elif "경기" in normalized and any(term in normalized for term in ("예정", "앞으로", "일정")):
        intent = "upcoming_games"
    elif "경기" in normalized and any(term in normalized for term in ("몇개", "몇건", "몇번", "수", "횟수")):
        intent = "game_count"
    else:
        intent = None
    if intent:
        return {"intent": intent, "months": months, "year": year, "limit": limit,
                "order": "low" if any(term in normalized for term in ("낮은", "적은", "최저")) else "high"}

    api_key = os.environ.get("SMSG_OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI 연결 설정이 아직 없습니다. 관리자가 OpenAI API 키를 설정해야 합니다.")
    model = os.environ.get("SMSG_OPENAI_MODEL", "gpt-4.1-mini").strip()
    payload = {
        "model": model,
        "store": False,
        "instructions": (
            "Classify the Korean user question into exactly one safe read-only ledger intent. "
            "Return only the required JSON. Never infer or invent ledger facts. "
            "months must be 1..12 only when a period is requested, otherwise null. "
            "year is a four digit year only when explicitly requested, otherwise null. "
            "limit must be between 1 and 20. order is high unless the user asks for low. "
            "attendance_ranking means ranking by recorded attendance counts. Use attendance_absent only when the user explicitly asks who did not attend or has no attendance/result record. "
            "Use attendance_absent for members with no recorded game result in a recent period; "
            "meal_summary for meal income/expense/settlement totals; meal_balance for balance; "
            "game_count for game counts; upcoming_games for future scheduled games. "
            "If the question is not about supported records, use unsupported. "
            f"Current Korea date: {today}."
        ),
        "input": [{"role": "user", "content": question}],
        "text": {"format": {"type": "json_schema", "name": "ledger_query", "strict": True, "schema": SCHEMA}},
        "max_output_tokens": 120,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("AI 인증 설정을 확인해주세요.") from None
        raise RuntimeError("AI에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("AI에 연결하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    text = next((part.get("text", "") for item in result.get("output", [])
                 for part in item.get("content", []) if part.get("type") == "output_text"), "")
    try:
        plan = json.loads(text)
    except (TypeError, ValueError):
        raise RuntimeError("질문을 분류하지 못했습니다. 표현을 바꿔 다시 물어봐주세요.") from None
    if not isinstance(plan, dict):
        raise RuntimeError("질문을 분류하지 못했습니다. 표현을 바꿔 다시 물어봐주세요.")
    if plan.get("intent") not in INTENTS:
        plan["intent"] = "unsupported"
    plan["months"] = plan.get("months") if type(plan.get("months")) is int and 1 <= plan["months"] <= 12 else None
    plan["year"] = plan.get("year") if type(plan.get("year")) is int and 2000 <= plan["year"] <= 2100 else None
    plan["limit"] = max(1, min(20, plan.get("limit", 10) if type(plan.get("limit")) is int else 10))
    plan["order"] = "low" if plan.get("order") == "low" else "high"
    return plan


def answer_question(c, question, today):
    """Resolve a constrained intent locally and formulate a factual answer."""
    from datetime import date, timedelta
    plan = classify_question(question, today)
    intent, limit, order = plan["intent"], plan["limit"], plan["order"]
    if intent == "unsupported":
        return "회원 수, 최근 미참석 회원, 참석 횟수, 핸디, 식대 합계·잔액, 경기 일정에 관해 물어볼 수 있어요."
    if intent == "member_count":
        n = c.execute("SELECT COUNT(*) FROM members WHERE active=1").fetchone()[0]
        return f"현재 활동 회원은 {n}명입니다."
    if intent == "attendance_absent":
        months = plan["months"] or 3
        now = date.fromisoformat(today)
        month = now.month - months
        year = now.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        import calendar
        start = now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1])).isoformat()
        rows = c.execute("""SELECT m.name, COUNT(g.id) AS n
            FROM members m LEFT JOIN game_results r ON r.member_id=m.id
            LEFT JOIN games g ON g.id=r.game_id AND g.date>=? AND g.date<=?
            WHERE m.active=1 GROUP BY m.id ORDER BY m.name""", (start, today)).fetchall()
        names = [r["name"] for r in rows if r["n"] == 0]
        return f"최근 {months}개월 동안 결과 기록이 없는 회원은 {len(names)}명입니다." + ("\n" + " · ".join(names) if names else "")
    if intent == "attendance_ranking":
        rows = c.execute("""SELECT m.name, COUNT(r.game_id) AS n FROM members m
            LEFT JOIN game_results r ON r.member_id=m.id WHERE m.active=1
            GROUP BY m.id ORDER BY n """ + ("ASC" if order == "low" else "DESC") + ", m.name LIMIT ?", (limit,)).fetchall()
        title = "참석 기록이 적은 회원" if order == "low" else "참석 기록이 많은 회원"
        return title + ":\n" + "\n".join(f"{i}. {r['name']} · {r['n']}회" for i, r in enumerate(rows, 1))
    if intent == "handicap_ranking":
        import app
        members = []
        for row in c.execute("SELECT id,name FROM members WHERE active=1"):
            score = app.recalculate_handicap(c, row["id"])
            members.append((row["name"], score["handicap"], score["basis"]))
        members.sort(key=lambda item: (item[1], item[0]), reverse=order == "high")
        title = "핸디가 높은 회원" if order == "high" else "핸디가 낮은 회원"
        return title + ":\n" + "\n".join(f"{i}. {name} · {hd:.1f} ({basis})" for i, (name, hd, basis) in enumerate(members[:limit], 1))
    if intent in ("meal_summary", "meal_balance"):
        year = plan["year"] or date.fromisoformat(today).year
        row = c.execute("SELECT COUNT(*) n, COALESCE(SUM(income),0) income, COALESCE(SUM(expense),0) expense, COALESCE(SUM(extra),0) extra FROM meals WHERE date LIKE ?", (f"{year}-%",)).fetchone()
        if intent == "meal_balance":
            opening = int(c.execute("SELECT value FROM settings WHERE id='opening'").fetchone()[0])
            change = c.execute("SELECT COALESCE(SUM(income-expense+extra),0) FROM meals").fetchone()[0]
            current_balance = opening + change
            return f"현재 식대 장부 잔액은 {current_balance:,}원입니다."
        return (f"{year}년 식대 기록 {row['n']}건\n"
                f"수입 {row['income']:,}원 · 지출 {row['expense']:,}원 · "
                f"정산 {row['income']-row['expense']:,}원 · 캐시백/이자 {row['extra']:,}원")
    if intent == "game_count":
        months = plan["months"]
        if months:
            start = (date.fromisoformat(today) - timedelta(days=round(months * 30.4375))).isoformat()
            n = c.execute("SELECT COUNT(*) FROM games WHERE date>=? AND date<=?", (start, today)).fetchone()[0]
            return f"최근 {months}개월 동안 등록된 경기는 {n}건입니다."
        year = plan["year"] or date.fromisoformat(today).year
        n = c.execute("SELECT COUNT(*) FROM games WHERE date LIKE ?", (f"{year}-%",)).fetchone()[0]
        return f"{year}년 등록된 경기는 {n}건입니다."
    if intent == "upcoming_games":
        rows = c.execute("SELECT date,course,(SELECT COUNT(*) FROM game_participants p WHERE p.game_id=g.id) AS n FROM games g WHERE date>=? ORDER BY date LIMIT ?", (today, limit)).fetchall()
        if not rows:
            return "예정된 경기가 없습니다."
        return "예정 경기:\n" + "\n".join(f"{r['date']} · {r['course']} · {r['n']}명 참석" for r in rows)
    return "이 질문은 아직 답할 수 없어요. 회원, 경기, 식대 기록에 관해 물어봐주세요."
