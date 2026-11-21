"""Search Kakao Local for restaurant listings."""
import json
import os
import urllib.parse
import urllib.request


PAGE_LIMIT = 3


def search_restaurants(neighborhood, page):
    key = os.environ.get("SMSG_KAKAO_REST_API_KEY", "").strip()
    if not key:
        raise RuntimeError("관리자가 카카오 REST API 키를 설정해야 합니다.")

    query = urllib.parse.urlencode({
        "query": f"{neighborhood} 맛집",
        "category_group_code": "FD6",
        "page": page,
        "size": 15,
    })
    request = urllib.request.Request(
        f"https://dapi.kakao.com/v2/local/search/keyword.json?{query}",
        headers={"Authorization": f"KakaoAK {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
        places = [
            {
                "id": place["id"],
                "name": place["place_name"],
                "category": place["category_name"].split(" > ")[-1],
                "address": place["road_address_name"] or place["address_name"],
                "phone": place["phone"],
            }
            for place in result["documents"] if place["id"].isascii() and place["id"].isdigit()
        ]
        return {"places": places, "has_more": page < PAGE_LIMIT and not result["meta"]["is_end"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise RuntimeError("카카오맵 검색에 실패했습니다. 잠시 후 다시 시도해주세요.") from None
