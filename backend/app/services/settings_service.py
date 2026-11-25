"""Runtime settings: env-var defaults overlaid with values saved from the UI."""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.db.models import AppSetting
from app.schemas.settings import RuntimeSettings, RuntimeSettingsUpdate


def default_runtime_settings(settings: Settings) -> RuntimeSettings:
    return RuntimeSettings(
        llm_model=settings.ollama_model,
        llm_temperature=settings.llm_temperature,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        retrieval_top_k=settings.retrieval_top_k,
        similarity_threshold=settings.similarity_threshold,
        relative_score_cutoff=settings.relative_score_cutoff,
        max_context_chars=settings.max_context_chars,
        history_turns=settings.history_turns,
    )


class SettingsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def defaults(self) -> RuntimeSettings:
        return default_runtime_settings(self._settings)

    def get(self, session: Session) -> RuntimeSettings:
        values = self.defaults().model_dump()
        fields = set(RuntimeSettings.model_fields)
        for row in session.scalars(select(AppSetting)):
            if row.key in fields:
                values[row.key] = row.value
        try:
            return RuntimeSettings(**values)
        except PydanticValidationError:
            # Corrupt or out-of-range stored overrides: fall back to defaults.
            return self.defaults()

    def update(self, session: Session, update: RuntimeSettingsUpdate) -> RuntimeSettings:
        changes = update.model_dump(exclude_none=True)
        merged = {**self.get(session).model_dump(), **changes}
        try:
            validated = RuntimeSettings(**merged)
        except PydanticValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'settings'}: {e['msg']}"
                for e in exc.errors()
            )
            raise ValidationError(errors) from exc
        for key in changes:
            row = session.get(AppSetting, key)
            value = getattr(validated, key)
            if row is None:
                session.add(AppSetting(key=key, value=value))
            else:
                row.value = value
        session.flush()
        return validated

    def reset(self, session: Session) -> RuntimeSettings:
        session.execute(delete(AppSetting))
        session.flush()
        return self.defaults()
