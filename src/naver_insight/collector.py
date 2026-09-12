"""여러 검색어 × 여러 채널을 순회하며 수집하는 오케스트레이션 계층."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .client import NaverApiError, NaverClient, SearchResult
from .settings import (
    CACHE_DIR,
    SEARCH_ENDPOINTS,
    TREND_MAX_GROUPS,
    TREND_MAX_KEYWORDS_PER_GROUP,
)

ProgressFn = Callable[[float, str], None]


@dataclass
class CollectionReport:
    results: list[SearchResult]
    errors: list[str]


def parse_keywords(raw: str, limit: int = 20) -> list[str]:
    """쉼표로 구분된 입력을 정규화한다(중복·공백 제거, 순서 유지)."""
    seen: list[str] = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        kw = chunk.strip()
        if kw and kw not in seen:
            seen.append(kw)
    return seen[:limit]


def collect_search(
    client: NaverClient,
    keywords: Iterable[str],
    endpoints: Iterable[str],
    per_call: int = 100,
    sort_map: dict[str, str] | None = None,
    progress: ProgressFn | None = None,
) -> CollectionReport:
    keywords = list(keywords)
    endpoints = [e for e in endpoints if e in SEARCH_ENDPOINTS]
    total_jobs = max(len(keywords) * len(endpoints), 1)
    results: list[SearchResult] = []
    errors: list[str] = []
    done = 0

    for keyword in keywords:
        for endpoint in endpoints:
            spec = SEARCH_ENDPOINTS[endpoint]
            if progress:
                progress(done / total_jobs, f"{keyword} · {spec.label} 수집 중…")
            try:
                results.append(
                    client.search_paged(
                        endpoint,
                        keyword,
                        target=min(per_call, spec.max_display * 3),
                        sort=(sort_map or {}).get(endpoint),
                    )
                )
            except NaverApiError as exc:
                errors.append(f"[{keyword} · {spec.label}] {exc}")
            done += 1

    if progress:
        progress(1.0, "수집 완료")
    return CollectionReport(results=results, errors=errors)


def build_keyword_groups(keywords: Iterable[str]) -> list[dict]:
    """검색어 1개 = 트렌드 그룹 1개. 공식 문서 제약(최대 5그룹)을 지킨다."""
    groups = []
    for keyword in list(keywords)[:TREND_MAX_GROUPS]:
        groups.append(
            {
                "groupName": keyword,
                "keywords": [keyword][:TREND_MAX_KEYWORDS_PER_GROUP],
            }
        )
    return groups


# 검색어 트렌드가 제공하는 가장 이른 날짜 (공식 문서)
TREND_MIN_DATE = date(2016, 1, 1)


def previous_window(start: date, end: date) -> tuple[date, date]:
    """현재 구간 바로 앞의, 길이가 같은 구간을 돌려준다.

    2016-01-01 이전은 API가 400을 돌려주므로 하한에서 자른다.
    """
    span = (end - start).days
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span)
    if prev_start < TREND_MIN_DATE:
        prev_start = TREND_MIN_DATE
    return prev_start, prev_end


def collect_trend(
    client: NaverClient,
    keywords: Iterable[str],
    start: date,
    end: date,
    time_unit: str = "date",
    device: str = "",
    gender: str = "",
    ages: list[str] | None = None,
    with_comparison: bool = False,
) -> tuple[dict | None, str | None]:
    groups = build_keyword_groups(keywords)
    if not groups:
        return None, "검색어가 없습니다."

    # 직전 기간과 비교하려면 두 구간을 **한 번에** 조회해야 한다.
    # ratio 는 요청 구간 안에서 최대값을 100으로 정규화하므로, 구간을 따로
    # 호출하면 각자 100을 갖게 되어 서로 비교할 수 없다.
    query_start = start
    if with_comparison:
        query_start = previous_window(start, end)[0]

    try:
        payload = client.search_trend(
            start_date=query_start.isoformat(),
            end_date=end.isoformat(),
            keyword_groups=groups,
            time_unit=time_unit,
            device=device,
            gender=gender,
            ages=ages,
        )
        return payload, None
    except NaverApiError as exc:
        return None, str(exc)


def save_snapshot(name: str, payload: dict) -> Path:
    """수집 결과 스냅샷을 data/cache 에 저장한다."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def list_snapshots() -> list[Path]:
    """저장된 스냅샷을 최신순으로 돌려준다."""
    if not CACHE_DIR.exists():
        return []
    return sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_snapshot(name: str) -> dict:
    path = CACHE_DIR / name if name.endswith(".json") else CACHE_DIR / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
