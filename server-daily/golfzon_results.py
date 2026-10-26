"""Extract Golfzon leaderboard scores and match them to registered members."""
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request


SCHEMA = {
    "type": "object",
    "properties": {
        "game_headers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": ["string", "null"]},
                    "course": {"type": ["string", "null"]},
                },
                "required": ["date", "course"],
                "additionalProperties": False,
            },
        },
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string"},
                    "score": {"type": "number"},
                },
                "required": ["nickname", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["game_headers", "results"],
    "additionalProperties": False,
}


def normalize_nickname(value):
    return re.sub(r"[\s\u200b]+", "", str(value or "")).casefold()


def compare_game_headers(headers, game):
    """Compare every legible screenshot header with the selected game; missing data needs review."""
    expected_date = str(game.get("date", ""))
    expected_course = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(game.get("course", "")))).casefold()
    dates, courses = set(), set()
    for header in headers if isinstance(headers, list) else []:
        if not isinstance(header, dict):
            continue
        raw_date = str(header.get("date") or "")
        parts = re.findall(r"\d+", raw_date)
        if len(parts) >= 3 and len(parts[0]) == 4:
            try:
                dates.add(f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}")
            except ValueError:
                pass
        raw_course = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(header.get("course") or ""))).casefold()
        if raw_course:
            courses.add(raw_course)
    if any(value != expected_date for value in dates) or any(value != expected_course for value in courses):
        return {"status": "mismatch", "dates": sorted(dates), "courses": sorted(courses)}
    if expected_date in dates and expected_course in courses:
        return {"status": "match", "dates": sorted(dates), "courses": sorted(courses)}
    return {"status": "incomplete", "dates": sorted(dates), "courses": sorted(courses)}


def match_results(rows, participants):
    """Only attach a recognized score when its nickname uniquely identifies a participant."""
    by_nickname = {}
    for member in participants:
        for value in (member.get("nickname"), member.get("name")):
            key = normalize_nickname(value)
            if key:
                by_nickname.setdefault(key, []).append(member)
    matched, unmatched, used = [], [], {}
    for row in rows:
        nickname = str(row.get("nickname", "")).strip()
        score = row.get("score")
        if not nickname or type(score) not in (int, float) or not -100 <= score <= 300:
            continue
        candidates = by_nickname.get(normalize_nickname(nickname), [])
        unique = {member["id"]: member for member in candidates}
        if len(unique) != 1:
            unmatched.append({"nickname": nickname, "score": score})
            continue
        member = next(iter(unique.values()))
        if member["id"] in used:
            if used[member["id"]]["score"] == score:
                continue
            unmatched.append({"nickname": nickname, "score": score})
            continue
        result = {"member_id": member["id"], "name": member["name"],
                  "nickname": nickname, "score": score}
        used[member["id"]] = result
        matched.append(result)
    return {"matched": matched, "unmatched": unmatched}


def recognize_scores(data_urls, game, participants):
    api_key = os.environ.get("SMSG_OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI 연결 설정이 아직 없습니다. 관리자가 OpenAI API 키를 설정해야 합니다.")
    model = os.environ.get("SMSG_OPENAI_MODEL", "gpt-4.1-mini").strip()
    roster = [{"name": m["name"], "nickname": m.get("nickname", "")}
              for m in participants]
    if isinstance(data_urls, str):
        data_urls = [data_urls]
    content = [{"type": "input_text", "text": json.dumps({
        "game_date": game["date"], "course": game["course"],
        "registered_participants": roster,
    }, ensure_ascii=False)}]
    content.extend({"type": "input_image", "image_url": data_url, "detail": "high"}
                   for data_url in data_urls)
    payload = {
        "model": model,
        "store": False,
        "instructions": (
            "Read the Golfzon golf round leaderboard screenshot(s). Extract any visible round header date and golf course name into game_headers. "
            "Normalize dates to YYYY-MM-DD. If multiple screenshots contain differing round headers, include each distinct header. Use null for a header field that is not visible or legible. "
            "Also extract each visible player's exact displayed nickname and their final stroke-play score relative to par. "
            "A displayed +4 is numeric 4, E or even par is 0, and -2 is numeric -2. Do not extract rank, handicap, or hole-by-hole strokes. "
            "Use the supplied participant roster to disambiguate visually similar names, but preserve the exact displayed nickname. "
            "Include only rows where both nickname and final score are clearly legible. Never guess unclear digits or names. "
            "The screenshot may show only part of the leaderboard; extract all clearly visible rows."
        ),
        "input": [{"role": "user", "content": content}],
        "text": {"format": {"type": "json_schema", "name": "golfzon_results",
                             "strict": True, "schema": SCHEMA}},
        "max_output_tokens": 2500,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("AI 인증 설정을 확인해주세요.") from None
        raise RuntimeError("스크린샷을 분석하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("스크린샷을 분석하지 못했습니다. 잠시 후 다시 시도해주세요.") from None
    text = next((part.get("text", "") for item in result.get("output", [])
                 for part in item.get("content", []) if part.get("type") == "output_text"), "")
    try:
        extracted = json.loads(text)
        rows = extracted["results"]
        headers = extracted["game_headers"]
    except (TypeError, ValueError, KeyError):
        raise RuntimeError("결과표를 읽지 못했습니다. 더 선명한 스크린샷으로 다시 시도해주세요.") from None
    return {**match_results(rows, participants), "game_headers": headers}
