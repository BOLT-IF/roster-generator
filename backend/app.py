"""FastAPI backend for badminton roster generation."""

from __future__ import annotations

import os
import secrets
import time
import hashlib
import json
from collections import defaultdict
from copy import deepcopy

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, field_validator
import unicodedata
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError

from env import load_local_env

load_local_env()

from cache import cache
from database import (
    CompletedSessionStatsRecord,
    PlayerRecord,
    PlayerPartnerSessionStatsRecord,
    PlayerSessionStatsRecord,
    PlayerStatsSummaryRecord,
    SessionRoundRecord,
    SessionScoreRecord,
    SharedSessionRecord,
    get_db_session,
    init_db,
)
from roster_engine import (
    find_duplicate_fixed_pair_matchups,
    generate_fixed_pair_knockout_roster,
    generate_roster,
    validate_roster,
    RosterError,
)

app = FastAPI(title="Badminton Roster API")

ADMIN_RECOVERY_TOKEN = os.getenv("ADMIN_RECOVERY_TOKEN", "thisismytoken")
DEFAULT_PLAYER_DIRECTORY = [
    "DG", "Hari", "Ashok", "Jitu", "Satya", "Krupa", "Kishore", "Malli",
    "Chiru", "Vivek", "Dhawan", "Avinash", "Vikram", "Marideva", "Sai",
    "Amit", "Varun", "Phani", "Bhaskar", "Sai Krishna", "Adi", "Bharat",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_error_details(value):
    """Drop unencodable characters (lone surrogates) from error payloads.

    FastAPI's default request-validation handler echoes the raw input inside
    the 422 details; a lone surrogate in that input made the response itself
    fail to UTF-8 encode, turning a clean 422 into a 500.
    """
    if isinstance(value, str):
        return value.encode("utf-8", "ignore").decode("utf-8")
    if isinstance(value, list):
        return [_sanitize_error_details(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_error_details(item) for key, item in value.items()}
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_error_details(jsonable_encoder(exc.errors()))},
    )


@app.on_event("startup")
def startup():
    init_db()
    cache.initialize()
    with get_db_session() as db:
        _ensure_player_registry(db)


def _cache_ttl(name: str, default_seconds: int) -> int:
    return cache.ttl(name, default_seconds)


def _cache_get_or_set(namespace: str, key_parts: list[str], ttl_seconds: int, builder):
    cache_key = cache.build_key(namespace, *key_parts)
    cached = cache.get_json(cache_key)
    if cached is not None:
        return cached

    value = builder()
    serialized = jsonable_encoder(value)
    cache.set_json(cache_key, serialized, ttl_seconds=ttl_seconds)
    return serialized


def _cache_token_key(token: str | None) -> str:
    if not token:
        return "anon"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _invalidate_session_views(session_id: str, include_analytics: bool = True):
    cache.bump("sessions")
    cache.bump(f"session:{session_id}")
    if include_analytics:
        cache.bump("history")
        cache.bump("player-stats")


def _invalidate_player_views():
    cache.bump("players")
    cache.bump("player-stats")


class RosterRequest(BaseModel):
    players: list[str]
    fixed_pairs: list[list[str]] = []
    draw_type: str = "round_robin"
    num_courts: int
    court_numbers: list[str] | None = None
    rounds: int = 9
    limits: dict[str, int] = {}
    pair_games: int = 3
    pair_start_round: int = 5
    max_consecutive_rest: int = 1
    seed: int | None = None

    @field_validator("players")
    @classmethod
    def players_not_empty(cls, v):
        if len(v) < 4:
            raise ValueError("Need at least 4 players")
        if len(v) > 64:
            raise ValueError("At most 64 players are supported")
        seen = set()
        for name in v:
            if not name or not name.strip():
                raise ValueError("Player names must be non-empty")
            if any(0xD800 <= ord(ch) <= 0xDFFF for ch in name):
                raise ValueError("Player names contain invalid characters")
            if " & " in name or "/" in name:
                raise ValueError("Player names cannot contain ' & ' or '/' (reserved for pair keys)")
            if name in seen:
                raise ValueError(f"Duplicate player name: {name}")
            seen.add(name)
        return v

    @field_validator("num_courts")
    @classmethod
    def courts_positive(cls, v):
        if v < 1:
            raise ValueError("Need at least 1 court")
        if v > 10:
            raise ValueError("At most 10 courts are supported")
        return v

    @field_validator("rounds")
    @classmethod
    def rounds_in_range(cls, v):
        if v < 1:
            raise ValueError("Need at least 1 round")
        if v > 50:
            raise ValueError("At most 50 rounds are supported")
        return v

    @field_validator("court_numbers")
    @classmethod
    def court_numbers_not_empty(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("court_numbers cannot be empty")
        return v

    @field_validator("pair_games")
    @classmethod
    def pair_games_at_least_one(cls, v):
        if v < 1:
            raise ValueError("pair_games must be at least 1")
        return v

    @field_validator("pair_start_round")
    @classmethod
    def pair_start_round_at_least_one(cls, v):
        if v < 1:
            raise ValueError("pair_start_round must be at least 1")
        return v

    @field_validator("max_consecutive_rest")
    @classmethod
    def max_consecutive_rest_in_range(cls, v):
        if v < 1:
            raise ValueError("max_consecutive_rest must be at least 1")
        if v > 10:
            raise ValueError("max_consecutive_rest must be at most 10")
        return v


class CourtResult(BaseModel):
    team_a: list[str]
    team_b: list[str]


class RoundResult(BaseModel):
    round: int
    courts: list[CourtResult]
    resting: list[str]


class RosterResponse(BaseModel):
    rounds: list[RoundResult]
    court_numbers: list[str]
    rest_counts: dict[str, int]
    fixed_pair_counts: dict[str, int]
    violations: list[str]
    warnings: list[str]


class RosterRevalidateRequest(RosterRequest):
    roster: RosterResponse


def _has_fixed_pair_knockout_schedule(draw_type: str, fixed_pairs: list[tuple[str, str]]) -> bool:
    return draw_type == "league_knockout" and len(fixed_pairs) > 0


def _collect_roster_violations(
    rounds: list[dict],
    limits: dict[str, int],
    max_consecutive_rest: int,
    fixed_pairs: list[tuple[str, str]],
    fixed_pair_counts: dict[tuple[str, str], int],
    pair_games: int,
    pair_start_round: int,
    draw_type: str,
):
    violations = validate_roster(
        rounds,
        limits,
        max_consecutive_rest,
        fixed_pairs,
        fixed_pair_counts,
        pair_games,
        pair_start_round,
    )
    if _has_fixed_pair_knockout_schedule(draw_type, fixed_pairs):
        violations.extend(find_duplicate_fixed_pair_matchups(rounds, fixed_pairs))
    return violations


class DrawConfig(BaseModel):
    draw_type: str = "round_robin"
    league_meetings: int = 1
    knockout_qualifiers: int = 4

    @field_validator("draw_type")
    @classmethod
    def draw_type_supported(cls, v):
        if v not in ("round_robin", "league_knockout"):
            raise ValueError("draw_type must be 'round_robin' or 'league_knockout'")
        return v

    @field_validator("knockout_qualifiers")
    @classmethod
    def qualifiers_supported(cls, v):
        if v not in (2, 4):
            raise ValueError("knockout_qualifiers must be 2 or 4")
        return v


class SessionPlayerReference(BaseModel):
    player_id: str
    full_name: str
    short_name: str


class SharedSessionCreateRequest(BaseModel):
    roster: RosterResponse
    draw_config: DrawConfig
    name: str | None = None
    selected_players: list[SessionPlayerReference] = []
    fixed_pair_player_ids: list[list[str]] = []
    fixed_pairs: list[list[str]] = []
    limits: dict[str, int] = {}

    @field_validator("name")
    @classmethod
    def validate_session_name(cls, value):
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in cleaned):
            raise ValueError("Session name contains invalid characters")
        if len(cleaned) > 120:
            raise ValueError("Session name must be 120 characters or fewer")
        return cleaned
    pair_games: int = 3
    pair_start_round: int = 5
    max_consecutive_rest: int = 1
    admin_token: str | None = None


class SharedSessionResponse(BaseModel):
    session_id: str
    name: str
    created_at: str
    updated_at: str
    can_edit: bool
    edit_token: str | None = None
    roster: RosterResponse
    draw_config: DrawConfig
    league_scores_by_round: list[list[dict[str, int | str]]]
    active_league_round: int
    ended_league_rounds: list[bool]
    knockout_scores_by_round: list[list[dict[str, int | str]]]
    active_knockout_round: int
    ended_knockout_rounds: list[bool]
    can_undo: bool
    version: int


class SharedSessionSummary(BaseModel):
    session_id: str
    name: str
    created_at: str
    updated_at: str
    draw_type: str
    status: str
    ended_rounds: int
    total_rounds: int
    live_rounds: int


class CompletedSessionStatsResponse(BaseModel):
    session_id: str
    session_name: str
    draw_type: str
    completed_at: str
    total_players: int
    total_matches: int
    champion_pair: str | None = None
    top_player: str | None = None


class PlayerResponse(BaseModel):
    player_id: str
    full_name: str
    short_name: str
    source: str
    aliases: list[str] = []
    created_at: str | None = None


class PlayerStatsSummaryResponse(BaseModel):
    player_id: str | None = None
    full_name: str | None = None
    short_name: str | None = None
    player_name: str
    sessions_played: int
    matches_played: int
    wins: int
    losses: int
    draws: int
    points: int
    point_difference: int
    league_matches_played: int
    league_wins: int
    league_losses: int
    league_draws: int
    league_points: int
    league_point_difference: int
    knockout_matches_played: int
    knockout_wins: int
    knockout_losses: int
    knockout_draws: int
    knockout_points: int
    knockout_point_difference: int
    championships: int
    win_rate: float
    last_session_at: str | None = None


class PartnerStatsResponse(BaseModel):
    partner_id: str | None = None
    full_name: str | None = None
    short_name: str | None = None
    partner_name: str
    matches_played: int
    wins: int
    win_rate: float


class PlayerStatsDetailResponse(PlayerStatsSummaryResponse):
    most_played_partner: PartnerStatsResponse | None = None
    top_partners: list[PartnerStatsResponse]


class RoundStartRequest(BaseModel):
    stage: str
    round_index: int


class ScoreUpdateRequest(BaseModel):
    stage: str
    round_index: int
    court_index: int
    team_key: str
    value: int | None = Field(default=None, ge=0, le=99)


class BatchScoreUpdateRequest(BaseModel):
    stage: str
    round_index: int
    updates: list[ScoreUpdateRequest]


class RoundEndRequest(BaseModel):
    stage: str
    round_index: int


class RoundEditRequest(BaseModel):
    stage: str
    round_index: int
    confirm_knockout_wipe: bool = False


class SessionRenameRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Session name is required")
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in cleaned):
            raise ValueError("Session name contains invalid characters")
        if len(cleaned) > 120:
            raise ValueError("Session name must be 120 characters or fewer")
        return cleaned


