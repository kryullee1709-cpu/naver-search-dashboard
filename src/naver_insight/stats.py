"""기술통계 · 교차표 · 피봇 · 카이제곱 검정 등 통계 계산 계층.

시각화는 하지 않는다. 여기서는 표로 쓸 수 있는 DataFrame만 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

ALPHA = 0.05


# ------------------------------------------------------------------ 기술통계
def describe_numeric(df: pd.DataFrame, columns: list[str], by: str | None = None) -> pd.DataFrame:
    """수치형 변수의 기술통계 — 건수·평균·표준편차·사분위·왜도.

    by 를 주면 그룹별로 쌓아 하나의 표로 만든다.
    """
    cols = [c for c in columns if c in df.columns]
    if df.empty or not cols:
        return pd.DataFrame()

    def _one(part: pd.DataFrame, label: str | None) -> list[dict]:
        rows = []
        for col in cols:
            series = pd.to_numeric(part[col], errors="coerce").dropna()
            if series.empty:
                continue
            row = {
                "변수": col,
                "건수": int(series.size),
                "평균": round(float(series.mean()), 2),
                "표준편차": round(float(series.std(ddof=1)), 2) if series.size > 1 else 0.0,
                "최소": round(float(series.min()), 2),
                "25%": round(float(series.quantile(0.25)), 2),
                "중앙값": round(float(series.median()), 2),
                "75%": round(float(series.quantile(0.75)), 2),
                "최대": round(float(series.max()), 2),
                "왜도": round(float(series.skew()), 2) if series.size > 2 else 0.0,
            }
            if label is not None:
                row = {by: label, **row}
            rows.append(row)
        return rows

    if by and by in df.columns:
        rows: list[dict] = []
        for label, part in df.groupby(by):
            rows.extend(_one(part, str(label)))
        return pd.DataFrame(rows)
    return pd.DataFrame(_one(df, None))


# -------------------------------------------------------------------- 교차표
@dataclass
class CrossTabResult:
    table: pd.DataFrame  # 관측 빈도 (합계 포함)
    expected: pd.DataFrame  # 기대 빈도
    chi2: float | None
    p_value: float | None
    dof: int | None
    cramers_v: float | None
    note: str

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < ALPHA


def crosstab_with_chi2(
    df: pd.DataFrame, row: str, col: str, top_n: int = 10
) -> CrossTabResult:
    """교차표 + 카이제곱 독립성 검정 + Cramér's V.

    범주가 많으면 상위 top_n 만 남기고 나머지는 '기타'로 묶는다.
    기대빈도 5 미만 칸이 20%를 넘으면 검정 결과를 신뢰할 수 없다고 표시한다.
    """
    empty = pd.DataFrame()
    if df.empty or row not in df.columns or col not in df.columns:
        return CrossTabResult(empty, empty, None, None, None, None, "데이터가 없습니다.")

    work = df[[row, col]].dropna().copy()
    if work.empty:
        return CrossTabResult(empty, empty, None, None, None, None, "데이터가 없습니다.")

    keep = work[col].value_counts().head(top_n).index
    work[col] = np.where(work[col].isin(keep), work[col], "기타")

    observed = pd.crosstab(work[row], work[col])
    if observed.shape[0] < 2 or observed.shape[1] < 2:
        table = observed.copy()
        table["합계"] = table.sum(axis=1)
        return CrossTabResult(
            table, empty, None, None, None, None,
            "행 또는 열이 하나뿐이라 독립성 검정을 할 수 없습니다.",
        )

    chi2, p_value, dof, expected = sps.chi2_contingency(observed)
    expected_df = pd.DataFrame(expected, index=observed.index, columns=observed.columns).round(1)

    n = int(observed.values.sum())
    min_dim = min(observed.shape) - 1
    cramers_v = float(np.sqrt(chi2 / (n * min_dim))) if n and min_dim else None

    low = int((expected < 5).sum())
    ratio = low / expected.size
    if ratio > 0.2:
        note = (
            f"기대빈도 5 미만인 칸이 {low}개({ratio:.0%})라 카이제곱 근사가 부정확합니다. "
            "참고용으로만 보세요."
        )
    elif p_value < ALPHA:
        note = f"p = {p_value:.4f} < {ALPHA} → 두 변수는 독립이 아닙니다(연관이 있습니다)."
    else:
        note = f"p = {p_value:.4f} ≥ {ALPHA} → 독립이라는 귀무가설을 기각하지 못합니다."

    table = observed.copy()
    table["합계"] = table.sum(axis=1)
    table.loc["합계"] = table.sum(axis=0)

    return CrossTabResult(
        table=table,
        expected=expected_df,
        chi2=round(float(chi2), 3),
        p_value=float(p_value),
        dof=int(dof),
        cramers_v=round(cramers_v, 3) if cramers_v is not None else None,
        note=note,
    )


# ------------------------------------------------------------------ 피봇테이블
def pivot_table(
    df: pd.DataFrame,
    index: str,
    columns: str,
    values: str,
    aggfunc: str = "mean",
    margins: bool = True,
) -> pd.DataFrame:
    if df.empty or not {index, columns, values} <= set(df.columns):
        return pd.DataFrame()
    out = pd.pivot_table(
        df, index=index, columns=columns, values=values,
        aggfunc=aggfunc, margins=margins, margins_name="전체",
    )
    return out.round(2)


# ------------------------------------------------ 검색어 간 비교 (추가 제안분)
def keyword_overlap(token_sets: dict[str, set[str]]) -> pd.DataFrame:
    """검색어 쌍별 연관어 자카드 유사도 — 같은 맥락에서 언급되는지 본다."""
    names = list(token_sets)
    if len(names) < 2:
        return pd.DataFrame()
    matrix = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            sa, sb = token_sets[a], token_sets[b]
            union = sa | sb
            matrix.loc[a, b] = round(len(sa & sb) / len(union), 3) if union else 0.0
    return matrix


def duplicate_report(df: pd.DataFrame) -> pd.DataFrame:
    """링크 기준 중복 — 같은 문서가 여러 채널·검색어에 걸쳐 잡히는 정도."""
    if df.empty or "link" not in df.columns:
        return pd.DataFrame()
    work = df[df["link"].astype(str).str.len() > 0]
    if work.empty:
        return pd.DataFrame()
    grouped = (
        work.groupby("link")
        .agg(
            중복수=("link", "size"),
            채널수=("channel", "nunique"),
            검색어수=("keyword", "nunique"),
            제목=("title", "first"),
        )
        .query("중복수 > 1")
        .sort_values(["채널수", "중복수"], ascending=False)
        .reset_index()
    )
    return grouped


def duplicate_rate(df: pd.DataFrame) -> float:
    """전체 문서 중 링크가 중복된 비율(%)."""
    if df.empty or "link" not in df.columns:
        return 0.0
    links = df["link"].astype(str)
    links = links[links.str.len() > 0]
    if links.empty:
        return 0.0
    return round((1 - links.nunique() / len(links)) * 100, 2)


def concentration(df: pd.DataFrame, column: str, top_n: int = 5) -> pd.DataFrame:
    """상위 N개 출처가 차지하는 비중 — 담론이 몇 곳에 쏠려 있는지."""
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    rows = []
    for keyword, part in df.groupby("keyword"):
        counts = part[column].value_counts()
        total = int(counts.sum())
        if not total:
            continue
        head = int(counts.head(top_n).sum())
        rows.append(
            {
                "keyword": keyword,
                f"상위{top_n} 점유율(%)": round(head / total * 100, 1),
                "고유 출처 수": int(counts.size),
                "문서 수": total,
                "최다 출처": counts.index[0],
                "최다 출처 건수": int(counts.iloc[0]),
            }
        )
    return pd.DataFrame(rows)
