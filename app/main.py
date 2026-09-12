"""네이버 마켓 인사이트 EDA 대시보드 (Streamlit).

실행: uv run streamlit run app/main.py
데이터 출처: NAVER API HUB — https://api.ncloud-docs.com/docs/naver-api-hub-overview

구조: 종합 / 채널별(심층 6 + 경량 2) / 트렌드(검색어 트렌드 · 쇼핑인사이트)
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))

from naver_insight import eda  # noqa: E402
from naver_insight.client import NaverClient  # noqa: E402
from naver_insight.collector import (  # noqa: E402
    collect_search,
    collect_trend,
    previous_window,
    list_snapshots,
    load_snapshot,
    parse_keywords,
    save_snapshot,
)
from naver_insight.settings import (  # noqa: E402
    SEARCH_ENDPOINTS,
    TREND_AGES,
    TREND_DEVICES,
    TREND_GENDERS,
    TREND_TIME_UNITS,
    get_credentials,
)
from views import channel as channel_view  # noqa: E402
from views import overview as overview_view  # noqa: E402
from views import trend as trend_view  # noqa: E402

st.set_page_config(page_title="네이버 마켓 인사이트 EDA", page_icon="🔎", layout="wide")

STYLE_PATH = ROOT / "assets" / "styles" / "dashboard.css"
if STYLE_PATH.exists():
    st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# 심층 EDA 탭을 만드는 채널과, 표본이 작아 경량 뷰로 보여주는 채널
DEEP_CHANNELS = ["news", "blog", "cafearticle", "webkr", "kin", "image"]
LIGHT_CHANNELS = ["local", "encyc"]

# 기간 필터를 실제로 적용할 탭 — 발행일이 있는 채널만 의미가 있다.
DATED_CHANNELS = {"news", "blog"}


# --------------------------------------------------------------------- 사이드바
def sidebar_controls() -> dict:
    st.sidebar.header("① 검색어")
    raw_keywords = st.sidebar.text_input(
        "쉼표(,)로 구분해 입력",
        value="탕후루, 마라탕, 두바이초콜릿",
        help="예: 탕후루, 마라탕, 두바이초콜릿",
    )
    keywords = parse_keywords(raw_keywords)

    st.sidebar.header("② 기간")
    today = date.today()
    default_start = today - timedelta(days=90)
    period = st.sidebar.date_input(
        "조회 기간",
        value=(default_start, today),
        max_value=today,
        help="트렌드·쇼핑인사이트 조회 구간이자, 뉴스·블로그 결과의 필터 구간입니다.",
    )
    if isinstance(period, tuple) and len(period) == 2:
        start_date, end_date = period
    else:
        start_date, end_date = default_start, today

    _period_scope_badge()
    compare = st.sidebar.toggle(
        "직전 동일 기간과 비교",
        value=True,
        help="같은 길이의 직전 구간을 함께 조회해 트렌드 탭에 증감률을 표시합니다. "
             "두 구간을 한 번의 요청으로 받아야 값이 서로 비교 가능해집니다.",
    )
    if compare:
        prev_start, prev_end = previous_window(start_date, end_date)
        st.sidebar.caption(f"직전 구간: {prev_start} ~ {prev_end}")

    st.sidebar.header("③ 수집 채널")
    selected = []
    cols = st.sidebar.columns(2)
    for idx, (key, spec) in enumerate(SEARCH_ENDPOINTS.items()):
        with cols[idx % 2]:
            if st.checkbox(spec.label, value=True, key=f"ep_{key}"):
                selected.append(key)

    st.sidebar.header("④ 수집 옵션")
    per_call = st.sidebar.slider(
        "검색어·채널당 수집 문서 수", min_value=50, max_value=1000, value=300, step=50,
        help="지역은 API 상한이 5건이라 이 값과 무관하게 5건입니다.",
    )
    sort_choice = st.sidebar.radio(
        "정렬", options=["날짜순", "정확도순"], horizontal=True,
        help="날짜순이면 '최근 N건'이라는 정의된 표본이 되어 기간 해석과 맞아떨어집니다.",
    )
    sort_map = {}
    for key, spec in SEARCH_ENDPOINTS.items():
        if not spec.sort_options:
            continue
        if sort_choice == "날짜순" and "date" in spec.sort_options:
            sort_map[key] = "date"
        else:
            sort_map[key] = spec.sort_options[0]

    st.sidebar.header("⑤ 트렌드 옵션")
    time_unit = st.sidebar.selectbox(
        "구간 단위", options=list(TREND_TIME_UNITS), index=0,
        format_func=lambda k: TREND_TIME_UNITS[k],
    )
    device = st.sidebar.selectbox(
        "기기", options=list(TREND_DEVICES), format_func=lambda k: TREND_DEVICES[k]
    )
    gender = st.sidebar.selectbox(
        "성별", options=list(TREND_GENDERS), format_func=lambda k: TREND_GENDERS[k]
    )
    ages = st.sidebar.multiselect(
        "연령대", options=list(TREND_AGES), format_func=lambda k: TREND_AGES[k]
    )

    run = st.sidebar.button("🔍 수집 실행", type="primary", width='stretch')

    opts = {
        "keywords": keywords,
        "start": start_date,
        "end": end_date,
        "endpoints": selected,
        "per_call": per_call,
        "sort_map": sort_map,
        "sort_choice": sort_choice,
        "time_unit": time_unit,
        "device": device,
        "gender": gender,
        "ages": ages,
        "compare": compare,
        "run": run,
    }
    _snapshot_controls(opts)
    return opts


def _period_scope_badge() -> None:
    """기간이 실제로 적용되는 대상과 아닌 대상을 기간 입력 바로 아래에 표시한다.

    발행일(pubDate·postdate)을 주는 채널은 뉴스·블로그뿐이라, 나머지 채널의
    결과는 기간을 좁혀도 그대로 남는다. 결과를 보고 나서 눈치채는 대신
    입력 시점에 알 수 있게 한다.
    """
    applied, skipped = [], []
    for key, spec in SEARCH_ENDPOINTS.items():
        if not st.session_state.get(f"ep_{key}", True):
            continue  # 선택하지 않은 채널은 표시하지 않는다
        (applied if key in DATED_CHANNELS else skipped).append(spec.label)
    applied.append("트렌드·쇼핑인사이트")

    chips = "".join(f"<span class='scope-chip on'>{label}</span>" for label in applied)
    chips += "".join(f"<span class='scope-chip off'>{label}</span>" for label in skipped)
    st.sidebar.markdown(
        f"<div class='period-scope'>"
        f"<div class='scope-row'><b>적용</b>{chips}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if skipped:
        st.sidebar.caption(
            "회색 채널은 API가 발행일을 주지 않아 기간이 적용되지 않습니다."
        )


def _snapshot_controls(opts: dict) -> None:
    """발표 당일 API 장애에 대비한 저장·불러오기."""
    st.sidebar.header("⑥ 스냅샷")
    snapshots = list_snapshots()
    if snapshots:
        picked = st.sidebar.selectbox(
            "불러오기", options=["(선택 안 함)"] + [s.name for s in snapshots]
        )
        if picked != "(선택 안 함)" and st.sidebar.button("이 스냅샷 불러오기",
                                                        width='stretch'):
            _apply_snapshot(picked)
    else:
        st.sidebar.caption("저장된 스냅샷이 없습니다.")

    if "df" in st.session_state and st.sidebar.button("현재 결과 저장", width='stretch'):
        name = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = save_snapshot(name, _serialize_state(opts))
        st.sidebar.success(f"저장했습니다: {path.name}")


def _serialize_state(opts: dict) -> dict:
    df: pd.DataFrame = st.session_state.get("df", pd.DataFrame())
    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "keywords": opts["keywords"],
        "start": str(opts["start"]),
        "end": str(opts["end"]),
        "records": df.drop(columns=["raw"]).assign(
            published_at=df["published_at"].astype(str)
        ).to_dict("records") if not df.empty else [],
        "raws": df["raw"].tolist() if not df.empty else [],
        "trend": st.session_state.get("trend", pd.DataFrame()).assign(
            period=lambda d: d["period"].astype(str)
        ).to_dict("records") if not st.session_state.get("trend", pd.DataFrame()).empty else [],
    }


def _apply_snapshot(name: str) -> None:
    payload = load_snapshot(name)
    records = payload.get("records", [])
    if not records:
        st.sidebar.warning("스냅샷에 문서가 없습니다.")
        return
    df = pd.DataFrame(records)
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df["raw"] = payload.get("raws", [{}] * len(df))[: len(df)]
    st.session_state["df"] = df
    trend = pd.DataFrame(payload.get("trend", []))
    if not trend.empty:
        trend["period"] = pd.to_datetime(trend["period"], errors="coerce")
    st.session_state["trend"] = trend
    st.session_state["errors"] = []
    st.session_state["trend_error"] = None
    st.session_state["snapshot_name"] = name
    st.rerun()


# ----------------------------------------------------------------------- 수집
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_collect(keywords: tuple, endpoints: tuple, per_call: int, sort_key: tuple):
    """같은 조건이면 재호출하지 않는다 — 탭을 옮길 때마다 API를 때리지 않도록."""
    client = NaverClient(get_credentials())
    report = collect_search(
        client, keywords=list(keywords), endpoints=list(endpoints),
        per_call=per_call, sort_map=dict(sort_key),
    )
    return eda.to_dataframe(report.results), report.errors


def run_collection(opts: dict) -> None:
    creds = get_credentials()
    if not creds.is_ready:
        st.error(
            "인증 정보가 없습니다. 로컬은 프로젝트 루트 `.env`, "
            "Streamlit Cloud 는 앱 설정의 Secrets 에 "
            "`NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` 을 채워주세요."
        )
        return

    with st.spinner("네이버 API에서 수집 중…"):
        df, errors = _cached_collect(
            tuple(opts["keywords"]), tuple(opts["endpoints"]),
            opts["per_call"], tuple(sorted(opts["sort_map"].items())),
        )
        client = NaverClient(creds)
        trend_payload, trend_error = collect_trend(
            client, keywords=opts["keywords"], start=opts["start"], end=opts["end"],
            time_unit=opts["time_unit"], device=opts["device"],
            gender=opts["gender"], ages=opts["ages"],
            with_comparison=opts.get("compare", False),
        )

    st.session_state["df"] = df
    st.session_state["errors"] = errors
    st.session_state["trend"] = eda.trend_to_dataframe(trend_payload or {})
    st.session_state["trend_error"] = trend_error
    st.session_state["opts"] = opts
    st.session_state.pop("snapshot_name", None)


# ------------------------------------------------------------------------ main
def main() -> None:
    st.title("🔎 네이버 마켓 인사이트 EDA 대시보드")
    st.caption(
        "NAVER API HUB 공식 문서 기반 · 검색 8채널 + 검색어 트렌드 + 쇼핑인사이트"
    )

    opts = sidebar_controls()
    creds = get_credentials()

    if not creds.is_ready:
        st.warning(
            "인증 정보가 없습니다.\n\n"
            "- **로컬 실행**: `config/.env.example` 을 루트에 `.env` 로 복사한 뒤 "
            "`NAVER_CLIENT_ID`·`NAVER_CLIENT_SECRET` 을 입력하세요.\n"
            "- **Streamlit Cloud 배포**: 앱 우측 상단 ⋮ → Settings → Secrets 에 "
            "같은 키를 `NAVER_CLIENT_ID = \"...\"` 형식으로 저장하세요."
        )
    else:
        st.caption(f"인증 모드: `{creds.mode}` · 엔드포인트: `{creds.base_url}`")

    if opts["run"]:
        if not opts["keywords"]:
            st.error("검색어를 하나 이상 입력하세요.")
        elif not opts["endpoints"]:
            st.error("수집할 채널을 하나 이상 선택하세요.")
        else:
            run_collection(opts)

    if "df" not in st.session_state:
        st.info("좌측에서 검색어와 기간을 입력하고 **수집 실행**을 눌러주세요.")
        return

    df_all: pd.DataFrame = st.session_state["df"]
    opts = st.session_state.get("opts", opts)

    if snapshot := st.session_state.get("snapshot_name"):
        st.info(f"스냅샷 `{snapshot}` 을 불러온 상태입니다. 라이브 호출이 아닙니다.")

    errors = st.session_state.get("errors", [])
    if errors:
        with st.expander(f"⚠️ 수집 중 오류 {len(errors)}건"):
            for err in errors:
                st.text(err)

    if df_all.empty:
        st.warning("수집된 문서가 없습니다.")
        return

    top = st.tabs(["📊 종합", "🗂 채널별", "📈 트렌드"])

    with top[0]:
        overview_view.render(_period_scoped(df_all, opts, dated_only=True), opts)

    with top[1]:
        _render_channels(df_all, opts)

    with top[2]:
        sub = st.tabs(["검색어 트렌드", "쇼핑인사이트"])
        with sub[0]:
            trend_view.render_search_trend(
                st.session_state.get("trend", pd.DataFrame()),
                st.session_state.get("trend_error"), opts,
            )
        with sub[1]:
            client = NaverClient(creds) if creds.is_ready else None
            trend_view.render_shopping(client, opts)


def _period_scoped(df: pd.DataFrame, opts: dict, dated_only: bool) -> pd.DataFrame:
    """기간 필터는 발행일이 있는 채널에만 적용한다(탭별 분리 적용)."""
    if not dated_only:
        return df
    return eda.filter_by_period(df, opts["start"], opts["end"])


def _render_channels(df_all: pd.DataFrame, opts: dict) -> None:
    available = [
        key for key in DEEP_CHANNELS
        if key in set(df_all["endpoint"].unique())
    ]
    light = [key for key in LIGHT_CHANNELS if key in set(df_all["endpoint"].unique())]
    if not available and not light:
        st.info("수집된 채널이 없습니다.")
        return

    labels = [SEARCH_ENDPOINTS[k].label for k in available + light]
    tabs = st.tabs(labels)

    for tab, key in zip(tabs, available + light):
        with tab:
            part = df_all[df_all["endpoint"] == key]
            if key in DATED_CHANNELS:
                scoped = eda.filter_by_period(part, opts["start"], opts["end"])
                dropped = len(part) - len(scoped)
                if dropped:
                    st.caption(
                        f"기간 필터로 {dropped:,}건 제외 — {opts['start']} ~ {opts['end']}"
                    )
                part = scoped
            if key == "local":
                channel_view.render_local(part)
            elif key == "encyc":
                channel_view.render_encyc(part)
            else:
                channel_view.render(part, key, SEARCH_ENDPOINTS[key].label)


if __name__ == "__main__":
    main()
