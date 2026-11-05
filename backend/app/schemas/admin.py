from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from ..services import question_types


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


GuestPolicy = Literal["ROSTER_ONLY", "OPEN", "DISABLED"]


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=255)
    semester: str = Field(..., min_length=1, max_length=50)
    guest_policy: GuestPolicy = "ROSTER_ONLY"


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=255)
    semester: str | None = Field(None, min_length=1, max_length=50)
    guest_policy: GuestPolicy | None = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    semester: str
    guest_policy: GuestPolicy
    created_at: datetime


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


class RosterEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    netid: str
    full_name: str
    email: str
    is_active: bool
    imported_at: datetime


class RosterUploadResult(BaseModel):
    imported: int
    updated: int
    deactivated: int
    errors: list[str]


class RosterEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    netid: str | None = Field(None, min_length=1, max_length=100)
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None


class RosterRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    netid: str = Field(..., min_length=1, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)


class RosterImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[RosterRowIn] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameMetadata(BaseModel):
    """The `game` section of an import/export file — deliberately course-free."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)
    max_players: int = Field(150, ge=1, le=500)


class GameCreate(GameMetadata):
    course_id: int = Field(..., gt=0)


class GameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    max_players: int | None = Field(None, ge=1, le=500)


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    title: str
    description: str
    max_players: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


QUESTION_STRUCTURAL_FIELDS = ("type", "grading_type", "config", "answer_data")


def validate_question_structure(
    q_type: str, grading_type: str, config: dict, answer_data: dict
) -> None:
    """Raise ValueError if config/answer_data don't fit the question type and grading."""
    question_types.validate_structure(q_type, grading_type, config, answer_data)


def _known_question_type(v: str | None) -> str | None:
    if v is not None and v not in question_types.QUESTION_TYPES:
        raise ValueError(
            f"type must be one of: {', '.join(question_types.QUESTION_TYPES)}"
        )
    return v


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(..., max_length=50)
    grading_type: str = Field(..., pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str = Field(..., min_length=1, max_length=2000)
    config: dict = Field(default_factory=dict)
    answer_data: dict = Field(default_factory=dict)
    time_limit_seconds: int = Field(30, ge=2, le=300)
    points_value: float = Field(1.0, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)

    _check_type = field_validator("type")(_known_question_type)

    @model_validator(mode="after")
    def validate_structure(self) -> QuestionCreate:
        validate_question_structure(
            self.type, self.grading_type, self.config, self.answer_data
        )
        return self


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = Field(None, max_length=50)
    grading_type: str | None = Field(None, pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str | None = Field(None, min_length=1, max_length=2000)
    config: dict | None = None
    answer_data: dict | None = None
    time_limit_seconds: int | None = Field(None, ge=2, le=300)
    points_value: float | None = Field(None, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)

    _check_type = field_validator("type")(_known_question_type)

    def touches_structure(self) -> bool:
        return any(getattr(self, f) is not None for f in QUESTION_STRUCTURAL_FIELDS)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    game_id: int
    type: str
    grading_type: str
    prompt: str
    config: dict
    answer_data: dict
    time_limit_seconds: int
    points_value: float
    order_index: int
    created_at: datetime


class QuestionReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[int] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Users (local accounts)
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=72)
    email: EmailStr | None = None

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(
        None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=72)
    role: str | None = Field(None, pattern="^(USER|ADMIN)$")

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str | None
    netid: str | None
    display_name: str | None
    email: str | None
    role: str
    created_at: datetime
    last_login: datetime | None


# ---------------------------------------------------------------------------
# Access management
# ---------------------------------------------------------------------------


class CourseAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int
    role: str = Field(..., pattern="^(HOST|PLAYER)$")


class GameAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: int


class UserWithAccessResponse(UserResponse):
    course_access: list[dict]
    game_access: list[int]


# ---------------------------------------------------------------------------
# Sessions (admin view)
# ---------------------------------------------------------------------------


class AdminSessionItem(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    session_id: str
    room_code: str
    status: str
    game_id: int
    game_title: str
    course_id: int
    course_name: str
    course_semester: str
    host_display_name: str | None
    created_at: datetime
    completed_at: datetime | None
    player_count: int


class HostSessionItem(AdminSessionItem):
    can_delete: (
        bool  # deletion (/game/sessions/{id}) is limited to the session host or ADMIN
    )


# ---------------------------------------------------------------------------
# Session detail and question feedback (docs/plans/question-feedback.md §4.6)
# ---------------------------------------------------------------------------


class FeedbackCounts(BaseModel):
    up: int = 0
    down: int = 0
    flagged: int = 0


class SessionDetailInfo(BaseModel):
    session_id: str
    room_code: str
    status: str
    game_title: str
    course_name: str
    course_semester: str
    created_at: datetime | None
    completed_at: datetime | None
    host_display_name: str | None


class SessionDetailPlayer(BaseModel):
    user_id: str
    display_name: str
    identifier: str = Field(..., description="netid, username or guest email")
    kind: Literal["netid", "local", "guest"]
    total_points: float


class SessionDetailResponse(BaseModel):
    """One player's answer and/or feedback on a question (answer fields are null when
    the player only voted)."""

    user_id: str
    answer_data: dict | None
    is_correct: bool | None
    points: float | None
    answer_time_ms: int | None
    rating: Literal["UP", "DOWN"] | None
    flagged: bool


class SessionDetailQuestion(BaseModel):
    question_id: int
    order_index: int
    type: str
    grading_type: str
    prompt: str
    config: dict
    answer_data: dict
    points_value: float
    feedback: FeedbackCounts
    responses: list[SessionDetailResponse]


class SessionDetail(BaseModel):
    session: SessionDetailInfo
    players: list[SessionDetailPlayer]
    questions: list[SessionDetailQuestion]


# ---------------------------------------------------------------------------
# Images (T8)
# ---------------------------------------------------------------------------


class ImageUsage(BaseModel):
    """One (question, field) that references an image."""

    game_id: int
    game_title: str
    question_id: int
    question_number: int = Field(..., description="1-based, as the editor numbers them")
    field: Literal["prompt", "option", "pin_drop"]


class ImageResponse(BaseModel):
    id: str
    course_id: int
    filename: str
    content_type: str
    width: int
    height: int
    byte_size: int
    sha256: str
    created_at: datetime
    updated_at: datetime
    url: str
    used_by: list[ImageUsage]


class ImageUploadResponse(ImageResponse):
    deduplicated: bool
