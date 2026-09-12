"""환경 변수(.env) 로딩 및 NAVER API HUB 엔드포인트 정의.

공식 문서: https://api.ncloud-docs.com/docs/naver-api-hub-overview
- 인증 헤더: X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
- 기본 엔드포인트: https://naverapihub.apigw.ntruss.com
- 이관 가이드(https://guide.ncloud-docs.com/docs/apihub-migration) 기준
  기존 openapi.naver.com/v1/search/news.json -> /search/v1/news 로 경로가 변경됨.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

HUB_BASE_URL_DEFAULT = "https://naverapihub.apigw.ntruss.com"
LEGACY_BASE_URL_DEFAULT = "https://openapi.naver.com"
# 검색어 트렌드도 API HUB 게이트웨이를 쓴다. 경로 접두사가 하이픈이 들어간
# "search-trend" 라서 "datalab"/"searchtrend" 로 부르면 404(errorCode 300)가 난다.
TREND_BASE_URL_DEFAULT = HUB_BASE_URL_DEFAULT


def load_env() -> None:
    """.env 를 매 호출마다 다시 읽어 프로세스 환경에 반영한다.

    config/.env 를 먼저, 루트 .env 를 나중에 읽어 루트가 우선한다.
    파일에 값이 있으면 이미 설정된 값이라도 덮어쓴다 — 서버를 띄운 뒤에
    .env 를 채우는 경우, 처음 로드된 빈 문자열이 남아 계속 "인증 정보 없음"으로
    보이는 문제를 막기 위함이다. 빈 값은 무시하므로 셸 환경 변수는 지워지지 않는다.
    """
    for candidate in (PROJECT_ROOT / "config" / ".env", PROJECT_ROOT / ".env"):
        if not candidate.exists():
            continue
        for key, value in dotenv_values(candidate).items():
            if value:
                os.environ[key] = value


@dataclass(frozen=True)
class SearchEndpoint:
    """검색 API 하나에 대한 명세 (공식 문서 기준)."""

    key: str
    label: str
    hub_path: str
    legacy_path: str
    max_display: int
    max_start: int
    sort_options: tuple[str, ...]
    sort_labels: dict[str, str] = field(default_factory=dict)
    extra_params: dict[str, str] = field(default_factory=dict)
    has_date: bool = False
    text_fields: tuple[str, ...] = ("title", "description")


# 공식 문서에 명시된 값만 반영한다.
SEARCH_ENDPOINTS: dict[str, SearchEndpoint] = {
    "news": SearchEndpoint(
        key="news",
        label="뉴스",
        hub_path="/search/v1/news",
        legacy_path="/v1/search/news.json",
        max_display=100,
        max_start=1000,
        sort_options=("sim", "date"),
        sort_labels={"sim": "정확도순", "date": "날짜순"},
        has_date=True,
    ),
    "blog": SearchEndpoint(
        key="blog",
        label="블로그",
        hub_path="/search/v1/blog",
        legacy_path="/v1/search/blog.json",
        max_display=100,
        max_start=1000,
        sort_options=("sim", "date"),
        sort_labels={"sim": "정확도순", "date": "날짜순"},
        has_date=True,
    ),
    "webkr": SearchEndpoint(
        key="webkr",
        label="웹문서",
        hub_path="/search/v1/webkr",
        legacy_path="/v1/search/webkr.json",
        max_display=100,
        max_start=1000,
        sort_options=(),
    ),
    "image": SearchEndpoint(
        key="image",
        label="이미지",
        hub_path="/search/v1/image",
        legacy_path="/v1/search/image.json",
        max_display=100,
        max_start=1000,
        sort_options=("sim", "date"),
        sort_labels={"sim": "정확도순", "date": "날짜순"},
        extra_params={"filter": "all"},
        text_fields=("title",),
    ),
    "kin": SearchEndpoint(
        key="kin",
        label="지식iN",
        hub_path="/search/v1/kin",
        legacy_path="/v1/search/kin.json",
        max_display=100,
        max_start=1000,
        sort_options=("sim", "date", "point"),
        sort_labels={"sim": "정확도순", "date": "날짜순", "point": "평점순"},
    ),
    "local": SearchEndpoint(
        key="local",
        label="지역",
        hub_path="/search/v1/local",
        legacy_path="/v1/search/local.json",
        max_display=5,  # 지역 검색은 최대 5건 (공식 문서)
        max_start=1,
        sort_options=("random", "comment"),
        sort_labels={"random": "정확도순", "comment": "리뷰순"},
        text_fields=("title", "category", "description"),
    ),
    "cafearticle": SearchEndpoint(
        key="cafearticle",
        label="카페글",
        hub_path="/search/v1/cafearticle",
        legacy_path="/v1/search/cafearticle.json",
        max_display=100,
        max_start=1000,
        sort_options=("sim", "date"),
        sort_labels={"sim": "정확도순", "date": "날짜순"},
    ),
    "encyc": SearchEndpoint(
        key="encyc",
        label="백과사전",
        hub_path="/search/v1/encyc",
        legacy_path="/v1/search/encyc.json",
        max_display=100,
        max_start=1000,
        sort_options=(),
    ),
}

# 검색어 트렌드 (데이터랩) — POST
TREND_HUB_PATH = "/search-trend/v1/search"
TREND_LEGACY_PATH = "/v1/datalab/search"

TREND_TIME_UNITS = {"date": "일간", "week": "주간", "month": "월간"}
TREND_DEVICES = {"": "전체", "pc": "PC", "mo": "모바일"}
TREND_GENDERS = {"": "전체", "m": "남성", "f": "여성"}
TREND_AGES = {
    "1": "0~12세",
    "2": "13~18세",
    "3": "19~24세",
    "4": "25~29세",
    "5": "30~34세",
    "6": "35~39세",
    "7": "40~44세",
    "8": "45~49세",
    "9": "50~54세",
    "10": "55~59세",
    "11": "60세 이상",
}

# 공식 문서 제약: 한 번에 최대 5개 그룹, 그룹당 검색어 최대 20개
TREND_MAX_GROUPS = 5
TREND_MAX_KEYWORDS_PER_GROUP = 20


# 쇼핑인사이트 (Data Lab) — 모두 POST
SHOPPING_CATEGORY_PATH = "/shopping/v1/categories"          # 분야별 트렌드
SHOPPING_KEYWORD_PATH = "/shopping/v1/category/keywords"    # 분야 내 키워드별 트렌드
SHOPPING_DEVICE_PATH = "/shopping/v1/category/device"       # 분야 기기/성별/연령별

SHOPPING_MAX_CATEGORIES = 3   # 분야별 트렌드는 한 번에 최대 3분야
SHOPPING_MAX_KEYWORDS = 5     # 키워드별 트렌드는 최대 5개 쌍

# 네이버쇼핑 대분류 코드. 세부 분야는 네이버쇼핑 URL의 cat_id 로 직접 입력받는다.
SHOPPING_CATEGORY_PRESETS = {
    "50000000": "패션의류",
    "50000001": "패션잡화",
    "50000002": "화장품/미용",
    "50000003": "디지털/가전",
    "50000004": "가구/인테리어",
    "50000005": "출산/육아",
    "50000006": "식품",
    "50000007": "스포츠/레저",
    "50000008": "생활/건강",
    "50000009": "여가/생활편의",
}


@dataclass(frozen=True)
class Credentials:
    mode: str
    client_id: str
    client_secret: str
    base_url: str
    trend_base_url: str

    @property
    def is_ready(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def headers(self) -> dict[str, str]:
        if self.mode == "legacy":
            return {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            }
        return {
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret,
        }

    def search_path(self, endpoint: SearchEndpoint) -> str:
        return endpoint.legacy_path if self.mode == "legacy" else endpoint.hub_path

    def trend_path(self) -> str:
        return TREND_LEGACY_PATH if self.mode == "legacy" else TREND_HUB_PATH


def _clean(value: str | None) -> str:
    value = (value or "").strip()
    # .env 예시 문구가 그대로 남아있는 경우는 미입력으로 취급
    if value.startswith("여기에"):
        return ""
    return value


def get_credentials(mode: str | None = None) -> Credentials:
    """환경 변수에서 인증 정보를 읽는다."""
    load_env()
    mode = (mode or os.getenv("NAVER_AUTH_MODE") or "hub").strip().lower()
    if mode not in {"hub", "legacy"}:
        mode = "hub"

    if mode == "legacy":
        client_id = _clean(os.getenv("NAVER_LEGACY_CLIENT_ID") or os.getenv("NAVER_CLIENT_ID"))
        client_secret = _clean(
            os.getenv("NAVER_LEGACY_CLIENT_SECRET") or os.getenv("NAVER_CLIENT_SECRET")
        )
        base_url = _clean(os.getenv("NAVER_LEGACY_BASE_URL")) or LEGACY_BASE_URL_DEFAULT
        trend_base_url = base_url
    else:
        client_id = _clean(os.getenv("NAVER_CLIENT_ID"))
        client_secret = _clean(os.getenv("NAVER_CLIENT_SECRET"))
        base_url = _clean(os.getenv("NAVER_HUB_BASE_URL")) or HUB_BASE_URL_DEFAULT
        trend_base_url = _clean(os.getenv("NAVER_TREND_BASE_URL")) or TREND_BASE_URL_DEFAULT

    return Credentials(
        mode=mode,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url.rstrip("/"),
        trend_base_url=trend_base_url.rstrip("/"),
    )
