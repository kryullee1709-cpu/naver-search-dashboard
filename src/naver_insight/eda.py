"""수집 결과를 EDA 가능한 형태로 정규화하고 기초 통계를 계산한다."""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd

from .settings import SEARCH_ENDPOINTS

TAG_RE = re.compile(r"<[^>]+>")

# 조사·접속사 등 분석에 의미가 적은 토큰
STOPWORDS = {
    "그리고", "하지만", "그러나", "이런", "저런", "그런", "합니다", "입니다", "있습니다",
    "위해", "대한", "통해", "관련", "지난", "오늘", "내일", "우리", "가장", "다시",
    "때문", "에서", "으로", "하는", "했다", "한다", "된다", "되는", "있는", "없는",
    "the", "and", "for", "with", "this", "that", "from", "you", "are", "was",
}

# 검색 결과에 날짜 필드가 있는 엔드포인트만 기간 필터가 실제로 적용된다.
DATE_FIELDS = {"news": "pubDate", "blog": "postdate"}


def strip_tags(text: str | None) -> str:
    if not text:
        return ""
    # 응답은 검색어를 <b> 태그로 감싸며(공식 문서), &quot; 같은 엔티티도 섞여 온다.
    return TAG_RE.sub("", html.unescape(str(text))).strip()


def _parse_date(endpoint: str, item: dict) -> pd.Timestamp | None:
    field = DATE_FIELDS.get(endpoint)
    if not field:
        return None
    raw = item.get(field)
    if not raw:
        return None
    if endpoint == "blog":  # YYYYMMDD
        return pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
    parsed = pd.to_datetime(raw, errors="coerce", utc=True)  # RFC 1123
    if pd.isna(parsed):
        return None
    return parsed.tz_convert("Asia/Seoul").tz_localize(None)


def _domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url or "")
    return match.group(1).replace("www.", "") if match else "(미상)"


def _source_of(endpoint: str, item: dict) -> str:
    """채널별 출처(도메인·블로거·카페명 등)를 뽑아낸다."""
    if endpoint == "blog":
        return strip_tags(item.get("bloggername")) or "(미상)"
    if endpoint == "cafearticle":
        return strip_tags(item.get("cafename")) or "(미상)"
    if endpoint == "local":
        return strip_tags(item.get("category")) or "(미상)"
    if endpoint == "news":
        return _domain(item.get("originallink") or item.get("link") or "")
    return _domain(item.get("link") or "")


COLUMNS = [
    "keyword", "endpoint", "channel", "rank", "title", "description",
    "link", "source", "published_at", "total", "raw",
]


def to_dataframe(results: list) -> pd.DataFrame:
    """SearchResult 리스트를 하나의 tidy DataFrame으로 변환."""
    rows: list[dict] = []
    for result in results:
        spec = SEARCH_ENDPOINTS[result.endpoint]
        for rank, item in enumerate(result.items, start=1):
            rows.append(
                {
                    "keyword": result.keyword,
                    "endpoint": result.endpoint,
                    "channel": spec.label,
                    "rank": rank,
                    "title": strip_tags(item.get("title")),
                    "description": strip_tags(item.get("description")),
                    "link": item.get("link") or item.get("originallink") or "",
                    "source": _source_of(result.endpoint, item),
                    "published_at": _parse_date(result.endpoint, item),
                    "total": result.total,
                    "raw": item,
                }
            )
    if not rows:
        return pd.DataFrame(columns=COLUMNS + ["text"])
    df = pd.DataFrame(rows)
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df["text"] = (df["title"] + " " + df["description"]).str.strip()
    return df


