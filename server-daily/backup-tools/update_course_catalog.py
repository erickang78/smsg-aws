#!/usr/bin/env python3
"""Refresh the SMSG course search catalog from Golfzon's public course API."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://lobby.golfzon.com/v1/dotcom/courses/course/search/list"
SOURCE = "https://www.golfzon.com/course/main"
PAGE_SIZE = 100


def fetch_page(page):
    query = urlencode({
        "page": page,
        "size": PAGE_SIZE,
        "softwareType": 0,
        "orderType": 1,
        "searchWord": "",
        "ciVersion": 0,
        "areaNo": 0,
    })
    request = Request(API + "?" + query, headers={
        "Accept": "application/json",
        "User-Agent": "SMSG course catalog updater/1.0",
        "Origin": "https://www.golfzon.com",
        "Referer": SOURCE,
    })
    with urlopen(request, timeout=30) as response:
        rows = json.loads(response.read())
        total = response.headers.get("X-TOTAL_COUNT") or response.headers.get("x-total_count")
    if not isinstance(rows, list) or not total:
        raise RuntimeError("unexpected_course_list_response")
    return int(total), rows


def collect_courses():
    total, first_page = fetch_page(1)
    if total < 1 or not first_page:
        raise RuntimeError("empty_course_list")
    rows = list(first_page)
    page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for page in range(2, page_count + 1):
        time.sleep(0.15)
        page_total, page_rows = fetch_page(page)
        if page_total != total:
            raise RuntimeError("course_count_changed_during_refresh")
        rows.extend(page_rows)
    courses = []
    seen = set()
    for row in rows:
        course_id = int(row["ciCode"])
        if course_id in seen:
            raise RuntimeError("duplicate_course_id")
        seen.add(course_id)
        courses.append({
            "id": course_id,
            "name": str(row.get("ccName") or "").strip(),
            "region": str(row.get("address") or "기타").strip(),
            "course_difficulty": round(float(row.get("difficultyCc") or 0) / 2, 1),
            "green_difficulty": round(float(row.get("difficultyGreen") or 0) / 2, 1),
        })
    if len(courses) != total or any(not course["name"] for course in courses):
        raise RuntimeError("incomplete_course_list")
    return courses


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".golfzon-courses-", delete=False) as tmp:
        temp_path = Path(tmp.name)
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    temp_path.chmod(0o644)
    os.replace(temp_path, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_path = root / "golfzon-courses.json"
    backup_dir = root / "backups" / "course-catalog"
    status_path = root / "backups" / "course-catalog-status.json"
    started = dt.datetime.now(dt.timezone.utc)
    try:
        courses = collect_courses()
        payload = {
            "source": SOURCE,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "courses": courses,
        }
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
        backup_dir.mkdir(parents=True, exist_ok=True)
        if catalog_path.exists():
            stamp = started.strftime("%Y%m%dT%H%M%SZ")
            backup_path = backup_dir / f"golfzon-courses-{stamp}.json"
            backup_path.write_bytes(catalog_path.read_bytes())
            backup_path.chmod(0o600)
            cutoff = time.time() - 30 * 86400
            for old in backup_dir.glob("golfzon-courses-*.json"):
                if old.stat().st_mtime < cutoff:
                    old.unlink()
        atomic_write(catalog_path, payload)
        status = {
            "ok": True,
            "last_success": payload["updated_at"],
            "course_count": len(courses),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except Exception as error:
        status = {
            "ok": False,
            "last_attempt": started.isoformat(),
            "error_type": type(error).__name__,
        }
        atomic_write(status_path, status)
        raise
    atomic_write(status_path, status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