class ScoreMutationResponse(BaseModel):
    ok: bool = True
    version: int


def _sanitize_player_name(value: str) -> str:
    # Collapse all whitespace - including newlines and control characters like
    # NUL, which were previously stored verbatim - into single spaces.
    cleaned = "".join(
        " " if ch.isspace() or unicodedata.category(ch) == "Cc" else ch for ch in value
    )
    return " ".join(cleaned.strip().split())


def _reject_reserved_name_characters(value: str, field: str):
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ValueError(f"{field} contains invalid characters")
    if " & " in value or "/" in value:
        raise ValueError(f"{field} cannot contain ' & ' or '/' (reserved for pair keys)")


class PlayerCreateRequest(BaseModel):
    full_name: str
    short_name: str

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str):
        cleaned = _sanitize_player_name(value)
        if not cleaned:
            raise ValueError("Value is required")
        if len(cleaned) > 120:
            raise ValueError("Value must be 120 characters or fewer")
        _reject_reserved_name_characters(cleaned, "Full name")
        return cleaned

    @field_validator("short_name")
    @classmethod
    def validate_short_name(cls, value: str):
        cleaned = _sanitize_player_name(value)
        if not cleaned:
            raise ValueError("Value is required")
        if len(cleaned) > 60:
            raise ValueError("Short name must be 60 characters or fewer")
        _reject_reserved_name_characters(cleaned, "Short name")
        return cleaned


class PlayerUpdateRequest(PlayerCreateRequest):
    pass


class PlayerDeleteRequest(BaseModel):
    admin_token: str
    delete_history: bool = False


def _create_empty_scores(rounds: list[RoundResult]) -> list[list[dict[str, int | str]]]:
    return [
        [
            {"teamA": "", "teamB": ""}
            for _ in round.courts
        ]
        for round in rounds
    ]


def _ensure_score_slot(scores: list[list[dict[str, int | str]]], round_index: int, court_index: int):
    while len(scores) <= round_index:
        scores.append([])

    while len(scores[round_index]) <= court_index:
        scores[round_index].append({"teamA": "", "teamB": ""})


def _normalize_player_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _generate_player_id() -> str:
    return f"plr_{secrets.token_hex(4)}"


def _serialize_player(row: PlayerRecord) -> PlayerResponse:
    return PlayerResponse(
        player_id=row.player_id,
        full_name=row.full_name,
        short_name=row.short_name,
        source=row.source,
        aliases=[alias for alias in (row.aliases or []) if alias],
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _create_player_record(db, full_name: str, short_name: str, *, source: str):
    normalized_full_name = _normalize_player_name(full_name)
    normalized_short_name = _normalize_player_name(short_name)
    player = PlayerRecord(
        player_id=_generate_player_id(),
        full_name=full_name,
        short_name=short_name,
        normalized_full_name=normalized_full_name,
        normalized_short_name=normalized_short_name,
        aliases=[],
        is_deleted=False,
        deleted_at=None,
        source=source,
    )
    db.add(player)
    db.flush()
    return player


def _ensure_legacy_player_record(db, full_name: str, short_name: str):
    normalized_full_name = _normalize_player_name(full_name)
    normalized_short_name = _normalize_player_name(short_name)

    existing_player = db.scalar(
        select(PlayerRecord).where(
            or_(
                PlayerRecord.normalized_full_name == normalized_full_name,
                PlayerRecord.normalized_short_name == normalized_short_name,
            )
        )
    )
    if existing_player:
        return existing_player, False

    values = {
        "player_id": _generate_player_id(),
        "full_name": full_name,
        "short_name": short_name,
        "normalized_full_name": normalized_full_name,
        "normalized_short_name": normalized_short_name,
        "aliases": [],
        "is_deleted": False,
        "deleted_at": None,
        "source": "legacy",
    }

    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "postgresql":
        statement = postgresql_insert(PlayerRecord).values(**values).on_conflict_do_nothing()
        db.execute(statement)
        db.flush()
    elif dialect_name == "sqlite":
        statement = sqlite_insert(PlayerRecord).values(**values).on_conflict_do_nothing()
        db.execute(statement)
        db.flush()
    else:
        player = _create_player_record(db, full_name, short_name, source="legacy")
        return player, True

    player = db.scalar(
        select(PlayerRecord).where(
            or_(
                PlayerRecord.normalized_full_name == normalized_full_name,
                PlayerRecord.normalized_short_name == normalized_short_name,
            )
        )
    )
    return player, bool(player and player.player_id == values["player_id"])


def _iter_legacy_player_names(payload: dict):
    player_directory = payload.get("player_directory") or []
    for player in player_directory:
        if isinstance(player, dict):
            if player.get("short_name"):
                yield player["short_name"]
            if player.get("full_name"):
                yield player["full_name"]

    for round_data in payload.get("roster", {}).get("rounds", []):
        for court in round_data.get("courts", []):
            for name in court.get("team_a", []):
                yield name
            for name in court.get("team_b", []):
                yield name
        for name in round_data.get("resting", []):
            yield name


def _ensure_player_registry(db):
    existing_players = db.scalars(select(PlayerRecord).order_by(PlayerRecord.full_name.asc())).all()
    active_players = [row for row in existing_players if not row.is_deleted]
    existing_full_names = {row.normalized_full_name for row in existing_players}
    existing_short_names = {row.normalized_short_name for row in existing_players}
    existing_aliases = {
        _normalize_player_name(alias)
        for row in existing_players
        for alias in (row.aliases or [])
        if isinstance(alias, str) and alias.strip()
    }
    discovered_names = set()

    session_records = db.scalars(select(SharedSessionRecord)).all()
    for record in session_records:
        payload = _upgrade_session_payload(deepcopy(record.data))
        for name in _iter_legacy_player_names(payload):
            cleaned = " ".join(str(name).strip().split())
            if cleaned:
                discovered_names.add(cleaned)

    for row in db.scalars(select(PlayerSessionStatsRecord.player_name)).all():
        cleaned = " ".join(str(row).strip().split())
        if cleaned:
            discovered_names.add(cleaned)

    for row in db.scalars(select(PlayerPartnerSessionStatsRecord.player_name)).all():
        cleaned = " ".join(str(row).strip().split())
        if cleaned:
            discovered_names.add(cleaned)

    for row in db.scalars(select(PlayerPartnerSessionStatsRecord.partner_name)).all():
        cleaned = " ".join(str(row).strip().split())
        if cleaned:
            discovered_names.add(cleaned)

    for row in db.scalars(select(PlayerStatsSummaryRecord.player_name)).all():
        cleaned = " ".join(str(row).strip().split())
        if cleaned:
            discovered_names.add(cleaned)

    if not active_players and not discovered_names:
        discovered_names.update(DEFAULT_PLAYER_DIRECTORY)

    changed = False
    for name in sorted(discovered_names):
        normalized = _normalize_player_name(name)
        if normalized in existing_full_names or normalized in existing_short_names or normalized in existing_aliases:
            continue
        player, created = _ensure_legacy_player_record(db, name, name)
        if not player:
            continue
        existing_full_names.add(player.normalized_full_name)
        existing_short_names.add(player.normalized_short_name)
        existing_aliases.update(
            _normalize_player_name(alias)
            for alias in (player.aliases or [])
            if isinstance(alias, str) and alias.strip()
        )
        changed = changed or created

    if changed:
        db.flush()

    for player in db.scalars(select(PlayerRecord)).all():
        next_aliases = [
            alias
            for alias in dict.fromkeys(
                alias
                for alias in (player.aliases or [])
                if isinstance(alias, str) and alias.strip()
            )
        ]
        if next_aliases != (player.aliases or []):
            player.aliases = next_aliases
            db.add(player)
            existing_aliases.update(_normalize_player_name(alias) for alias in next_aliases)


def _find_player_by_name(db, name: str) -> PlayerRecord | None:
    normalized = _normalize_player_name(name)
    if not normalized:
        return None
    player = db.scalar(
        select(PlayerRecord).where(PlayerRecord.normalized_short_name == normalized, PlayerRecord.is_deleted.is_(False))
    )
    if player:
        return player
    player = db.scalar(
        select(PlayerRecord).where(PlayerRecord.normalized_full_name == normalized, PlayerRecord.is_deleted.is_(False))
    )
    if player:
        return player

    for candidate in db.scalars(select(PlayerRecord).where(PlayerRecord.is_deleted.is_(False))).all():
        aliases = {_normalize_player_name(alias) for alias in (candidate.aliases or []) if alias}
        if normalized in aliases:
            return candidate
    return None


def _player_uses_name(player: PlayerRecord, normalized_name: str) -> bool:
    if player.normalized_full_name == normalized_name or player.normalized_short_name == normalized_name:
        return True
    return normalized_name in {
        _normalize_player_name(alias)
        for alias in (player.aliases or [])
        if isinstance(alias, str) and alias.strip()
    }


def _find_name_conflict(
    db,
    normalized_name: str,
    exclude_player_id: str | None = None,
    *,
    include_deleted: bool = False,
) -> PlayerRecord | None:
    for player in db.scalars(select(PlayerRecord)).all():
        if exclude_player_id and player.player_id == exclude_player_id:
            continue
        if player.is_deleted and not include_deleted:
            continue
        if _player_uses_name(player, normalized_name):
            return player
    return None


def _find_soft_deleted_player_for_restore(db, normalized_full_name: str, normalized_short_name: str) -> PlayerRecord | None:
    matches = []
    for player in db.scalars(select(PlayerRecord).where(PlayerRecord.is_deleted.is_(True))).all():
        # Restore only when the request matches the deleted player's CURRENT
        # full name (the documented recreate contract - a fresh short name is
        # allowed and rebrands the player). Old aliases and short-only matches
        # must NOT restore: they silently rebranded the deleted player
        # whenever a new person reused one of those names.
        if player.normalized_full_name == normalized_full_name:
            matches.append(player)

    if not matches:
        return None

    unique_matches = {player.player_id: player for player in matches}
    if len(unique_matches) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple deleted players match this name. Edit an existing player instead of creating a new one.",
        )

    return next(iter(unique_matches.values()))


def _restore_deleted_player(db, player: PlayerRecord, full_name: str, short_name: str) -> PlayerRecord:
    normalized_full_name = _normalize_player_name(full_name)
    normalized_short_name = _normalize_player_name(short_name)

    alias_pool = []
    for value in (player.full_name, player.short_name, *(player.aliases or [])):
        cleaned = " ".join(str(value).strip().split())
        normalized_value = _normalize_player_name(cleaned)
        if not cleaned or normalized_value in {normalized_full_name, normalized_short_name}:
            continue
        alias_pool.append(cleaned)

    player.full_name = full_name
    player.short_name = short_name
    player.normalized_full_name = normalized_full_name
    player.normalized_short_name = normalized_short_name
    player.aliases = list(dict.fromkeys(alias_pool))
    player.is_deleted = False
    player.deleted_at = None
    db.add(player)
    db.flush()
    db.refresh(player)
    return player