def filter_by_period(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """날짜 정보가 있는 채널만 기간으로 거르고, 없는 채널은 그대로 유지한다."""
    if df.empty:
        return df
    has_date = df["published_at"].notna()
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    in_range = df["published_at"].between(start_ts, end_ts)
    return df[~has_date | in_range].copy()


def channel_summary(df: pd.DataFrame) -> pd.DataFrame:
    """검색어 × 채널 문서량 요약 (전체검색건수 = API가 보고한 total)."""
    if df.empty:
        return pd.DataFrame(columns=["keyword", "channel", "수집건수", "전체검색건수"])
    return (
        df.groupby(["keyword", "channel"], as_index=False)
        .agg(수집건수=("title", "count"), 전체검색건수=("total", "max"))
        .sort_values(["keyword", "전체검색건수"], ascending=[True, False])
    )


def share_of_voice(df: pd.DataFrame) -> pd.DataFrame:
    """채널별 노출 점유율(SOV).

    채널마다 모집단 규모가 3~5자릿수 차이 나므로(웹문서 수백만 vs 지역 수건)
    채널을 가로질러 합산하지 않는다. 점유율은 **채널 안에서** 계산한다.
    """
    if df.empty:
        return pd.DataFrame(columns=["channel", "keyword", "전체검색건수", "점유율(%)"])
    per = (
        df.groupby(["channel", "keyword"])["total"].max().reset_index()
        .rename(columns={"total": "전체검색건수"})
    )
    denom = per.groupby("channel")["전체검색건수"].transform("sum")
    per["점유율(%)"] = (per["전체검색건수"] / denom * 100).round(2).fillna(0.0)
    return per.sort_values(["channel", "전체검색건수"], ascending=[True, False])


def sov_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """채널 × 검색어 점유율 행렬 — 채널마다 강한 검색어가 다른지 한눈에 본다."""
    sov = share_of_voice(df)
    if sov.empty:
        return pd.DataFrame()
    return sov.pivot(index="channel", columns="keyword", values="점유율(%)").fillna(0.0)


def volume_timeseries(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """날짜가 있는 채널(뉴스·블로그)의 발행량 시계열."""
    dated = df[df["published_at"].notna()]
    if dated.empty:
        return pd.DataFrame(columns=["date", "keyword", "channel", "count"])
    return (
        dated.assign(date=dated["published_at"].dt.to_period(freq).dt.start_time)
        .groupby(["date", "keyword", "channel"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )


def top_sources(df: pd.DataFrame, limit: int = 15) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["keyword", "source", "count"])
    return (
        df[df["source"] != "(미상)"]
        .groupby(["keyword", "source"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
        .groupby("keyword", group_keys=False)
        .head(limit)
    )


def keyword_tokens(
    df: pd.DataFrame, keyword: str | None = None, limit: int = 30, min_len: int = 2
) -> pd.DataFrame:
    """제목·요약에서 연관어 빈도를 뽑는다(형태소 분석기 없이 단순 토큰화)."""
    target = df if keyword is None else df[df["keyword"] == keyword]
    if target.empty:
        return pd.DataFrame(columns=["token", "count"])
    own = {t.lower() for k in target["keyword"].unique() for t in re.split(r"\s+", str(k)) if t}
    counter: Counter = Counter()
    for text in target["text"].fillna(""):
        for token in re.findall(r"[가-힣A-Za-z0-9]+", str(text)):
            low = token.lower()
            if len(token) < min_len or low in STOPWORDS or low in own or token.isdigit():
                continue
            counter[token] += 1
    return pd.DataFrame(counter.most_common(limit), columns=["token", "count"])


def trend_to_dataframe(payload: dict) -> pd.DataFrame:
    """검색어 트렌드 응답을 tidy DataFrame으로 변환."""
    rows = []
    for group in payload.get("results", []) or []:
        title = group.get("title")
        for point in group.get("data", []) or []:
            rows.append(
                {
                    "group": title,
                    "period": pd.to_datetime(point.get("period"), errors="coerce"),
                    "ratio": float(point.get("ratio", 0) or 0),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["group", "period", "ratio"])
    return pd.DataFrame(rows).sort_values(["group", "period"])


def trend_stats(trend_df: pd.DataFrame) -> pd.DataFrame:
    """그룹별 트렌드 기초 통계 + 전·후반 변화율."""
    if trend_df.empty:
        return pd.DataFrame(columns=["group", "평균", "최대", "최소", "표준편차", "변화율(%)"])
    rows = []
    for group, part in trend_df.groupby("group"):
        series = part.sort_values("period")["ratio"]
        half = max(len(series) // 2, 1)
        first, second = series.iloc[:half].mean(), series.iloc[half:].mean()
        change = ((second - first) / first * 100) if first else 0.0
        rows.append(
            {
                "group": group,
                "평균": round(series.mean(), 2),
                "최대": round(series.max(), 2),
                "최소": round(series.min(), 2),
                "표준편차": round(series.std(ddof=0), 2),
                "변화율(%)": round(change, 2),
            }
        )
    return pd.DataFrame(rows).sort_values("평균", ascending=False)


def split_windows(trend_df: pd.DataFrame, boundary: date) -> pd.DataFrame:
    """트렌드 결과를 직전 구간 / 현재 구간으로 나눈다.

    boundary(=현재 구간 시작일) 이전이면 '직전', 이후면 '현재'.
    한 번의 요청으로 받은 데이터라 두 구간의 ratio 는 같은 기준으로 정규화되어
    있고, 따라서 서로 비교할 수 있다.
    """
    if trend_df.empty:
        return trend_df.assign(구간=pd.Series(dtype=str))
    out = trend_df.copy()
    out["구간"] = np.where(out["period"] < pd.Timestamp(boundary), "직전", "현재")
    return out


def compare_windows(trend_df: pd.DataFrame, boundary: date) -> pd.DataFrame:
    """검색어별 직전 구간 대비 증감률."""
    split = split_windows(trend_df, boundary)
    if split.empty or split["구간"].nunique() < 2:
        return pd.DataFrame(
            columns=["group", "직전 평균", "현재 평균", "증감률(%)", "직전 최대", "현재 최대"]
        )
    rows = []
    for group, part in split.groupby("group"):
        before = part.loc[part["구간"] == "직전", "ratio"]
        after = part.loc[part["구간"] == "현재", "ratio"]
        if before.empty or after.empty:
            continue
        prev_mean, cur_mean = before.mean(), after.mean()
        change = ((cur_mean - prev_mean) / prev_mean * 100) if prev_mean else 0.0
        rows.append(
            {
                "group": group,
                "직전 평균": round(float(prev_mean), 2),
                "현재 평균": round(float(cur_mean), 2),
                "증감률(%)": round(float(change), 1),
                "직전 최대": round(float(before.max()), 2),
                "현재 최대": round(float(after.max()), 2),
            }
        )
    return pd.DataFrame(rows).sort_values("증감률(%)", ascending=False)
