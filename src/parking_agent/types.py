"""파이프라인 전 구간의 데이터 계약입니다.

이 파일은 P1(계약·통합 담당)만 수정합니다.
다른 담당자는 읽기만 하며, 필드 추가·변경이 필요하면 조 채널에 먼저 제안합니다.
모든 모듈은 여기 정의된 타입만 주고받으며, dict를 그대로 넘기지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypedDict

# --------------------------------------------------------------------------
# 공통 상수
# --------------------------------------------------------------------------

SortBy = Literal["distance", "price"]
DayType = Literal["weekday", "weekend", "holiday"]

#: 필수조건 탈락 사유입니다. 문자열을 임의로 만들지 않고 이 목록만 사용합니다.
RejectReason = Literal[
    "만차",
    "영업 종료",
    "영업시간 부족",
    "예산 초과",
    "거리 초과",
]


# --------------------------------------------------------------------------
# 1단계 · 사용자 입력에서 추출한 파라미터 (P2 산출)
# --------------------------------------------------------------------------


@dataclass
class RankingParams:
    """사용자 발화에서 추출한 검색 조건입니다.

    place만 필수이며 나머지는 미지정(None)일 수 있습니다.
    미지정 값을 임의의 기본값으로 채우지 않습니다. 기본값 적용은
    evaluate/rank 단계에서 수행하고, 적용 사실을 응답에 명시합니다.
    """

    place: str
    duration_minutes: int | None = None
    budget_won: int | None = None
    sort_by: SortBy = "distance"

    #: 직전 턴의 조건을 병합했는지 여부입니다. 리랭킹 응답 문구 분기에 사용합니다.
    merged_from_previous: bool = False


# --------------------------------------------------------------------------
# 2단계 · 앱이 주입하는 실행 컨텍스트 (P1 산출)
# --------------------------------------------------------------------------


@dataclass
class SearchPolicy:
    """검색 규칙입니다. LLM이 변경할 수 없는 코드 상수입니다."""

    adjacent_district_count: int = 5
    max_distance_m: int = 2000
    top_k: int = 3
    default_duration_minutes: int = 60


@dataclass
class RequestContext:
    """호출 1회 동안 고정되는 값입니다.

    대화 메시지에 넣지 않습니다. 위치정보가 대화 로그에 남지 않도록 하기 위함입니다.
    """

    user_id: str
    request_time: datetime  # KST
    day_type: DayType
    user_lat: float | None = None
    user_lng: float | None = None
    response_mode: Literal["driving", "normal"] = "normal"
    policy: SearchPolicy = field(default_factory=SearchPolicy)


# --------------------------------------------------------------------------
# 3단계 · 목적지 확정 (P3 산출)
# --------------------------------------------------------------------------


@dataclass
class Place:
    """지오코딩 결과 후보 1건입니다."""

    name: str
    address: str
    lat: float
    lng: float
    district: str  # 예: "강남구"
    #: 사용자 현재 위치로부터의 거리입니다. 위치 미제공 시 None입니다.
    distance_from_user_m: int | None = None


@dataclass
class GeocodeResult:
    """지오코딩 도구의 반환값입니다.

    예외를 던지지 않습니다. 실패도 정상 반환값으로 표현합니다.
    - candidates가 0건이면 message에 폴백 안내 문구가 담깁니다.
    - candidates가 2건 이상이면 호출자가 사용자에게 재확인합니다.
    """

    candidates: list[Place]
    message: str | None = None

    @property
    def is_confirmed(self) -> bool:
        return len(self.candidates) == 1


# --------------------------------------------------------------------------
# 4단계 · 주차장 후보 (P4 산출)
# --------------------------------------------------------------------------


@dataclass
class ParkingLot:
    """서울시 공영주차장 1건의 원본 정보입니다.

    확인할 수 없는 값은 추정하지 않고 None으로 둡니다.
    """

    code: str
    name: str
    address: str
    district: str
    lat: float | None = None
    lng: float | None = None

    total_slots: int | None = None
    current_cars: int | None = None

    #: "HHMM" 4자리 문자열입니다. 예: "0900". 24시간 운영은 "0000"/"2400"입니다.
    open_time: str | None = None
    close_time: str | None = None

    base_fee: int | None = None
    base_minutes: int | None = None
    extra_fee: int | None = None
    extra_minutes: int | None = None

    @property
    def available_slots(self) -> int | None:
        """잔여 주차면입니다. 원본 값이 없으면 None(확인 불가)입니다."""
        if self.total_slots is None or self.current_cars is None:
            return None
        return max(0, self.total_slots - self.current_cars)


@dataclass
class SearchResult:
    """주차장 검색 도구의 반환값입니다."""

    lots: list[ParkingLot]
    searched_districts: list[str]
    message: str | None = None


# --------------------------------------------------------------------------
# 5단계 · 판정과 계산 (P5 산출)
# --------------------------------------------------------------------------


@dataclass
class Evaluation:
    """주차장 1건에 대한 계산·판정 결과입니다.

    계산할 수 없는 항목은 None으로 두고 note에 사유를 적습니다.
    """

    lot: ParkingLot
    distance_m: int
    is_open: bool
    #: 마감까지 남은 분입니다. 24시간 운영이면 None입니다.
    minutes_until_close: int | None = None
    estimated_fee: int | None = None
    #: 요금 계산 근거입니다. 예: "기본 30분 1,000원 + 추가 90분 3,000원"
    fee_basis: str | None = None
    #: 할인 등 반영하지 못한 조건입니다.
    fee_note: str | None = None
    #: 기본값을 적용한 항목명입니다. 예: ["duration_minutes"]
    assumed_fields: list[str] = field(default_factory=list)


@dataclass
class Rejection:
    """필수조건을 만족하지 못해 제외된 후보입니다."""

    lot_name: str
    reasons: list[RejectReason]


@dataclass
class EvaluationResult:
    """판정 도구의 반환값입니다."""

    passed: list[Evaluation]
    rejected: list[Rejection]


# --------------------------------------------------------------------------
# 6단계 · 최종 추천 (P6 산출)
# --------------------------------------------------------------------------


@dataclass
class Recommendation:
    """응답에 노출되는 주차장 1건입니다.

    응답 문장의 모든 수치는 이 객체에서만 가져옵니다.
    출력 가드레일이 답변과 이 객체를 대조합니다.
    """

    rank: int
    name: str
    distance_m: int
    #: "3,200원" 또는 "계산 불가"
    fee_text: str
    #: "12면" 또는 "확인 불가"
    availability_text: str
    #: "24시간" 또는 "22:00 마감 (3시간 20분 남음)"
    hours_text: str
    reason: str = ""


@dataclass
class RankResult:
    """랭킹 도구의 반환값입니다. 0건이어도 예외를 던지지 않습니다."""

    recommendations: list[Recommendation]
    rejected: list[Rejection]
    sort_by: SortBy
    assumed_fields: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.recommendations) == 0


# --------------------------------------------------------------------------
# 파이프라인 최종 산출물
# --------------------------------------------------------------------------


@dataclass
class AgentResponse:
    """사용자에게 전달되는 최종 결과입니다."""

    answer: str
    params: RankingParams
    rank_result: RankResult | None = None
    #: 출력 가드레일 판정입니다. "SAFE" 또는 "UNSAFE"입니다.
    verdict: str = "SAFE"
    verdict_reason: str | None = None


# --------------------------------------------------------------------------
# LCEL Pipeline State (P1 계약) — Phase 2 동결
# --------------------------------------------------------------------------


class ParkingState(TypedDict, total=False):
    """LCEL 파이프라인이 공유하는 상태입니다.

    각 stage는 이 state를 입력받아 자신의 결과를 추가한 새 state를 반환합니다.
    초기 상태는 utterance/prev_params/ctx 3종이며, 이후 단계에서 순차적으로
    params → geocode_result → destination → search_result → evaluation_result
    → rank_result → answer → verdict 로 누적됩니다.
    """

    utterance: str
    prev_params: RankingParams | None
    ctx: RequestContext

    params: RankingParams
    is_valid: bool
    validation_message: str | None

    geocode_result: GeocodeResult
    destination: Place | None

    search_result: SearchResult
    evaluation_result: EvaluationResult
    rank_result: RankResult | None

    answer: str
    verdict: str
    verdict_reason: str | None
