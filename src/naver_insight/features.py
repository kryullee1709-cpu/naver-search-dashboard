"""채널별 파생 변수와 한국어 명사 추출.

- 공통: 제목·요약 길이, 단어 수, 랭크 구간
- 뉴스/블로그: 요일·시간대
- 이미지: 가로/세로/화소수/종횡비 (API가 문자열로 주므로 숫자 변환)
- 지역: WGS84 좌표 (mapx/mapy 는 실제 좌표 x 10^7 정수 문자열)
"""

from __future__ import annotations

import functools
import re

import pandas as pd

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 명사이지만 분석에 의미가 적은 것들
NOUN_STOPWORDS = {
    "것", "수", "때", "곳", "등", "중", "위", "안", "말", "년", "월", "일", "시",
    "분", "개", "명", "번", "점", "주", "가지", "정도", "경우", "관련", "이번",
    "지난", "오늘", "내일", "우리", "저희", "여기", "거기", "네이버", "블로그",
    "포스팅", "글", "사진", "이미지", "정보", "내용", "소개", "추천",
}


@functools.lru_cache(maxsize=1)
def _kiwi():
    """Kiwi 인스턴스는 초기화 비용이 커서 한 번만 만든다."""
    try:
        from kiwipiepy import Kiwi

        return Kiwi()
    except Exception:  # 설치 실패 시 정규식 토큰화로 자동 강등
        return None


def extract_nouns(texts, min_len: int = 2, exclude: set[str] | None = None) -> list[str]:
    """형태소 분석으로 명사만 뽑는다. Kiwi 를 못 쓰면 정규식으로 강등한다."""
    exclude = {e.lower() for e in (exclude or set())}
    kiwi = _kiwi()
    joined = [str(t) for t in texts if t]

    nouns: list[str] = []
    if kiwi is not None:
        for _, tokens in zip(joined, kiwi.tokenize(joined)):
            for token in tokens:
                # NNG 일반명사, NNP 고유명사, SL 외국어
                if token.tag in ("NNG", "NNP", "SL") and len(token.form) >= min_len:
                    nouns.append(token.form)
    else:
        for text in joined:
            nouns.extend(t for t in re.findall(r"[가-힣A-Za-z0-9]+", text) if len(t) >= min_len)

    return [
        n for n in nouns
        if n not in NOUN_STOPWORDS and n.lower() not in exclude and not n.isdigit()
    ]


def noun_counts(
    df: pd.DataFrame, limit: int = 25, exclude_keywords: bool = True
) -> pd.DataFrame:
    """제목·요약에서 명사 빈도표를 만든다."""
    if df.empty or "text" not in df.columns:
        return pd.DataFrame(columns=["명사", "빈도"])
    exclude = set()
    if exclude_keywords:
        for kw in df["keyword"].unique():
            exclude.update(re.split(r"\s+", str(kw)))
    nouns = extract_nouns(df["text"].fillna("").tolist(), exclude=exclude)
    if not nouns:
        return pd.DataFrame(columns=["명사", "빈도"])
    counts = pd.Series(nouns).value_counts().head(limit)
    return counts.rename_axis("명사").reset_index(name="빈도")


def noun_set(df: pd.DataFrame, limit: int = 100) -> set[str]:
    """자카드 비교용 상위 명사 집합."""
    table = noun_counts(df, limit=limit)
    return set(table["명사"]) if not table.empty else set()


def add_common_features(df: pd.DataFrame, rank_bins: int = 5) -> pd.DataFrame:
    """모든 채널에 공통으로 붙는 파생 변수."""
    if df.empty:
        return df
    out = df.copy()
    out["제목길이"] = out["title"].fillna("").str.len()
    out["요약길이"] = out["description"].fillna("").str.len()
    out["제목단어수"] = out["title"].fillna("").str.split().str.len()
    out["도메인"] = out["link"].fillna("").apply(_domain)

    # 랭크를 5구간으로 — "상위에 노출되는 문서는 더 긴가" 같은 질문에 쓴다.
    max_rank = int(out["rank"].max()) if len(out) else 0
    if max_rank >= rank_bins:
        size = max(max_rank // rank_bins, 1)
        out["랭크구간"] = ((out["rank"] - 1) // size + 1).clip(upper=rank_bins)
        out["랭크구간"] = out["랭크구간"].apply(lambda i: f"{i}구간")
    else:
        out["랭크구간"] = "1구간"

    if out["published_at"].notna().any():
        out["요일"] = out["published_at"].dt.dayofweek.map(
            {i: d for i, d in enumerate(WEEKDAYS)}
        )
        out["시간대"] = out["published_at"].dt.hour
        out["연월"] = out["published_at"].dt.to_period("M").astype(str)
    return out


def add_image_features(df: pd.DataFrame) -> pd.DataFrame:
    """이미지 채널 전용 — 유일하게 진짜 연속형 변수를 가진 채널."""
    if df.empty:
        return df
    out = df.copy()
    widths, heights = [], []
    for raw in out["raw"]:
        item = raw if isinstance(raw, dict) else {}
        widths.append(pd.to_numeric(item.get("sizewidth"), errors="coerce"))
        heights.append(pd.to_numeric(item.get("sizeheight"), errors="coerce"))
    out["가로"] = widths
    out["세로"] = heights
    out["화소수(만)"] = (out["가로"] * out["세로"] / 10_000).round(1)
    out["종횡비"] = (out["가로"] / out["세로"]).round(3)
    out["방향"] = out["종횡비"].apply(
        lambda r: "정사각형" if pd.isna(r) is False and abs(r - 1) < 0.05
        else ("가로형" if r and r > 1 else "세로형")
    )
    return out


def add_local_features(df: pd.DataFrame) -> pd.DataFrame:
    """지역 채널 전용 — mapx/mapy 는 WGS84 좌표에 10^7 을 곱한 정수 문자열."""
    if df.empty:
        return df
    out = df.copy()
    lons, lats, cats, addrs = [], [], [], []
    for raw in out["raw"]:
        item = raw if isinstance(raw, dict) else {}
        x = pd.to_numeric(item.get("mapx"), errors="coerce")
        y = pd.to_numeric(item.get("mapy"), errors="coerce")
        lons.append(x / 1e7 if pd.notna(x) else None)
        lats.append(y / 1e7 if pd.notna(y) else None)
        cats.append(item.get("category") or "")
        addrs.append(item.get("address") or item.get("roadAddress") or "")
    out["lon"] = lons
    out["lat"] = lats
    out["분류"] = cats
    out["주소"] = addrs
    out["시도"] = out["주소"].str.split().str[0].replace("", "(미상)")
    out["대분류"] = out["분류"].str.split(">").str[0].replace("", "(미상)")
    return out


def _domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", str(url or ""))
    return match.group(1).replace("www.", "") if match else "(미상)"


def tld_of(domain: str) -> str:
    """도메인의 최상위 구간 — 웹문서 채널에서 출처 성격을 대략 나눈다."""
    parts = str(domain or "").split(".")
    if len(parts) < 2:
        return "(미상)"
    if len(parts) >= 3 and parts[-2] in {"co", "or", "ne", "go", "ac", "re", "pe"}:
        return ".".join(parts[-2:])
    return parts[-1]
