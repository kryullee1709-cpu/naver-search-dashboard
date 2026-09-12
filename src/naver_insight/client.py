"""NAVER API HUB 호출 클라이언트.

- 검색 API: GET {base}/search/v1/{type}
- 검색어 트렌드: POST {base}/datalab/v1/search
공식 문서: https://api.ncloud-docs.com/docs/naver-api-hub-overview
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .settings import (
    SEARCH_ENDPOINTS,
    SHOPPING_CATEGORY_PATH,
    SHOPPING_DEVICE_PATH,
    SHOPPING_KEYWORD_PATH,
    Credentials,
    SearchEndpoint,
    get_credentials,
)


class NaverApiError(RuntimeError):
    """API 호출 실패."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SearchResult:
    endpoint: str
    keyword: str
    total: int
    items: list[dict]
    last_build_date: str | None = None


class NaverClient:
    def __init__(self, credentials: Credentials | None = None, timeout: int = 10):
        self.credentials = credentials or get_credentials()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.credentials.headers())

    # ------------------------------------------------------------------ 공통
    def _request(self, method: str, path: str, base: str | None = None, **kwargs) -> dict:
        url = f"{base or self.credentials.base_url}{path}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:  # 네트워크 오류
            raise NaverApiError(f"네트워크 오류: {exc}") from exc

        if response.status_code == 429:
            raise NaverApiError("호출 한도(RPS)를 초과했습니다. 잠시 후 다시 시도하세요.", 429)
        if response.status_code == 401:
            # 키는 맞지만 해당 상품을 이용 신청하지 않은 경우 errorCode 210이 온다.
            if "210" in response.text or "subscription" in response.text.lower():
                raise NaverApiError(
                    "이용 신청이 되지 않은 API입니다(401/210). 네이버 클라우드 플랫폼 콘솔에서 "
                    "해당 상품(검색어 트렌드 등)을 신청한 뒤 다시 시도하세요.",
                    401,
                )
            raise NaverApiError("인증 실패(401). .env의 Client ID/Secret을 확인하세요.", 401)
        if response.status_code == 404:
            raise NaverApiError(
                f"엔드포인트를 찾을 수 없습니다(404): {url}", 404
            )
        if response.status_code >= 400:
            raise NaverApiError(
                f"HTTP {response.status_code}: {response.text[:300]}", response.status_code
            )
        try:
            return response.json()
        except ValueError as exc:
            raise NaverApiError(f"JSON 파싱 실패: {response.text[:200]}") from exc

    # ------------------------------------------------------------- 검색 API
    def search(
        self,
        endpoint_key: str,
        query: str,
        display: int = 100,
        start: int = 1,
        sort: str | None = None,
    ) -> SearchResult:
        endpoint: SearchEndpoint = SEARCH_ENDPOINTS[endpoint_key]
        params: dict[str, str | int] = {
            "query": query,
            "display": min(display, endpoint.max_display),
            "start": min(start, endpoint.max_start),
        }
        if sort and sort in endpoint.sort_options:
            params["sort"] = sort
        elif endpoint.sort_options:
            params["sort"] = endpoint.sort_options[0]
        params.update(endpoint.extra_params)

        payload = self._request("GET", self.credentials.search_path(endpoint), params=params)
        return SearchResult(
            endpoint=endpoint_key,
            keyword=query,
            total=int(payload.get("total", 0) or 0),
            items=payload.get("items", []) or [],
            last_build_date=payload.get("lastBuildDate"),
        )

    def search_paged(
        self,
        endpoint_key: str,
        query: str,
        target: int = 100,
        sort: str | None = None,
        pause: float = 0.1,
    ) -> SearchResult:
        """display 상한을 넘겨서 모아야 할 때 start 를 늘려가며 수집한다."""
        endpoint = SEARCH_ENDPOINTS[endpoint_key]
        collected: list[dict] = []
        total = 0
        last_build = None
        start = 1
        while len(collected) < target and start <= endpoint.max_start:
            take = min(endpoint.max_display, target - len(collected))
            result = self.search(endpoint_key, query, display=take, start=start, sort=sort)
            total = result.total or total
            last_build = result.last_build_date or last_build
            if not result.items:
                break
            collected.extend(result.items)
            if len(result.items) < take:
                break
            start += take
            if start > endpoint.max_start:
                break
            time.sleep(pause)
        return SearchResult(
            endpoint=endpoint_key,
            keyword=query,
            total=total,
            items=collected[:target],
            last_build_date=last_build,
        )

    # -------------------------------------------------------- 검색어 트렌드
    def search_trend(
        self,
        start_date: str,
        end_date: str,
        keyword_groups: list[dict],
        time_unit: str = "date",
        device: str = "",
        ages: list[str] | None = None,
        gender: str = "",
    ) -> dict:
        body: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
        }
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages

        return self._request(
            "POST",
            self.credentials.trend_path(),
            base=self.credentials.trend_base_url,
            json=body,
            headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------ 쇼핑인사이트
    def _shopping(self, path: str, body: dict) -> dict:
        return self._request(
            "POST",
            path,
            base=self.credentials.trend_base_url,
            json=body,
            headers={"Content-Type": "application/json"},
        )

    def shopping_categories(
        self,
        start_date: str,
        end_date: str,
        categories: list[dict],
        time_unit: str = "month",
        device: str = "",
        gender: str = "",
        ages: list[str] | None = None,
    ) -> dict:
        """분야별 클릭 추이. categories 는 {"name":..., "param":[코드]} 배열."""
        body: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": categories,
        }
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages
        return self._shopping(SHOPPING_CATEGORY_PATH, body)

    def shopping_keywords(
        self,
        start_date: str,
        end_date: str,
        category_code: str,
        keywords: list[dict],
        time_unit: str = "month",
        device: str = "",
        gender: str = "",
        ages: list[str] | None = None,
    ) -> dict:
        """분야 안에서 키워드별 클릭 추이. keywords 는 {"name":..., "param":[검색어]} 배열."""
        body: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category_code,
            "keyword": keywords,
        }
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages
        return self._shopping(SHOPPING_KEYWORD_PATH, body)

    def shopping_segment(
        self,
        start_date: str,
        end_date: str,
        category_code: str,
        time_unit: str = "month",
        device: str = "",
        gender: str = "",
        ages: list[str] | None = None,
    ) -> dict:
        """분야의 기기·성별·연령 필터별 추이 (동일 엔드포인트에서 필터로 구분)."""
        body: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category_code,
        }
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages
        return self._shopping(SHOPPING_DEVICE_PATH, body)
