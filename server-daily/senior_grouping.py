"""Match-specific senior tee selections and handicap adjustments."""
import re


def apply_senior_tees(members, game_date, selected_ids):
    if not isinstance(selected_ids, list) or any(not isinstance(id_, str) for id_ in selected_ids):
        raise ValueError("시니어티 사용자를 확인해주세요.")
    selected = set(selected_ids)
    match_year = int(game_date[:4])
    for member in members:
        birth = re.search(r"생년\s*:\s*(\d{4}|\d{2})년", member.pop("note", "") or "")
        year = int(birth[1]) if birth else match_year
        if birth and len(birth[1]) == 2:
            year += (match_year // 100 - (year > match_year % 100)) * 100
        member["senior"] = year <= 1958
        member["senior_tee"] = member["id"] in selected
        if member["senior_tee"]:
            if not member["senior"]:
                raise ValueError("시니어티는 생년이 등록된 1958년생 및 그 이전 출생 참가자만 선택할 수 있습니다.")
        selected.discard(member["id"])
    if selected:
        raise ValueError("경기 참가자 중에서 시니어티 사용자를 선택해주세요.")


def validate_senior_balance(groups):
    counts = [sum(bool(member.get("senior")) for member in group) for group in groups]
    if max(counts) - min(counts) > 1:
        raise ValueError("조별 시니어 인원 차이가 1명 이내가 되도록 배정해주세요.")