def _player_related_names(player: PlayerRecord) -> list[str]:
    names = []
    for value in [player.full_name, player.short_name, *(player.aliases or [])]:
        cleaned = " ".join(str(value).strip().split())
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return names


def _delete_player_history(db, player: PlayerRecord):
    related_names = _player_related_names(player)
    if not related_names:
        return

    for row in db.scalars(
        select(PlayerSessionStatsRecord).where(PlayerSessionStatsRecord.player_name.in_(related_names))
    ).all():
        db.delete(row)

    for row in db.scalars(
        select(PlayerPartnerSessionStatsRecord).where(
            (PlayerPartnerSessionStatsRecord.player_name.in_(related_names)) |
            (PlayerPartnerSessionStatsRecord.partner_name.in_(related_names))
        )
    ).all():
        db.delete(row)

    for row in db.scalars(
        select(PlayerStatsSummaryRecord).where(PlayerStatsSummaryRecord.player_name.in_(related_names))
    ).all():
        db.delete(row)

    db.flush()
    _rebuild_player_stats_summary(db)


def _upgrade_session_payload(payload: dict) -> dict:
    payload.setdefault("edit_token", secrets.token_urlsafe(12))
    payload.setdefault("undo_stack", [])
    return payload


def _hydrate_legacy_session_storage(db, record: SharedSessionRecord, payload: dict):
    existing_round = db.scalar(
        select(SessionRoundRecord).where(SessionRoundRecord.session_id == record.session_id).limit(1)
    )
    existing_score = db.scalar(
        select(SessionScoreRecord).where(SessionScoreRecord.session_id == record.session_id).limit(1)
    )
    if existing_round or existing_score:
        return payload

    league_rounds = payload.get("roster", {}).get("rounds", [])
    legacy_league_scores = payload.get("league_scores_by_round", [])
    legacy_knockout_scores = payload.get("knockout_scores_by_round", [])
    legacy_ended_league = payload.get("ended_league_rounds", [False for _ in league_rounds])
    legacy_ended_knockout = payload.get("ended_knockout_rounds", [])
    legacy_active_league = payload.get("active_league_round", -1)
    legacy_active_knockout = payload.get("active_knockout_round", -1)

    for round_index in range(len(league_rounds)):
        db.add(
            SessionRoundRecord(
                session_id=record.session_id,
                stage="league",
                round_index=round_index,
                started=round_index <= legacy_active_league,
                ended=legacy_ended_league[round_index] if round_index < len(legacy_ended_league) else False,
            )
        )

    knockout_round_total = max(len(legacy_knockout_scores), len(legacy_ended_knockout), legacy_active_knockout + 1)
    for round_index in range(knockout_round_total):
        db.add(
            SessionRoundRecord(
                session_id=record.session_id,
                stage="knockout",
                round_index=round_index,
                started=round_index <= legacy_active_knockout,
                ended=legacy_ended_knockout[round_index] if round_index < len(legacy_ended_knockout) else False,
            )
        )

    for stage, rounds in (("league", legacy_league_scores), ("knockout", legacy_knockout_scores)):
        for round_index, round_scores in enumerate(rounds):
            for court_index, score in enumerate(round_scores):
                team_a_score = None if score.get("teamA", "") == "" else score.get("teamA")
                team_b_score = None if score.get("teamB", "") == "" else score.get("teamB")
                if team_a_score is None and team_b_score is None:
                    continue
                db.add(
                    SessionScoreRecord(
                        session_id=record.session_id,
                        stage=stage,
                        round_index=round_index,
                        court_index=court_index,
                        team_a_score=team_a_score,
                        team_b_score=team_b_score,
                    )
                )

    next_payload = deepcopy(payload)
    for key in (
        "league_scores_by_round",
        "active_league_round",
        "ended_league_rounds",
        "knockout_scores_by_round",
        "active_knockout_round",
        "ended_knockout_rounds",
    ):
        next_payload.pop(key, None)

    record.data = next_payload
    db.add(record)
    db.flush()
    return next_payload


def _get_round_state(db, session_id: str, stage: str, total_rounds: int):
    round_records = db.scalars(
        select(SessionRoundRecord)
        .where(SessionRoundRecord.session_id == session_id, SessionRoundRecord.stage == stage)
        .order_by(SessionRoundRecord.round_index.asc())
    ).all()
    round_map = {record.round_index: record for record in round_records}
    round_count = total_rounds
    if round_map:
        round_count = max(round_count, max(round_map.keys()) + 1)
    ended_rounds = [bool(round_map.get(round_index) and round_map[round_index].ended) for round_index in range(round_count)]
    active_round = max((record.round_index for record in round_records if record.started), default=-1)
    return active_round, ended_rounds


def _get_scores_by_round(db, session_id: str, stage: str, round_sizes: list[int]):
    scores_by_round = [
        [{"teamA": "", "teamB": ""} for _ in range(court_count)]
        for court_count in round_sizes
    ]
    score_records = db.scalars(
        select(SessionScoreRecord)
        .where(SessionScoreRecord.session_id == session_id, SessionScoreRecord.stage == stage)
        .order_by(SessionScoreRecord.round_index.asc(), SessionScoreRecord.court_index.asc())
    ).all()
    for record in score_records:
        while len(scores_by_round) <= record.round_index:
            scores_by_round.append([])
        while len(scores_by_round[record.round_index]) <= record.court_index:
            scores_by_round[record.round_index].append({"teamA": "", "teamB": ""})
        scores_by_round[record.round_index][record.court_index] = {
            "teamA": "" if record.team_a_score is None else record.team_a_score,
            "teamB": "" if record.team_b_score is None else record.team_b_score,
        }
    return scores_by_round


def _is_score_complete(score: dict | None) -> bool:
    if not score:
        return False
    return score.get("teamA", "") != "" and score.get("teamB", "") != ""


def _get_match_winner(score: dict | None, court: dict) -> list[str] | None:
    if not _is_score_complete(score):
        return None
    if score["teamA"] == score["teamB"]:
        return None
    return court["team_a"] if score["teamA"] > score["teamB"] else court["team_b"]


def _rank_stats_entries(entries):
    return sorted(
        entries,
        key=lambda item: (
            -item[1]["points"],
            -item[1]["point_difference"],
            -item[1]["wins"],
            item[0],
        ),
    )


def _build_pair_standings(rounds: list[dict], scores_by_round: list[list[dict]]):
    standings = {}
    for round_index, round_data in enumerate(rounds):
        for court_index, court in enumerate(round_data.get("courts", [])):
            score = scores_by_round[round_index][court_index] if round_index < len(scores_by_round) else None
            if not _is_score_complete(score):
                continue

            team_a_key = " & ".join(court["team_a"])
            team_b_key = " & ".join(court["team_b"])
            standings.setdefault(team_a_key, {"points": 0, "wins": 0, "losses": 0, "point_difference": 0, "played": 0})
            standings.setdefault(team_b_key, {"points": 0, "wins": 0, "losses": 0, "point_difference": 0, "played": 0})

            point_delta = score["teamA"] - score["teamB"]
            standings[team_a_key]["played"] += 1
            standings[team_b_key]["played"] += 1
            standings[team_a_key]["point_difference"] += point_delta
            standings[team_b_key]["point_difference"] -= point_delta

            if score["teamA"] == score["teamB"]:
                continue
            if score["teamA"] > score["teamB"]:
                standings[team_a_key]["points"] += 2
                standings[team_a_key]["wins"] += 1
                standings[team_b_key]["losses"] += 1
            else:
                standings[team_b_key]["points"] += 2
                standings[team_b_key]["wins"] += 1
                standings[team_a_key]["losses"] += 1

    return _rank_stats_entries(standings.items())


def _create_knockout_round(label: str, round_number: int, matches: list[list[list[str]]]):
    return {
        "id": label.lower().replace(" ", "-"),
        "label": label,
        "round": round_number,
        "courts": [{"team_a": team_a, "team_b": team_b} for team_a, team_b in matches],
        "resting": [],
    }


def _build_knockout_rounds_for_stats(
    draw_config: dict,
    roster_rounds: list[dict],
    league_scores_by_round: list[list[dict]],
    knockout_scores_by_round: list[list[dict]],
    ended_league_rounds: list[bool],
    ended_knockout_rounds: list[bool],
):
    if draw_config.get("draw_type") != "league_knockout":
        return []
    if roster_rounds and not all(ended_league_rounds[:len(roster_rounds)]):
        return []

    pair_standings = _build_pair_standings(roster_rounds, league_scores_by_round)
    qualifier_count = min(draw_config.get("knockout_qualifiers", 4), len(pair_standings))
    if qualifier_count < 2:
        return []

    seeds = [pair_name.split(" & ") for pair_name, _ in pair_standings[:qualifier_count]]
    base_round = len(roster_rounds)

    if qualifier_count == 2:
        return [_create_knockout_round("Final", base_round + 1, [[seeds[0], seeds[1]]])]

    semifinal_round = _create_knockout_round(
        "Semifinals",
        base_round + 1,
        [[seeds[0], seeds[3]], [seeds[1], seeds[2]]],
    )
    rounds = [semifinal_round]
    semifinal_scores = knockout_scores_by_round[0] if knockout_scores_by_round else []
    semifinal_winners = []

    for court_index, court in enumerate(semifinal_round["courts"]):
        winner = None
        if ended_knockout_rounds[:1] and ended_knockout_rounds[0]:
            winner = _get_match_winner(
                semifinal_scores[court_index] if court_index < len(semifinal_scores) else None,
                court,
            )
        semifinal_winners.append(winner)

    if semifinal_winners and all(semifinal_winners):
        rounds.append(_create_knockout_round("Final", base_round + 2, [[semifinal_winners[0], semifinal_winners[1]]]))

    return rounds


def _iter_completed_matches(payload: dict, db, session_id: str):
    roster_rounds = payload.get("roster", {}).get("rounds", [])
    league_round_sizes = [len(round_data.get("courts", [])) for round_data in roster_rounds]
    _, ended_league_rounds = _get_round_state(db, session_id, "league", len(roster_rounds))
    league_scores = _get_scores_by_round(db, session_id, "league", league_round_sizes)

    for round_index, round_data in enumerate(roster_rounds):
        if round_index >= len(ended_league_rounds) or not ended_league_rounds[round_index]:
            continue
        for court_index, court in enumerate(round_data.get("courts", [])):
            score = league_scores[round_index][court_index] if round_index < len(league_scores) else None
            if _is_score_complete(score):
                yield {
                    "stage": "league",
                    "round_index": round_index,
                    "court": court,
                    "score": score,
                }

    active_knockout_round, ended_knockout_rounds = _get_round_state(db, session_id, "knockout", 0)
    knockout_round_total = max(len(ended_knockout_rounds), active_knockout_round + 1)
    if knockout_round_total <= 0:
        return

    knockout_scores = _get_scores_by_round(db, session_id, "knockout", [0 for _ in range(knockout_round_total)])
    knockout_rounds = _build_knockout_rounds_for_stats(
        payload.get("draw_config", {}),
        roster_rounds,
        league_scores,
        knockout_scores,
        ended_league_rounds,
        ended_knockout_rounds,
    )

    for round_index, round_data in enumerate(knockout_rounds):
        if round_index >= len(ended_knockout_rounds) or not ended_knockout_rounds[round_index]:
            continue
        for court_index, court in enumerate(round_data.get("courts", [])):
            score = knockout_scores[round_index][court_index] if round_index < len(knockout_scores) and court_index < len(knockout_scores[round_index]) else None
            if _is_score_complete(score):
                yield {
                    "stage": "knockout",
                    "round_index": round_index,
                    "court": court,
                    "score": score,
                }


