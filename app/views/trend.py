"""트렌드 탭 — 검색어 트렌드(데이터랩)와 쇼핑인사이트."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from naver_insight import eda, stats
from naver_insight.collector import previous_window
from naver_insight.client import NaverApiError, NaverClient
from naver_insight.settings import (
    SHOPPING_CATEGORY_PRESETS,
    SHOPPING_MAX_CATEGORIES,
    SHOPPING_MAX_KEYWORDS,
    TREND_AGES,
    TREND_DEVICES,
    TREND_GENDERS,
    TREND_MAX_GROUPS,
    TREND_TIME_UNITS,
)

from .common import bar, box, heatmap, line, section, show_table


def render_search_trend(trend_df: pd.DataFrame, error: str | None, opts: dict) -> None:
    st.caption(
        f"{opts['start']} ~ {opts['end']} · {TREND_TIME_UNITS[opts['time_unit']]} · "
        f"기기 {TREND_DEVICES[opts['device']]} · 성별 {TREND_GENDERS[opts['gender']]}"
        + (f" · 연령 {', '.join(TREND_AGES[a] for a in opts['ages'])}" if opts["ages"] else "")
    )
    if error:
        st.warning(f"검색어 트렌드 조회 실패: {error}")
        return
    if trend_df.empty:
        st.info("트렌드 데이터가 없습니다. 수집을 먼저 실행해 주세요.")
        return
    if len(opts["keywords"]) > TREND_MAX_GROUPS:
        st.caption(f"공식 문서 제약으로 앞의 {TREND_MAX_GROUPS}개 검색어만 조회합니다.")

    compare = bool(opts.get("compare"))
    if compare:
        _comparison(trend_df, opts)

    section("상대 검색량 추이", "구간 내 최대값을 100으로 둔 상대값입니다. 절대 검색 횟수가 아닙니다.")
    fig = line(trend_df, x="period", y="ratio", color="group", height=400,
               labels={"period": "기간", "ratio": "상대 검색량", "group": "검색어"})
    if compare:
        _mark_boundary(fig, trend_df, opts)
    st.plotly_chart(fig, width='stretch', key="tr_line")

    c1, c2 = st.columns(2)
    with c1:
        section("검색어별 분포")
        st.plotly_chart(
            box(trend_df, x="group", y="ratio", color="group",
                labels={"group": "검색어", "ratio": "상대 검색량"}),
            width='stretch', key="tr_box",
        )
    with c2:
        section("기간 × 검색어 히트맵")
        matrix = trend_df.pivot_table(index="group", columns=trend_df["period"].dt.strftime("%Y-%m-%d"),
                                      values="ratio", aggfunc="mean")
        if not matrix.empty:
            st.plotly_chart(
                heatmap(matrix, text=False,
                        labels=dict(x="기간", y="검색어", color="상대 검색량")),
                width='stretch', key="tr_heat",
            )

    # 비교를 켜면 조회 구간에 직전 기간이 함께 들어오므로,
    # 아래 통계 표는 현재 구간만 잘라서 계산한다(차트는 두 구간을 모두 보여준다).
    current = trend_df[trend_df["period"] >= pd.Timestamp(opts["start"])] if compare else trend_df
    if compare:
        st.caption(f"아래 표는 현재 구간({opts['start']} ~ {opts['end']})만 계산한 값입니다.")

    section("표 1 — 기초 통계와 전·후반 변화율")
    show_table(eda.trend_stats(current))

    section("표 2 — 상대 검색량 기술통계")
    show_table(stats.describe_numeric(current, ["ratio"], by="group"))

    section("표 3 — 기간별 피봇테이블")
    pivot = current.assign(기간=current["period"].dt.strftime("%Y-%m-%d"))
    show_table(stats.pivot_table(pivot, "기간", "group", "ratio", "mean"))

    if compare:
        section("표 4 — 직전 구간 대비 증감")
        show_table(eda.compare_windows(trend_df, opts["start"]))


# --------------------------------------------------------------- 쇼핑인사이트
def render_shopping(client: NaverClient | None, opts: dict) -> None:
    st.caption(
        "네이버쇼핑 클릭 추이입니다. 검색 채널이 '언급량'이라면 이쪽은 '구매 관심'입니다. "
        "분야 코드는 네이버쇼핑에서 카테고리를 고른 뒤 URL의 cat_id 값으로 확인할 수 있습니다."
    )

    c1, c2 = st.columns([1.2, 1])
    with c1:
        picked = st.multiselect(
            "분야 선택 (최대 3개)",
            options=list(SHOPPING_CATEGORY_PRESETS),
            format_func=lambda code: f"{SHOPPING_CATEGORY_PRESETS[code]} ({code})",
            default=["50000006"],
            max_selections=SHOPPING_MAX_CATEGORIES,
        )
    with c2:
        custom = st.text_input(
            "직접 입력 (cat_id, 쉼표 구분)",
            help="프리셋에 없는 세부 분야를 볼 때 사용합니다.",
        )

    categories = [
        {"name": SHOPPING_CATEGORY_PRESETS[c], "param": [c]} for c in picked
    ]
    for code in [c.strip() for c in custom.split(",") if c.strip()]:
        if len(categories) >= SHOPPING_MAX_CATEGORIES:
            break
        categories.append({"name": code, "param": [code]})

    if not categories:
        st.info("분야를 하나 이상 선택하거나 입력해 주세요.")
        return
    if client is None:
        st.warning("인증 정보가 없어 조회할 수 없습니다.")
        return

    go = st.button("쇼핑인사이트 조회", type="primary", key="shop_run")
    if go:
        _fetch(client, categories, opts)

    payload = st.session_state.get("shopping")
    if not payload:
        st.info("**쇼핑인사이트 조회** 버튼을 눌러주세요.")
        return
    _render_payload(payload, opts)


def _fetch(client: NaverClient, categories: list[dict], opts: dict) -> None:
    start, end = opts["start"].isoformat(), opts["end"].isoformat()
    unit = opts["time_unit"]
    result: dict = {"categories": categories}
    try:
        result["category_trend"] = client.shopping_categories(start, end, categories, unit)
        first = categories[0]["param"][0]
        result["first_code"] = first
        result["first_name"] = categories[0]["name"]

        keywords = [
            {"name": kw, "param": [kw]} for kw in opts["keywords"][:SHOPPING_MAX_KEYWORDS]
        ]
        if keywords:
            result["keyword_trend"] = client.shopping_keywords(
                start, end, first, keywords, unit
            )
        segments = {}
        for label, kwargs in {
            "PC": {"device": "pc"},
            "모바일": {"device": "mo"},
            "남성": {"gender": "m"},
            "여성": {"gender": "f"},
        }.items():
            segments[label] = client.shopping_segment(start, end, first, unit, **kwargs)
        result["segments"] = segments
        result["error"] = None
    except NaverApiError as exc:
        result["error"] = str(exc)
    st.session_state["shopping"] = result


def _to_df(payload: dict | None, label_key: str = "title") -> pd.DataFrame:
    rows = []
    for group in (payload or {}).get("results", []) or []:
        for point in group.get("data", []) or []:
            rows.append(
                {
                    "group": group.get(label_key),
                    "period": pd.to_datetime(point.get("period"), errors="coerce"),
                    "ratio": float(point.get("ratio", 0) or 0),
                }
            )
    return pd.DataFrame(rows).sort_values(["group", "period"]) if rows else pd.DataFrame()


def _render_payload(payload: dict, opts: dict) -> None:
    if payload.get("error"):
        st.warning(f"쇼핑인사이트 조회 실패: {payload['error']}")
        return

    cat_df = _to_df(payload.get("category_trend"))
    kw_df = _to_df(payload.get("keyword_trend"))

    section("분야별 클릭 추이")
    if cat_df.empty:
        st.info("분야 데이터가 없습니다.")
    else:
        st.plotly_chart(
            line(cat_df, x="period", y="ratio", color="group", height=380,
                 labels={"period": "기간", "ratio": "상대 클릭량", "group": "분야"}),
            width='stretch', key="shop_cat",
        )

    if not kw_df.empty:
        section(
            f"'{payload.get('first_name')}' 분야 안에서 검색어별 클릭 추이",
            "입력하신 검색어를 이 분야 안에서 비교합니다.",
        )
        st.plotly_chart(
            line(kw_df, x="period", y="ratio", color="group", height=360,
                 labels={"period": "기간", "ratio": "상대 클릭량", "group": "검색어"}),
            width='stretch', key="shop_kw",
        )

    seg_rows = []
    for label, seg_payload in (payload.get("segments") or {}).items():
        seg = _to_df(seg_payload)
        if not seg.empty:
            seg["세그먼트"] = label
            seg_rows.append(seg)
    seg_df = pd.concat(seg_rows) if seg_rows else pd.DataFrame()

    if not seg_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            section("기기·성별 세그먼트 추이")
            st.plotly_chart(
                line(seg_df, x="period", y="ratio", color="세그먼트", height=340,
                     labels={"period": "기간", "ratio": "상대 클릭량"}),
                width='stretch', key="shop_seg",
            )
        with c2:
            section("세그먼트별 평균 비교")
            avg = seg_df.groupby("세그먼트", as_index=False)["ratio"].mean().round(2)
            st.plotly_chart(
                bar(avg, x="세그먼트", y="ratio", labels={"ratio": "평균 상대 클릭량"}),
                width='stretch', key="shop_segbar",
            )

    st.divider()
    section("표 1 — 분야별 기초 통계")
    show_table(eda.trend_stats(cat_df))

    if not kw_df.empty:
        section("표 2 — 검색어별 기초 통계 (분야 내)")
        show_table(eda.trend_stats(kw_df))

    if not seg_df.empty:
        section("표 3 — 세그먼트 기술통계")
        show_table(stats.describe_numeric(seg_df, ["ratio"], by="세그먼트"))

        section("표 4 — 기간 × 세그먼트 피봇테이블")
        pivot = seg_df.assign(기간=seg_df["period"].dt.strftime("%Y-%m-%d"))
        show_table(stats.pivot_table(pivot, "기간", "세그먼트", "ratio", "mean"))


def _mark_boundary(fig, trend_df: pd.DataFrame, opts: dict) -> None:
    """직전 구간을 음영으로 덮고 현재 구간이 시작되는 지점에 선을 긋는다."""
    boundary = pd.Timestamp(opts["start"])
    first = trend_df["period"].min()
    if pd.isna(first) or first >= boundary:
        return
    fig.add_vrect(
        x0=first, x1=boundary,
        fillcolor="#9CA3AF", opacity=0.10, line_width=0, layer="below",
    )
    fig.add_vline(
        x=boundary.to_pydatetime(), line_width=2, line_dash="dot", line_color="#6B7280",
    )
    fig.add_annotation(
        x=boundary, yref="paper", y=1.06, showarrow=False,
        text="현재 구간 시작", font=dict(size=11, color="#6B7280"),
    )


def _comparison(trend_df: pd.DataFrame, opts: dict) -> None:
    """직전 동일 기간 대비 증감."""
    prev_start, prev_end = previous_window(opts["start"], opts["end"])
    section(
        "직전 동일 기간 대비",
        f"직전 {prev_start} ~ {prev_end} · 현재 {opts['start']} ~ {opts['end']}",
    )
    table = eda.compare_windows(trend_df, opts["start"])
    if table.empty:
        st.info("직전 구간 데이터가 없어 비교할 수 없습니다. 기간을 넓혀보세요.")
        return

    cols = st.columns(min(len(table), 5))
    for col, (_, row) in zip(cols, table.iterrows()):
        col.metric(
            row["group"],
            f"{row['현재 평균']:.1f}",
            delta=f"{row['증감률(%)']:+.1f}%",
        )
    st.caption(
        "두 구간을 한 번의 요청으로 함께 조회해 같은 기준으로 정규화된 값입니다. "
        "구간을 따로 조회하면 각각 최대값이 100이 되어 비교할 수 없습니다."
    )

    split = eda.split_windows(trend_df, opts["start"])
    c1, c2 = st.columns([1.2, 1])
    with c1:
        avg = (
            split.groupby(["group", "구간"], as_index=False)["ratio"].mean().round(2)
            .rename(columns={"ratio": "평균 상대 검색량"})
        )
        st.plotly_chart(
            bar(avg, x="group", y="평균 상대 검색량", color="구간", barmode="group",
                labels={"group": "검색어"}),
            width='stretch', key="tr_cmp_bar",
        )
    with c2:
        show_table(table)