def _get_session_completion_state(db, record: SharedSessionRecord, payload: dict):
    draw_config = payload.get("draw_config", {})
    league_total = len(payload.get("roster", {}).get("rounds", []))
    knockout_total = _planned_knockout_rounds(draw_config, _count_league_pairs(payload))
    total_rounds = league_total + knockout_total
    _, ended_league_rounds = _get_round_state(db, record.session_id, "league", league_total)
    _, ended_knockout_rounds = _get_round_state(db, record.session_id, "knockout", knockout_total)
    ended_rounds = sum(1 for ended in ended_league_rounds if ended) + sum(1 for ended in ended_knockout_rounds if ended)
    return {
        "completed": total_rounds > 0 and ended_rounds >= total_rounds,
        "total_rounds": total_rounds,
        "ended_rounds": ended_rounds,
    }


def _delete_session_analytics(db, session_id: str):
    summary = db.get(CompletedSessionStatsRecord, session_id)
    if summary:
        db.delete(summary)

    for row in db.scalars(
        select(PlayerSessionStatsRecord).where(PlayerSessionStatsRecord.session_id == session_id)
    ).all():
        db.delete(row)

    for row in db.scalars(
        select(PlayerPartnerSessionStatsRecord).where(PlayerPartnerSessionStatsRecord.session_id == session_id)
    ).all():
        db.delete(row)


def _delete_completed_session_history(db, session_id: str):
    summary = db.get(CompletedSessionStatsRecord, session_id)
    if summary:
        db.delete(summary)


def _rebuild_player_stats_summary(db):
    session_rows = db.scalars(
        select(PlayerSessionStatsRecord).order_by(PlayerSessionStatsRecord.completed_at.desc())
    ).all()
    partner_rows = db.scalars(select(PlayerPartnerSessionStatsRecord)).all()

    partner_totals = defaultdict(lambda: {"wins": 0, "matches": 0})
    for row in partner_rows:
        key = (row.player_name, row.partner_name)
        partner_totals[key]["wins"] += row.wins
        partner_totals[key]["matches"] += row.matches_played

    aggregates = {}
    for row in session_rows:
        aggregate = aggregates.setdefault(
            row.player_name,
            {
                "sessions_played": 0,
                "matches_played": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "points": 0,
                "point_difference": 0,
                "league_matches_played": 0,
                "league_wins": 0,
                "league_losses": 0,
                "league_draws": 0,
                "league_points": 0,
                "league_point_difference": 0,
                "knockout_matches_played": 0,
                "knockout_wins": 0,
                "knockout_losses": 0,
                "knockout_draws": 0,
                "knockout_points": 0,
                "knockout_point_difference": 0,
                "championships": 0,
                "last_session_at": None,
            },
        )
        aggregate["sessions_played"] += 1
        for key in aggregate.keys():
            if key in {"sessions_played", "last_session_at"}:
                continue
            if hasattr(row, key):
                aggregate[key] += getattr(row, key)
        if aggregate["last_session_at"] is None or row.completed_at > aggregate["last_session_at"]:
            aggregate["last_session_at"] = row.completed_at

    player_names = list(aggregates.keys())
    if player_names:
        db.execute(
            delete(PlayerStatsSummaryRecord).where(
                PlayerStatsSummaryRecord.player_name.not_in(player_names)
            )
        )
    else:
        db.execute(delete(PlayerStatsSummaryRecord))
        db.flush()
        return

    summary_rows = []
    for player_name, values in aggregates.items():
        summary_rows.append(
            {
                "player_name": player_name,
                "sessions_played": values["sessions_played"],
                "matches_played": values["matches_played"],
                "wins": values["wins"],
                "losses": values["losses"],
                "draws": values["draws"],
                "points": values["points"],
                "point_difference": values["point_difference"],
                "league_matches_played": values["league_matches_played"],
                "league_wins": values["league_wins"],
                "league_losses": values["league_losses"],
                "league_draws": values["league_draws"],
                "league_points": values["league_points"],
                "league_point_difference": values["league_point_difference"],
                "knockout_matches_played": values["knockout_matches_played"],
                "knockout_wins": values["knockout_wins"],
                "knockout_losses": values["knockout_losses"],
                "knockout_draws": values["knockout_draws"],
                "knockout_points": values["knockout_points"],
                "knockout_point_difference": values["knockout_point_difference"],
                "championships": values["championships"],
                "best_partner": None,
                "best_partner_wins": 0,
                "best_partner_matches": 0,
                "last_session_at": values["last_session_at"],
            }
        )

    dialect_name = db.bind.dialect.name if db.bind else ""
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        dialect_insert = None

    if dialect_insert is None:
        db.execute(delete(PlayerStatsSummaryRecord))
        db.flush()
        for row in summary_rows:
            db.add(PlayerStatsSummaryRecord(**row))
        return

    insert_stmt = dialect_insert(PlayerStatsSummaryRecord).values(summary_rows)
    update_columns = {
        column.name: insert_stmt.excluded[column.name]
        for column in PlayerStatsSummaryRecord.__table__.columns
        if column.name != "player_name"
    }
    db.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[PlayerStatsSummaryRecord.player_name],
            set_=update_columns,
        )
    )


def _sync_completed_session_stats(db, record: SharedSessionRecord, payload: dict):
    completion_state = _get_session_completion_state(db, record, payload)
    existing_summary = db.get(CompletedSessionStatsRecord, record.session_id)

    if not completion_state["completed"]:
        if existing_summary:
            _delete_session_analytics(db, record.session_id)
            # The session factory runs with autoflush=False; flush the pending
            # deletes so the summary rebuild below aggregates post-delete state
            # instead of re-counting the rows it is about to remove.
            db.flush()
            _rebuild_player_stats_summary(db)
        return

    if existing_summary and existing_summary.processed_version == record.version:
        return

    _delete_session_analytics(db, record.session_id)
    player_totals = {}
    partner_totals = {}
    session_matches = list(_iter_completed_matches(payload, db, record.session_id))

    for match in session_matches:
        stage = match["stage"]
        court = match["court"]
        score = match["score"]
        point_delta = score["teamA"] - score["teamB"]
        stage_prefix = "league" if stage == "league" else "knockout"

        for player in court["team_a"] + court["team_b"]:
            player_totals.setdefault(
                player,
                {
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "points": 0,
                    "point_difference": 0,
                    "league_matches_played": 0,
                    "league_wins": 0,
                    "league_losses": 0,
                    "league_draws": 0,
                    "league_points": 0,
                    "league_point_difference": 0,
                    "knockout_matches_played": 0,
                    "knockout_wins": 0,
                    "knockout_losses": 0,
                    "knockout_draws": 0,
                    "knockout_points": 0,
                    "knockout_point_difference": 0,
                    "championships": 0,
                },
            )

        for player in court["team_a"]:
            player_totals[player]["matches_played"] += 1
            player_totals[player][f"{stage_prefix}_matches_played"] += 1
            player_totals[player]["point_difference"] += point_delta
            player_totals[player][f"{stage_prefix}_point_difference"] += point_delta
        for player in court["team_b"]:
            player_totals[player]["matches_played"] += 1
            player_totals[player][f"{stage_prefix}_matches_played"] += 1
            player_totals[player]["point_difference"] -= point_delta
            player_totals[player][f"{stage_prefix}_point_difference"] -= point_delta

        for team in (court["team_a"], court["team_b"]):
            if len(team) == 2:
                for player, partner, delta_sign in (
                    (team[0], team[1], 1 if team is court["team_a"] else -1),
                    (team[1], team[0], 1 if team is court["team_a"] else -1),
                ):
                    partner_totals.setdefault(
                        (player, partner),
                        {"matches_played": 0, "wins": 0, "losses": 0, "draws": 0, "points": 0, "point_difference": 0},
                    )
                    partner_totals[(player, partner)]["matches_played"] += 1
                    partner_totals[(player, partner)]["point_difference"] += point_delta * delta_sign

        winner = _get_match_winner(score, court)
        if not winner:
            for player in court["team_a"] + court["team_b"]:
                player_totals[player]["draws"] += 1
                player_totals[player][f"{stage_prefix}_draws"] += 1
            for team in (court["team_a"], court["team_b"]):
                if len(team) == 2:
                    for player, partner in ((team[0], team[1]), (team[1], team[0])):
                        partner_totals[(player, partner)]["draws"] += 1
            continue

        losers = court["team_b"] if winner == court["team_a"] else court["team_a"]
        for player in winner:
            player_totals[player]["wins"] += 1
            player_totals[player]["points"] += 2
            player_totals[player][f"{stage_prefix}_wins"] += 1
            player_totals[player][f"{stage_prefix}_points"] += 2
        for player in losers:
            player_totals[player]["losses"] += 1
            player_totals[player][f"{stage_prefix}_losses"] += 1

        if len(winner) == 2:
            for player, partner in ((winner[0], winner[1]), (winner[1], winner[0])):
                partner_totals[(player, partner)]["wins"] += 1
                partner_totals[(player, partner)]["points"] += 2
        if len(losers) == 2:
            for player, partner in ((losers[0], losers[1]), (losers[1], losers[0])):
                partner_totals[(player, partner)]["losses"] += 1

    league_rounds = payload.get("roster", {}).get("rounds", [])
    league_scores = _get_scores_by_round(db, record.session_id, "league", [len(round_data.get("courts", [])) for round_data in league_rounds])
    top_player = None
    if player_totals:
        ranked_players = _rank_stats_entries(
            ((player, totals) for player, totals in player_totals.items())
        )
        top_player = ranked_players[0][0]

    champion_pair = None
    knockout_matches = [match for match in session_matches if match["stage"] == "knockout"]
    if knockout_matches:
        final_match = knockout_matches[-1]
        champion = _get_match_winner(final_match["score"], final_match["court"])
        champion_pair = " & ".join(champion) if champion else None
        if champion:
            for player in champion:
                player_totals[player]["championships"] += 1

    if not champion_pair:
        pair_standings = _build_pair_standings(league_rounds, league_scores)
        champion_pair = pair_standings[0][0] if pair_standings else None

    completed_at = record.updated_at
    draw_type = payload.get("draw_config", {}).get("draw_type", "round_robin")

    db.add(
        CompletedSessionStatsRecord(
            session_id=record.session_id,
            session_name=record.name,
            draw_type=draw_type,
            total_players=len(player_totals),
            total_matches=len(session_matches),
            champion_pair=champion_pair,
            top_player=top_player,
            processed_version=record.version,
            completed_at=completed_at,
        )
    )

    for player_name, totals in player_totals.items():
        db.add(
            PlayerSessionStatsRecord(
                session_id=record.session_id,
                player_name=player_name,
                session_name=record.name,
                draw_type=draw_type,
                completed_at=completed_at,
                **totals,
            )
        )

    for (player_name, partner_name), totals in partner_totals.items():
        db.add(
            PlayerPartnerSessionStatsRecord(
                session_id=record.session_id,
                player_name=player_name,
                partner_name=partner_name,
                **totals,
            )
        )

    db.flush()
    _rebuild_player_stats_summary(db)


def _ensure_completed_session_stats(db):
    records = db.scalars(select(SharedSessionRecord).order_by(SharedSessionRecord.updated_at.desc())).all()
    changed = False
    for record in records:
        payload = _upgrade_session_payload(deepcopy(record.data))
        payload = _hydrate_legacy_session_storage(db, record, payload)
        summary = db.get(CompletedSessionStatsRecord, record.session_id)
        completion_state = _get_session_completion_state(db, record, payload)
        needs_sync = (
            completion_state["completed"] and (not summary or summary.processed_version != record.version)
        ) or (not completion_state["completed"] and summary is not None)
        if needs_sync:
            _sync_completed_session_stats(db, record, payload)
            changed = True
    has_summary_rows = db.scalar(select(PlayerStatsSummaryRecord.player_name).limit(1))
    has_session_rows = db.scalar(select(PlayerSessionStatsRecord.player_name).limit(1))
    stale_summary = db.scalar(
        select(PlayerStatsSummaryRecord.player_name).where(PlayerStatsSummaryRecord.sessions_played == 0).limit(1)
    )
    if (not has_summary_rows and has_session_rows) or (stale_summary and has_session_rows):
        _rebuild_player_stats_summary(db)
        changed = True
    if changed:
        db.flush()


def _to_completed_session_stats_response(row: CompletedSessionStatsRecord) -> CompletedSessionStatsResponse:
    return CompletedSessionStatsResponse(
        session_id=row.session_id,
        session_name=row.session_name,
        draw_type=row.draw_type,
        completed_at=row.completed_at.isoformat(),
        total_players=row.total_players,
        total_matches=row.total_matches,
        champion_pair=row.champion_pair,
        top_player=row.top_player,
    )


def _to_player_stats_summary_response(db, row: PlayerStatsSummaryRecord) -> PlayerStatsSummaryResponse:
    win_rate = round((row.wins / row.matches_played) * 100, 1) if row.matches_played else 0.0
    player = _find_player_by_name(db, row.player_name)
    return PlayerStatsSummaryResponse(
        player_id=player.player_id if player else None,
        full_name=player.full_name if player else row.player_name,
        short_name=player.short_name if player else row.player_name,
        player_name=row.player_name,
        sessions_played=row.sessions_played,
        matches_played=row.matches_played,
        wins=row.wins,
        losses=row.losses,
        draws=row.draws,
        points=row.points,
        point_difference=row.point_difference,
        league_matches_played=row.league_matches_played,
        league_wins=row.league_wins,
        league_losses=row.league_losses,
        league_draws=row.league_draws,
        league_points=row.league_points,
        league_point_difference=row.league_point_difference,
        knockout_matches_played=row.knockout_matches_played,
        knockout_wins=row.knockout_wins,
        knockout_losses=row.knockout_losses,
        knockout_draws=row.knockout_draws,
        knockout_points=row.knockout_points,
        knockout_point_difference=row.knockout_point_difference,
        championships=row.championships,
        win_rate=win_rate,
        last_session_at=row.last_session_at.isoformat() if row.last_session_at else None,
    )


def _serialize_session(record: SharedSessionRecord, edit_token: str | None = None, db=None) -> SharedSessionResponse:
    should_close_db = db is None
    db_session = db
    if should_close_db:
        db_context = get_db_session()
        db_session = db_context.__enter__()

    try:
        payload = _upgrade_session_payload(deepcopy(record.data))
        payload = _hydrate_legacy_session_storage(db_session, record, payload)
        roster_rounds = payload.get("roster", {}).get("rounds", [])
        league_round_sizes = [len(round_data.get("courts", [])) for round_data in roster_rounds]
        active_league_round, ended_league_rounds = _get_round_state(
            db_session, record.session_id, "league", len(roster_rounds)
        )
        active_knockout_round, ended_knockout_rounds = _get_round_state(
            db_session, record.session_id, "knockout", 0
        )
        knockout_round_total = max(
            len(ended_knockout_rounds),
            active_knockout_round + 1,
        )
        if knockout_round_total > len(ended_knockout_rounds):
            ended_knockout_rounds.extend([False] * (knockout_round_total - len(ended_knockout_rounds)))
        league_scores_by_round = _get_scores_by_round(
            db_session, record.session_id, "league", league_round_sizes
        )
        knockout_scores_by_round = _get_scores_by_round(
            db_session, record.session_id, "knockout", [0 for _ in range(knockout_round_total)]
        )

        can_undo = len(payload.get("undo_stack", [])) > 0
        response_payload = {
            key: value
            for key, value in payload.items()
            if key in {"name", "roster", "draw_config"}
        }
        can_edit = _is_valid_edit_token(payload, edit_token)
        return SharedSessionResponse(
            session_id=record.session_id,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            can_edit=can_edit,
            edit_token=edit_token if can_edit else None,
            can_undo=can_undo,
            version=record.version,
            league_scores_by_round=league_scores_by_round,
            active_league_round=active_league_round,
            ended_league_rounds=ended_league_rounds,
            knockout_scores_by_round=knockout_scores_by_round,
            active_knockout_round=active_knockout_round,
            ended_knockout_rounds=ended_knockout_rounds,
            **response_payload,
        )
    finally:
        if should_close_db:
            db_context.__exit__(None, None, None)


def _count_league_pairs(payload: dict) -> int:
    pairs = set()
    for round_data in payload.get("roster", {}).get("rounds", []):
        for court in round_data.get("courts", []):
            pairs.add(" & ".join(court.get("team_a", [])))
            pairs.add(" & ".join(court.get("team_b", [])))
    return len([pair for pair in pairs if pair])


def _planned_knockout_rounds(draw_config: dict, pair_count: int) -> int:
    if draw_config.get("draw_type") != "league_knockout":
        return 0
    qualifiers = min(draw_config.get("knockout_qualifiers", 4), pair_count)
    if qualifiers >= 4:
        return 2
    if qualifiers >= 2:
        return 1
    return 0


def _serialize_session_summary(record: SharedSessionRecord, db=None) -> SharedSessionSummary:
    should_close_db = db is None
    db_session = db
    if should_close_db:
        db_context = get_db_session()
        db_session = db_context.__enter__()

    try:
        payload = _upgrade_session_payload(deepcopy(record.data))
        payload = _hydrate_legacy_session_storage(db_session, record, payload)
        draw_config = payload.get("draw_config", {})
        league_total = len(payload.get("roster", {}).get("rounds", []))
        knockout_total = _planned_knockout_rounds(draw_config, _count_league_pairs(payload))
        total_rounds = league_total + knockout_total
        active_league_round, ended_league_rounds = _get_round_state(db_session, record.session_id, "league", league_total)
        active_knockout_round, ended_knockout_rounds = _get_round_state(db_session, record.session_id, "knockout", knockout_total)
        ended_rounds = sum(1 for ended in ended_league_rounds if ended) + sum(1 for ended in ended_knockout_rounds if ended)
        live_rounds = max(0, active_league_round + 1 - sum(ended_league_rounds))
        live_rounds += max(0, active_knockout_round + 1 - sum(ended_knockout_rounds))

        if ended_rounds >= total_rounds and total_rounds > 0:
            status = "completed"
        elif active_league_round >= 0 or active_knockout_round >= 0:
            status = "in_progress"
        else:
            status = "ready"

        return SharedSessionSummary(
            session_id=record.session_id,
            name=record.name,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            draw_type=draw_config.get("draw_type", "round_robin"),
            status=status,
            ended_rounds=ended_rounds,
            total_rounds=total_rounds,
            live_rounds=live_rounds,
        )
    finally:
        if should_close_db:
            db_context.__exit__(None, None, None)


def _generate_session_id() -> str:
    return secrets.token_urlsafe(6)


def _get_session_record(session_id: str) -> SharedSessionRecord:
    with get_db_session() as db:
        record = db.scalar(
            select(SharedSessionRecord).where(SharedSessionRecord.session_id == session_id)
        )
        if not record:
            raise HTTPException(status_code=404, detail="Shared session not found")
        _hydrate_legacy_session_storage(db, record, _upgrade_session_payload(deepcopy(record.data)))
        db.expunge(record)
        return record


def _is_valid_edit_token(payload: dict, edit_token: str | None) -> bool:
    if edit_token is None:
        return False

    return edit_token == payload.get("edit_token") or edit_token == ADMIN_RECOVERY_TOKEN


def _require_edit_access(payload: dict, edit_token: str | None):
    if not _is_valid_edit_token(payload, edit_token):
        raise HTTPException(status_code=403, detail="Scorer access required")


def _get_or_create_round_record(db, session_id: str, stage: str, round_index: int) -> SessionRoundRecord:
    record = db.get(SessionRoundRecord, (session_id, stage, round_index))
    if record:
        return record

    record = SessionRoundRecord(
        session_id=session_id,
        stage=stage,
        round_index=round_index,
        started=False,
        ended=False,
    )
    db.add(record)
    db.flush()
    return record


def _get_stage_progress(db, session_id: str, stage: str):
    round_records = db.scalars(
        select(SessionRoundRecord)
        .where(SessionRoundRecord.session_id == session_id, SessionRoundRecord.stage == stage)
        .order_by(SessionRoundRecord.round_index.asc())
    ).all()
    active_round = max((record.round_index for record in round_records if record.started), default=-1)
    return round_records, active_round


def _get_score_record(db, session_id: str, stage: str, round_index: int, court_index: int) -> SessionScoreRecord | None:
    return db.get(SessionScoreRecord, (session_id, stage, round_index, court_index))


def _validate_score_target(db, session_id: str, payload: dict, stage: str, round_index: int, court_index: int):
    if stage not in {"league", "knockout"}:
        raise HTTPException(status_code=400, detail="Invalid stage")

    if stage == "league":
        rounds = payload.get("roster", {}).get("rounds", [])
        if round_index < 0 or round_index >= len(rounds):
            raise HTTPException(status_code=400, detail="Invalid round or court index")
        court_count = len(rounds[round_index].get("courts", []))
        if court_index < 0 or court_index >= court_count:
            raise HTTPException(status_code=400, detail="Invalid round or court index")

    round_record = db.get(SessionRoundRecord, (session_id, stage, round_index))
    if round_record and round_record.ended:
        raise HTTPException(status_code=409, detail="Round is locked after being ended")
    if not round_record or not round_record.started:
        raise HTTPException(status_code=409, detail="Round must be started before scores can be entered")


def _apply_score_update(db, session_id: str, payload: dict, req: ScoreUpdateRequest):
    if req.team_key not in {"teamA", "teamB"}:
        raise HTTPException(status_code=400, detail="Invalid team key")

    _validate_score_target(db, session_id, payload, req.stage, req.round_index, req.court_index)

    next_value = "" if req.value is None else req.value
    score_record = _get_score_record(db, session_id, req.stage, req.round_index, req.court_index)
    current_value = ""
    if score_record:
        current_value = score_record.team_a_score if req.team_key == "teamA" else score_record.team_b_score
        current_value = "" if current_value is None else current_value

    if current_value == next_value:
        return False

    if not score_record:
        score_record = SessionScoreRecord(
            session_id=session_id,
            stage=req.stage,
            round_index=req.round_index,
            court_index=req.court_index,
            team_a_score=None,
            team_b_score=None,
        )
        # Flush immediately so a later update in the same batch (which looks
        # the row up by primary key) finds this row instead of inserting a
        # duplicate and failing the whole batch with a UNIQUE violation.
        db.add(score_record)
        db.flush()

    if req.team_key == "teamA":
        score_record.team_a_score = None if next_value == "" else int(next_value)
    else:
        score_record.team_b_score = None if next_value == "" else int(next_value)
    db.add(score_record)
    return True


def _update_session_record(session_id: str, updater, edit_token: str | None = None, response_builder=None):
    for attempt in range(3):
        try:
            with get_db_session() as db:
                record = db.scalar(
                    select(SharedSessionRecord)
                    .where(SharedSessionRecord.session_id == session_id)
                    .with_for_update()
                )
                if not record:
                    raise HTTPException(status_code=404, detail="Shared session not found")

                next_payload = _upgrade_session_payload(deepcopy(record.data))
                next_payload = _hydrate_legacy_session_storage(db, record, next_payload)
                _require_edit_access(next_payload, edit_token)
                changed = updater(db, record, next_payload)
                if changed is False:
                    return (
                        response_builder(record, db)
                        if response_builder
                        else _serialize_session(record, edit_token=edit_token, db=db)
                    )

                record.data = next_payload
                record.version += 1
                db.add(record)
                db.flush()
                db.refresh(record)
                _sync_completed_session_stats(db, record, next_payload)
                response = (
                    response_builder(record, db)
                    if response_builder
                    else _serialize_session(record, edit_token=edit_token, db=db)
                )
                _invalidate_session_views(session_id)
                return response
        except OperationalError as exc:
            message = str(exc).lower()
            if "statement timeout" not in message or attempt == 2:
                raise
            time.sleep(0.2 * (attempt + 1))


def _capture_undo_snapshot(payload: dict):
    payload["undo_stack"] = []


def _restore_undo_snapshot(payload: dict, snapshot: dict):
    payload["undo_stack"] = []


def _build_roster_response_from_rounds(
    rounds: list[dict],
    players: list[str],
    court_numbers: list[str],
    fixed_pairs: list[tuple[str, str]],
    draw_type: str,
    limits: dict[str, int],
    pair_games: int,
    pair_start_round: int,
    max_consecutive_rest: int,
    warnings: list[str] | None = None,
):
    fixed_pair_counts = {pair: 0 for pair in fixed_pairs}
    rest_counts: dict[str, int] = {player: 0 for player in players}

    for round_data in rounds:
        for player in round_data.get("resting", []):
            rest_counts[player] += 1

        for court in round_data.get("courts", []):
            for team in (court[0], court[1]):
                if len(team) != 2:
                    continue
                pair_key = tuple(sorted(team))
                if pair_key in fixed_pair_counts:
                    fixed_pair_counts[pair_key] += 1

    violations = _collect_roster_violations(
        rounds,
        limits,
        max_consecutive_rest,
        fixed_pairs,
        fixed_pair_counts,
        pair_games,
        pair_start_round,
        draw_type,
    )

    round_results = []
    for round_data in rounds:
        round_results.append(
            RoundResult(
                round=round_data["round"],
                courts=[
                    CourtResult(team_a=list(team_a), team_b=list(team_b))
                    for team_a, team_b in round_data.get("courts", [])
                ],
                resting=list(round_data.get("resting", [])),
            )
        )

    return RosterResponse(
        rounds=round_results,
        court_numbers=court_numbers,
        rest_counts=dict(sorted(rest_counts.items())),
        fixed_pair_counts={f"{a} & {b}": count for (a, b), count in fixed_pair_counts.items()},
        violations=violations,
        warnings=warnings or [],
    )


def _normalize_existing_roster(req: RosterRequest, roster: RosterResponse) -> RosterResponse:
    players = list(req.players)
    players_set = set(players)
    fixed_pairs = [tuple(sorted(pair)) for pair in req.fixed_pairs]

    court_numbers = req.court_numbers
    if not court_numbers or len(court_numbers) != req.num_courts:
        court_numbers = [str(i + 1) for i in range(req.num_courts)]

    num_playing = req.num_courts * 4
    num_resting = len(players) - num_playing
    if num_resting < 0:
        raise HTTPException(
            status_code=422,
            detail=f"Need at least {num_playing} players for {req.num_courts} court(s), but only {len(players)} provided.",
        )

    expected_rounds = req.rounds
    if len(roster.rounds) != expected_rounds:
        raise HTTPException(status_code=422, detail="Edited roster must contain the configured number of rounds")

    warnings: list[str] = []
    if num_resting == 0 and req.limits:
        warnings.append(
            "No rest slots available (players == courts*4). Consecutive game limits cannot be enforced."
        )

    normalized_rounds: list[dict] = []
    for expected_round_number, round_result in enumerate(roster.rounds, start=1):
        if round_result.round != expected_round_number:
            raise HTTPException(status_code=422, detail="Edited roster contains invalid round numbering")
        if len(round_result.courts) != req.num_courts:
            raise HTTPException(status_code=422, detail=f"Round {round_result.round} must contain exactly {req.num_courts} courts")
        if len(round_result.resting) != num_resting:
            raise HTTPException(status_code=422, detail=f"Round {round_result.round} must contain exactly {num_resting} resting players")

        seen_players: list[str] = []
        normalized_courts: list[tuple[tuple[str, str], tuple[str, str]]] = []
        for court_result in round_result.courts:
            if len(court_result.team_a) != 2 or len(court_result.team_b) != 2:
                raise HTTPException(status_code=422, detail=f"Round {round_result.round} courts must contain exactly 2 players per team")
            for player in court_result.team_a + court_result.team_b:
                if player not in players_set:
                    raise HTTPException(status_code=422, detail=f"Round {round_result.round} contains unknown player '{player}'")
                seen_players.append(player)
            normalized_courts.append(
                (
                    tuple(sorted(court_result.team_a)),
                    tuple(sorted(court_result.team_b)),
                )
            )

        for player in round_result.resting:
            if player not in players_set:
                raise HTTPException(status_code=422, detail=f"Round {round_result.round} contains unknown player '{player}'")
            seen_players.append(player)

        if len(seen_players) != len(players) or set(seen_players) != players_set:
            raise HTTPException(status_code=422, detail=f"Round {round_result.round} must include every selected player exactly once")
        if len(seen_players) != len(set(seen_players)):
            raise HTTPException(status_code=422, detail=f"Round {round_result.round} contains duplicate players")

        normalized_rounds.append(
            {
                "round": round_result.round,
                "courts": normalized_courts,
                "resting": sorted(round_result.resting),
            }
        )

    return _build_roster_response_from_rounds(
        normalized_rounds,
        players,
        court_numbers,
        fixed_pairs,
        req.draw_type,
        req.limits,
        req.pair_games,
        req.pair_start_round,
        req.max_consecutive_rest,
        warnings=warnings,
    )


@app.post("/api/generate", response_model=RosterResponse)
def api_generate(req: RosterRequest):
    request_fingerprint = hashlib.sha256(
        json.dumps(req.model_dump(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    def build_response():
        fixed_pairs = [tuple(sorted(p)) for p in req.fixed_pairs]

        court_numbers = req.court_numbers
        if not court_numbers or len(court_numbers) != req.num_courts:
            court_numbers = [str(i + 1) for i in range(req.num_courts)]

        try:
            if _has_fixed_pair_knockout_schedule(req.draw_type, fixed_pairs):
                rounds, rest_counts, fpc, warnings = generate_fixed_pair_knockout_roster(
                    players=req.players,
                    fixed_pairs=fixed_pairs,
                    num_courts=req.num_courts,
                    num_rounds=req.rounds,
                    pair_target=req.pair_games,
                )
            else:
                rounds, rest_counts, fpc, warnings = generate_roster(
                    players=req.players,
                    num_courts=req.num_courts,
                    num_rounds=req.rounds,
                    consecutive_limits=req.limits,
                    fixed_pairs=fixed_pairs,
                    pair_target=req.pair_games,
                    max_consecutive_rest=req.max_consecutive_rest,
                    pair_start_round=req.pair_start_round,
                    seed=req.seed,
                )
        except RosterError as e:
            raise HTTPException(status_code=422, detail=str(e))

        violations = _collect_roster_violations(
            rounds,
            req.limits,
            req.max_consecutive_rest,
            fixed_pairs,
            fpc,
            req.pair_games,
            req.pair_start_round,
            req.draw_type,
        )

        round_results = []
        for r in rounds:
            courts = [
                CourtResult(team_a=list(ta), team_b=list(tb))
                for ta, tb in r["courts"]
            ]
            round_results.append(RoundResult(
                round=r["round"], courts=courts, resting=r["resting"],
            ))

        fpc_str = {f"{a} & {b}": count for (a, b), count in fpc.items()}

        return RosterResponse(
            rounds=round_results,
            court_numbers=court_numbers,
            rest_counts=rest_counts,
            fixed_pair_counts=fpc_str,
            violations=violations,
            warnings=warnings,
        )

    if req.seed is None:
        # An unseeded request must produce a fresh roster every time; caching
        # by request fingerprint would return the identical roster for the
        # full generate TTL (an hour by default), silently breaking the
        # planner's "Regenerate Roster" action.
        return jsonable_encoder(build_response())

    return _cache_get_or_set(
        "roster",
        [request_fingerprint],
        _cache_ttl("CACHE_TTL_GENERATE", 3600),
        build_response,
    )


@app.post("/api/rosters/revalidate", response_model=RosterResponse)
def api_revalidate_roster(req: RosterRevalidateRequest):
    return _normalize_existing_roster(req, req.roster)


def _validation_error_detail(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = first.get("msg", "Invalid request")
    return f"{location}: {message}" if location else message


@app.post("/api/sessions", response_model=SharedSessionResponse)
def create_shared_session(req: SharedSessionCreateRequest):
    if req.admin_token != ADMIN_RECOVERY_TOKEN:
        raise HTTPException(status_code=403, detail="Organizer token required to start a session")

    inferred_players = [player.short_name for player in req.selected_players]
    if not inferred_players:
        seen_players = set()
        for round_data in req.roster.rounds:
            for court in round_data.courts:
                seen_players.update(court.team_a)
                seen_players.update(court.team_b)
            seen_players.update(round_data.resting)
        inferred_players = sorted(seen_players)

    if req.draw_config.draw_type == "league_knockout":
        pair_count = len(req.fixed_pairs) if req.fixed_pairs else max(len(inferred_players) // 2, 1)
        if req.draw_config.knockout_qualifiers > pair_count:
            raise HTTPException(
                status_code=422,
                detail="knockout_qualifiers cannot exceed the number of fixed pairs",
            )

    try:
        normalized_roster = _normalize_existing_roster(
            RosterRequest(
                players=inferred_players,
                fixed_pairs=req.fixed_pairs,
                num_courts=len(req.roster.court_numbers),
                court_numbers=req.roster.court_numbers,
                rounds=len(req.roster.rounds),
                limits=req.limits,
                pair_games=req.pair_games,
                pair_start_round=req.pair_start_round,
                max_consecutive_rest=req.max_consecutive_rest,
            ),
            req.roster,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_error_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = {
        "name": req.name or f"session-{secrets.token_hex(2)}",
        "edit_token": secrets.token_urlsafe(12),
        "roster": normalized_roster.model_dump(),
        "draw_config": req.draw_config.model_dump(),
        "player_directory": [player.model_dump() for player in req.selected_players],
        "fixed_pair_player_ids": req.fixed_pair_player_ids,
    }

    with get_db_session() as db:
        _ensure_player_registry(db)
        while True:
            session_id = _generate_session_id()
            existing = db.scalar(
                select(SharedSessionRecord).where(SharedSessionRecord.session_id == session_id)
            )
            if not existing:
                break

        record = SharedSessionRecord(
            session_id=session_id,
            name=payload["name"],
            data=payload,
            version=1,
        )
        db.add(record)
        db.flush()
        db.refresh(record)
        response = _serialize_session(record, edit_token=payload["edit_token"], db=db)
        _invalidate_session_views(session_id, include_analytics=False)
        _invalidate_player_views()
        return response


@app.get("/api/sessions/{session_id}", response_model=SharedSessionResponse)
def get_shared_session(session_id: str, edit_token: str | None = None):
    return _cache_get_or_set(
        f"session:{session_id}",
        [_cache_token_key(edit_token)],
        _cache_ttl("CACHE_TTL_SESSION_DETAIL", 15),
        lambda: _serialize_session(_get_session_record(session_id), edit_token=edit_token),
    )


@app.get("/api/sessions", response_model=list[SharedSessionSummary])
def list_shared_sessions():
    def build_response():
        with get_db_session() as db:
            records = db.scalars(
                select(SharedSessionRecord).order_by(SharedSessionRecord.updated_at.desc())
            ).all()
            return [_serialize_session_summary(record, db=db) for record in records]

    return _cache_get_or_set(
        "sessions",
        ["all"],
        _cache_ttl("CACHE_TTL_SESSIONS", 20),
        build_response,
    )


@app.get("/api/players", response_model=list[PlayerResponse])
def list_players():
    def build_response():
        with get_db_session() as db:
            _ensure_player_registry(db)
            rows = db.scalars(
                select(PlayerRecord)
                .where(PlayerRecord.is_deleted.is_(False))
                .order_by(PlayerRecord.full_name.asc())
            ).all()
            return [_serialize_player(row) for row in rows]

    return _cache_get_or_set(
        "players",
        ["all"],
        _cache_ttl("CACHE_TTL_PLAYERS", 300),
        build_response,
    )


@app.post("/api/players", response_model=PlayerResponse, status_code=201)
def create_player(req: PlayerCreateRequest):
    with get_db_session() as db:
        _ensure_player_registry(db)
        normalized_full_name = _normalize_player_name(req.full_name)
        normalized_short_name = _normalize_player_name(req.short_name)

        existing_full = _find_name_conflict(db, normalized_full_name)
        if existing_full:
            raise HTTPException(status_code=409, detail="A player with this full name already exists")

        existing_short = _find_name_conflict(db, normalized_short_name)
        if existing_short:
            raise HTTPException(status_code=409, detail="A player with this short name already exists")

        soft_deleted_player = _find_soft_deleted_player_for_restore(db, normalized_full_name, normalized_short_name)
        if soft_deleted_player:
            restore_short_conflict = _find_name_conflict(
                db,
                normalized_short_name,
                exclude_player_id=soft_deleted_player.player_id,
                include_deleted=True,
            )
            if restore_short_conflict:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A deleted player still holds this short name. Recreate that player "
                        "with the same full and short name to restore it, or pick another name."
                    ),
                )
            player = _restore_deleted_player(db, soft_deleted_player, req.full_name, req.short_name)
        else:
            deleted_full = _find_name_conflict(db, normalized_full_name, include_deleted=True)
            if deleted_full:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A deleted player still holds this full name. Recreate that player "
                        "with the same full and short name to restore it, or pick another name."
                    ),
                )

            deleted_short = _find_name_conflict(db, normalized_short_name, include_deleted=True)
            if deleted_short:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A deleted player still holds this short name. Recreate that player "
                        "with the same full and short name to restore it, or pick another name."
                    ),
                )

            player = _create_player_record(db, req.full_name, req.short_name, source="manual")
        response = _serialize_player(player)
        _invalidate_player_views()
        return response


@app.patch("/api/players/{player_id}", response_model=PlayerResponse)
def update_player(player_id: str, req: PlayerUpdateRequest):
    with get_db_session() as db:
        _ensure_player_registry(db)
        player = db.get(PlayerRecord, player_id)
        if not player or player.is_deleted:
            raise HTTPException(status_code=404, detail="Player not found")

        normalized_full_name = _normalize_player_name(req.full_name)
        normalized_short_name = _normalize_player_name(req.short_name)

        existing_full = _find_name_conflict(
            db, normalized_full_name, exclude_player_id=player_id, include_deleted=True
        )
        if existing_full:
            if existing_full.is_deleted:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A deleted player still holds this full name. Recreate that player "
                        "with the same full and short name to restore it, or pick another name."
                    ),
                )
            raise HTTPException(status_code=409, detail="A player with this full name already exists")

        existing_short = _find_name_conflict(
            db, normalized_short_name, exclude_player_id=player_id, include_deleted=True
        )
        if existing_short:
            if existing_short.is_deleted:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A deleted player still holds this short name. Recreate that player "
                        "with the same full and short name to restore it, or pick another name."
                    ),
                )
            raise HTTPException(status_code=409, detail="A player with this short name already exists")

        alias_pool = []
        for value in (player.full_name, player.short_name, *(player.aliases or [])):
            cleaned = " ".join(str(value).strip().split())
            normalized_value = _normalize_player_name(cleaned)
            if not cleaned or normalized_value in {normalized_full_name, normalized_short_name}:
                continue
            alias_pool.append(cleaned)

        player.full_name = req.full_name
        player.short_name = req.short_name
        player.normalized_full_name = normalized_full_name
        player.normalized_short_name = normalized_short_name
        player.aliases = list(dict.fromkeys(alias_pool))
        db.add(player)
        db.flush()
        db.refresh(player)
        response = _serialize_player(player)
        _invalidate_player_views()
        return response


@app.post("/api/players/{player_id}/delete", status_code=204)
def delete_player(player_id: str, req: PlayerDeleteRequest):
    with get_db_session() as db:
        _ensure_player_registry(db)
        player = db.get(PlayerRecord, player_id)
        if not player or player.is_deleted:
            raise HTTPException(status_code=404, detail="Player not found")
        if req.admin_token != ADMIN_RECOVERY_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid admin token")

        if req.delete_history:
            _delete_player_history(db, player)

        player.is_deleted = True
        player.deleted_at = datetime.now(timezone.utc)
        db.add(player)
        _invalidate_player_views()

    return Response(status_code=204)


@app.get("/api/history/sessions", response_model=list[CompletedSessionStatsResponse])
def list_completed_sessions():
    def build_response():
        with get_db_session() as db:
            _ensure_player_registry(db)
            _ensure_completed_session_stats(db)
            rows = db.scalars(
                select(CompletedSessionStatsRecord).order_by(CompletedSessionStatsRecord.completed_at.desc())
            ).all()
            return [_to_completed_session_stats_response(row) for row in rows]

    return _cache_get_or_set(
        "history",
        ["completed"],
        _cache_ttl("CACHE_TTL_HISTORY", 60),
        build_response,
    )


@app.get("/api/stats/players", response_model=list[PlayerStatsSummaryResponse])
def list_player_stats():
    def build_response():
        with get_db_session() as db:
            _ensure_player_registry(db)
            _ensure_completed_session_stats(db)
            rows = db.scalars(
                select(PlayerStatsSummaryRecord).order_by(
                    PlayerStatsSummaryRecord.championships.desc(),
                    PlayerStatsSummaryRecord.points.desc(),
                    PlayerStatsSummaryRecord.point_difference.desc(),
                    PlayerStatsSummaryRecord.wins.desc(),
                    PlayerStatsSummaryRecord.player_name.asc(),
                )
            ).all()
            return [_to_player_stats_summary_response(db, row) for row in rows]

    return _cache_get_or_set(
        "player-stats",
        ["summary"],
        _cache_ttl("CACHE_TTL_PLAYER_STATS", 60),
        build_response,
    )


@app.get("/api/stats/players/{player_name}", response_model=PlayerStatsDetailResponse)
def get_player_stats(player_name: str):
    def build_response():
        with get_db_session() as db:
            _ensure_player_registry(db)
            _ensure_completed_session_stats(db)
            row = db.get(PlayerStatsSummaryRecord, player_name)
            if not row:
                raise HTTPException(status_code=404, detail="Player stats not found")

            partner_rows = db.scalars(
                select(PlayerPartnerSessionStatsRecord)
                .where(PlayerPartnerSessionStatsRecord.player_name == player_name)
            ).all()

            partner_totals = defaultdict(lambda: {"wins": 0, "matches": 0})
            for partner_row in partner_rows:
                partner_totals[partner_row.partner_name]["wins"] += partner_row.wins
                partner_totals[partner_row.partner_name]["matches"] += partner_row.matches_played

            ranked_partners = [
                (
                    lambda partner: {
                        "partner_id": partner.player_id if partner else None,
                        "full_name": partner.full_name if partner else partner_name,
                        "short_name": partner.short_name if partner else partner_name,
                        "partner_name": partner_name,
                        "matches_played": totals["matches"],
                        "wins": totals["wins"],
                        "win_rate": round((totals["wins"] / totals["matches"]) * 100, 1) if totals["matches"] else 0.0,
                    }
                )(_find_player_by_name(db, partner_name))
                for partner_name, totals in partner_totals.items()
                if totals["matches"] > 0
            ]

            top_partners = sorted(
                ranked_partners,
                key=lambda item: (-item["win_rate"], -item["wins"], -item["matches_played"], item["partner_name"]),
            )[:3]
            most_played_partner = min(
                ranked_partners,
                key=lambda item: (-item["matches_played"], -item["wins"], -item["win_rate"], item["partner_name"]),
                default=None,
            )

            summary = _to_player_stats_summary_response(db, row)
            return PlayerStatsDetailResponse(
                **summary.model_dump(),
                most_played_partner=PartnerStatsResponse(**most_played_partner) if most_played_partner else None,
                top_partners=[PartnerStatsResponse(**partner) for partner in top_partners],
            )

    return _cache_get_or_set(
        "player-stats",
        ["detail", player_name],
        _cache_ttl("CACHE_TTL_PLAYER_STATS", 60),
        build_response,
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_shared_session(session_id: str, edit_token: str | None = None):
    with get_db_session() as db:
        record = db.scalar(
            select(SharedSessionRecord).where(SharedSessionRecord.session_id == session_id)
        )
        if not record:
            raise HTTPException(status_code=404, detail="Shared session not found")
        payload = _hydrate_legacy_session_storage(db, record, _upgrade_session_payload(deepcopy(record.data)))
        _require_edit_access(payload, edit_token)
        completion_state = _get_session_completion_state(db, record, payload)
        round_records = db.scalars(
            select(SessionRoundRecord).where(SessionRoundRecord.session_id == session_id)
        ).all()
        for round_record in round_records:
            db.delete(round_record)
        score_records = db.scalars(
            select(SessionScoreRecord).where(SessionScoreRecord.session_id == session_id)
        ).all()
        for score_record in score_records:
            db.delete(score_record)
        if completion_state["completed"]:
            _delete_completed_session_history(db, session_id)
        else:
            _delete_session_analytics(db, session_id)
            _rebuild_player_stats_summary(db)
        db.delete(record)
        _invalidate_session_views(session_id, include_analytics=completion_state["completed"])
    return Response(status_code=204)


@app.post("/api/sessions/{session_id}/rename", response_model=SharedSessionResponse)
def rename_shared_session(session_id: str, req: SessionRenameRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        next_name = req.name.strip()
        if record.name == next_name and payload.get("name") == next_name:
            return False

        payload["name"] = next_name
        record.name = next_name
        db.add(record)
        return True

    return _update_session_record(session_id, updater, edit_token=edit_token)


@app.post("/api/sessions/{session_id}/start-round", response_model=SharedSessionResponse)
def start_round(session_id: str, req: RoundStartRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        if req.stage == "league":
            current_round = _get_stage_progress(db, session_id, "league")[1]
            if req.round_index != current_round + 1:
                raise HTTPException(status_code=409, detail="Round must be started in sequence")
            if req.round_index >= len(payload.get("roster", {}).get("rounds", [])):
                raise HTTPException(status_code=400, detail="Invalid round index")
            _capture_undo_snapshot(payload)
            round_record = _get_or_create_round_record(db, session_id, "league", req.round_index)
            round_record.started = True
            db.add(round_record)
            return True

        if req.stage != "knockout":
            raise HTTPException(status_code=400, detail="Invalid stage")

        if payload.get("draw_config", {}).get("draw_type") != "league_knockout":
            raise HTTPException(
                status_code=409,
                detail="Knockout rounds are only available for league + knockout sessions",
            )
        league_records, _ = _get_stage_progress(db, session_id, "league")
        total_league_rounds = len(payload.get("roster", {}).get("rounds", []))
        if len(league_records) < total_league_rounds or not all(item.ended for item in league_records):
            raise HTTPException(status_code=409, detail="Finish all league rounds before starting the knockout")

        current_round = _get_stage_progress(db, session_id, "knockout")[1]
        if req.round_index != current_round + 1:
            raise HTTPException(status_code=409, detail="Round must be started in sequence")
        _capture_undo_snapshot(payload)
        round_record = _get_or_create_round_record(db, session_id, "knockout", req.round_index)
        round_record.started = True
        db.add(round_record)
        return True

    return _update_session_record(session_id, updater, edit_token=edit_token)


@app.post("/api/sessions/{session_id}/end-round", response_model=SharedSessionResponse)
def end_round(session_id: str, req: RoundEndRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        if req.stage == "league":
            round_records, active_round = _get_stage_progress(db, session_id, "league")
            round_record = next((item for item in round_records if item.round_index == req.round_index), None)
            if req.round_index != active_round or not round_record or not round_record.started:
                raise HTTPException(status_code=409, detail="Only the active round can be ended")
            if round_record.ended:
                raise HTTPException(status_code=409, detail="Round has already been ended")

            league_rounds = payload.get("roster", {}).get("rounds", [])
            round_sizes = [len(round_data.get("courts", [])) for round_data in league_rounds]
            round_scores = _get_scores_by_round(db, session_id, "league", round_sizes)[req.round_index]
            if not all(score["teamA"] != "" and score["teamB"] != "" for score in round_scores):
                raise HTTPException(status_code=409, detail="Enter all scores before ending the round")

            _capture_undo_snapshot(payload)
            round_record.ended = True
            db.add(round_record)
            return True

        if req.stage != "knockout":
            raise HTTPException(status_code=400, detail="Invalid stage")

        if payload.get("draw_config", {}).get("draw_type") != "league_knockout":
            raise HTTPException(
                status_code=409,
                detail="Knockout rounds are only available for league + knockout sessions",
            )
        league_records, _ = _get_stage_progress(db, session_id, "league")
        total_league_rounds = len(payload.get("roster", {}).get("rounds", []))
        if len(league_records) < total_league_rounds or not all(item.ended for item in league_records):
            raise HTTPException(status_code=409, detail="Finish all league rounds before starting the knockout")

        round_records, active_round = _get_stage_progress(db, session_id, "knockout")
        round_record = next((item for item in round_records if item.round_index == req.round_index), None)
        if req.round_index != active_round or not round_record or not round_record.started:
            raise HTTPException(status_code=409, detail="Only the active round can be ended")
        if round_record.ended:
            raise HTTPException(status_code=409, detail="Round has already been ended")

        round_scores = _get_scores_by_round(db, session_id, "knockout", [0 for _ in range(req.round_index + 1)])[req.round_index]
        if not round_scores or not all(score["teamA"] != "" and score["teamB"] != "" for score in round_scores):
            raise HTTPException(status_code=409, detail="Enter all scores before ending the round")
        if any(score["teamA"] == score["teamB"] for score in round_scores):
            raise HTTPException(
                status_code=409,
                detail="Knockout matches cannot end in a tie - adjust the scores or play a tiebreaker",
            )

        _capture_undo_snapshot(payload)
        round_record.ended = True
        db.add(round_record)
        return True

    return _update_session_record(session_id, updater, edit_token=edit_token)


@app.post("/api/sessions/{session_id}/undo", response_model=SharedSessionResponse)
def undo_last_change(session_id: str, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        if not payload["undo_stack"]:
            raise HTTPException(status_code=409, detail="Nothing to undo")

        snapshot = payload["undo_stack"].pop()
        _restore_undo_snapshot(payload, snapshot)
        return True

    return _update_session_record(session_id, updater, edit_token=edit_token)


@app.post("/api/sessions/{session_id}/edit-round", response_model=SharedSessionResponse)
def edit_round(session_id: str, req: RoundEditRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        if req.stage == "league":
            if req.round_index < 0 or req.round_index >= len(payload.get("roster", {}).get("rounds", [])):
                raise HTTPException(status_code=400, detail="Invalid round index")
            round_record = db.get(SessionRoundRecord, (session_id, "league", req.round_index))
            if not round_record or not round_record.ended:
                raise HTTPException(status_code=409, detail="Only ended rounds can be edited")

            league_records, _ = _get_stage_progress(db, session_id, "league")
            ended_indices = [item.round_index for item in league_records if item.ended]
            if req.round_index != max(ended_indices):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Only the most recently ended round can be edited; "
                        "re-opening an earlier round would leave later rounds inconsistent"
                    ),
                )

            knockout_rounds = db.scalars(
                select(SessionRoundRecord).where(
                    SessionRoundRecord.session_id == session_id,
                    SessionRoundRecord.stage == "knockout",
                )
            ).all()
            knockout_scores = db.scalars(
                select(SessionScoreRecord).where(
                    SessionScoreRecord.session_id == session_id,
                    SessionScoreRecord.stage == "knockout",
                )
            ).all()
            if (knockout_rounds or knockout_scores) and not req.confirm_knockout_wipe:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Editing a league round deletes all knockout scores and results for this "
                        "session. Retry with confirm_knockout_wipe=true to proceed."
                    ),
                )

            _capture_undo_snapshot(payload)
            round_record.ended = False
            db.add(round_record)
            for knockout_round in knockout_rounds:
                db.delete(knockout_round)
            for knockout_score in knockout_scores:
                db.delete(knockout_score)
            return True

        if req.stage != "knockout":
            raise HTTPException(status_code=400, detail="Invalid stage")

        round_record = db.get(SessionRoundRecord, (session_id, "knockout", req.round_index))
        if not round_record:
            raise HTTPException(status_code=400, detail="Invalid round index")
        if not round_record.ended:
            raise HTTPException(status_code=409, detail="Only ended rounds can be edited")

        _capture_undo_snapshot(payload)
        later_rounds = db.scalars(
            select(SessionRoundRecord).where(
                SessionRoundRecord.session_id == session_id,
                SessionRoundRecord.stage == "knockout",
                SessionRoundRecord.round_index > req.round_index,
            )
        ).all()
        for later_round in later_rounds:
            db.delete(later_round)
        later_scores = db.scalars(
            select(SessionScoreRecord).where(
                SessionScoreRecord.session_id == session_id,
                SessionScoreRecord.stage == "knockout",
                SessionScoreRecord.round_index > req.round_index,
            )
        ).all()
        for later_score in later_scores:
            db.delete(later_score)
        round_record.ended = False
        round_record.started = True
        db.add(round_record)
        return True

    return _update_session_record(session_id, updater, edit_token=edit_token)


@app.post("/api/sessions/{session_id}/score", response_model=ScoreMutationResponse)
def update_score(session_id: str, req: ScoreUpdateRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        return _apply_score_update(db, session_id, payload, req)

    return _update_session_record(
        session_id,
        updater,
        edit_token=edit_token,
        response_builder=lambda record, db: ScoreMutationResponse(version=record.version),
    )


@app.post("/api/sessions/{session_id}/scores/batch", response_model=ScoreMutationResponse)
def update_scores_batch(session_id: str, req: BatchScoreUpdateRequest, edit_token: str | None = None):
    def updater(db, record, payload: dict):
        changed = False
        for update in req.updates:
            if update.stage != req.stage or update.round_index != req.round_index:
                raise HTTPException(status_code=400, detail="Batch updates must target the same stage and round")
            if _apply_score_update(db, session_id, payload, update):
                changed = True
        return changed

    return _update_session_record(
        session_id,
        updater,
        edit_token=edit_token,
        response_builder=lambda record, db: ScoreMutationResponse(version=record.version),
    )
