"""Project custom fields: the four rings' definition, value, and read rules.

The definition and value tables live in
``repos/project_custom_fields.py``. This module owns everything above SQL
(PLAN.md §6):

* every write asserts a project role through
  :meth:`ProjectService.assert_project_role` — there is no second permission
  check in the custom-field path;
* the four-type system, the ``select`` option rules, the ``key`` shape and the
  required-value semantics are checked here and nowhere else;
* a definition is only usable inside the project that owns it.

Two rules deserve calling out because they protect user data or a frozen shape:

* **S-2** — removing a ``select`` option that stored values still reference is
  refused with 409. Those values are *not* rewritten or deleted; the patch is
  rejected as a whole.
* **S-12** — concurrent definition edits are last-write-wins. No version column
  and no optimistic-lock retry exists, by decision.

Values are always handed to the repo as **normalised strings** (PLAN §6.2):
the column is TEXT and no per-type column was added.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence

from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_custom_fields import (
    CUSTOM_FIELD_TYPES,
    ProjectCustomFieldRepo,
    ProjectCustomFieldRow,
)
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import PROJECT_READ, PROJECT_WRITE, ProjectActor, ProjectService

#: ``key`` is a lower-snake identifier so it can be used as a stable JSON key.
CUSTOM_FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

CUSTOM_FIELD_LABEL_MAX_LENGTH = 64
CUSTOM_FIELD_TEXT_MAX_LENGTH = 2000
CUSTOM_FIELD_OPTION_MAX_COUNT = 50
CUSTOM_FIELD_OPTION_MAX_LENGTH = 64

#: Accepted unix-second window: 1970-01-01T00:00:01Z .. 2100-01-01T00:00:00Z.
#: The upper bound also rejects millisecond timestamps by a wide margin.
CUSTOM_FIELD_TIMESTAMP_MIN = 1
CUSTOM_FIELD_TIMESTAMP_MAX = 4102444800


def _field_invalid(message: str) -> OctopError:
    """A bad *definition* — 409 ``PROJECT_CUSTOM_FIELD_INVALID``."""
    return OctopError(ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, message)


def _value_invalid(message: str) -> OctopError:
    """A bad *value* — 400 ``PROJECT_CUSTOM_FIELD_VALUE_INVALID``."""
    return OctopError(ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, message)


def _field_not_found(message: str) -> OctopError:
    """Definition missing, or owned by another project — 404."""
    return OctopError(ErrorCode.PROJECT_CUSTOM_FIELD_NOT_FOUND, message)


def normalize_field_key(raw: object) -> str:
    key = str(raw or "").strip()
    if not CUSTOM_FIELD_KEY_PATTERN.match(key):
        raise _field_invalid("A field key must match ^[a-z][a-z0-9_]{0,31}$.")
    return key


def normalize_field_label(raw: object) -> str:
    label = str(raw or "").strip()
    if not label:
        raise _field_invalid("A field label is required.")
    if len(label) > CUSTOM_FIELD_LABEL_MAX_LENGTH:
        raise _field_invalid(
            f"A field label may not exceed {CUSTOM_FIELD_LABEL_MAX_LENGTH} characters."
        )
    return label


def normalize_field_type(raw: object) -> str:
    type_name = str(raw or "").strip()
    if type_name not in CUSTOM_FIELD_TYPES:
        raise _field_invalid(f"Unknown field type: '{type_name}'.")
    return type_name


def normalize_field_options(type_name: str, raw: object) -> list[str]:
    """Options are only meaningful for ``select``; anything else must be empty."""
    if raw is None or raw is UNSET:
        raw = []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
        raise _field_invalid("Field options must be a list of strings.")
    options: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise _field_invalid("Every field option must be a string.")
        option = item.strip()
        if not option:
            raise _field_invalid("A field option may not be empty.")
        if len(option) > CUSTOM_FIELD_OPTION_MAX_LENGTH:
            raise _field_invalid(
                f"A field option may not exceed {CUSTOM_FIELD_OPTION_MAX_LENGTH} characters."
            )
        options.append(option)
    if len(set(options)) != len(options):
        raise _field_invalid("Field options must be unique.")
    if type_name == "select":
        if not options:
            raise _field_invalid("A 'select' field needs at least one option.")
        if len(options) > CUSTOM_FIELD_OPTION_MAX_COUNT:
            raise _field_invalid(
                f"A 'select' field may not have more than {CUSTOM_FIELD_OPTION_MAX_COUNT} options."
            )
    elif options:
        raise _field_invalid("Only a 'select' field may declare options.")
    return options


def _as_number(raw: object) -> float | int:
    if isinstance(raw, bool):
        raise _value_invalid("A number field does not accept a boolean.")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if not math.isfinite(raw):
            raise _value_invalid("A number field does not accept a non-finite value.")
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise _value_invalid("A number field does not accept an empty string.")
        try:
            return int(text)
        except ValueError:
            pass
        try:
            parsed = float(text)
        except ValueError as exc:
            raise _value_invalid(f"'{raw}' is not a number.") from exc
        if not math.isfinite(parsed):
            raise _value_invalid("A number field does not accept a non-finite value.")
        return parsed
    raise _value_invalid("A number field accepts a number or a numeric string.")


def normalize_field_value(row: ProjectCustomFieldRow, raw: object) -> str:
    """Validate one value against its definition and return the stored form."""
    field_type = row.type
    if field_type == "text":
        if not isinstance(raw, str):
            raise _value_invalid("A text field accepts a string.")
        # The limit is measured on the trimmed value; the original is stored.
        if len(raw.strip()) > CUSTOM_FIELD_TEXT_MAX_LENGTH:
            raise _value_invalid(
                f"A text value may not exceed {CUSTOM_FIELD_TEXT_MAX_LENGTH} characters."
            )
        return raw
    if field_type == "number":
        number = _as_number(raw)
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        return json.dumps(number)
    if field_type == "date":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise _value_invalid("A date field accepts unix seconds as an integer.")
        if not (CUSTOM_FIELD_TIMESTAMP_MIN <= raw < CUSTOM_FIELD_TIMESTAMP_MAX):
            raise _value_invalid("A date value is outside the accepted range.")
        return str(raw)
    if field_type == "select":
        if not isinstance(raw, str):
            raise _value_invalid("A select field accepts a string.")
        if raw not in row.options:
            raise _value_invalid(f"'{raw}' is not one of this field's options.")
        return raw
    raise _value_invalid(f"Unknown field type: '{field_type}'.")


class ProjectCustomFieldService:
    """Definitions and per-task values for one project at a time."""

    def __init__(
        self,
        services: SharedServices,
        *,
        project_service: ProjectService | None = None,
    ) -> None:
        self._services = services
        self._fields: ProjectCustomFieldRepo = services.project_custom_field_repo
        self._projects = (
            project_service if project_service is not None else ProjectService(services)
        )

    # ── definitions (ring ①) ─────────────────────────────────────────────────

    def list_fields(self, project_id: str, *, user: ProjectActor) -> list[ProjectCustomFieldRow]:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        return self._fields.list_by_project(project_id)

    def create_field(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        key: object,
        label: object,
        type: object,
        required: bool = False,
        options: object = (),
        sort_order: int | None = None,
    ) -> ProjectCustomFieldRow:
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        clean_type = normalize_field_type(type)
        clean_key = normalize_field_key(key)
        clean_label = normalize_field_label(label)
        clean_options = normalize_field_options(clean_type, options)
        if self._fields.find_by_key(project_id, clean_key) is not None:
            raise _field_invalid(f"A field with key '{clean_key}' already exists in this project.")
        try:
            return self._fields.create(
                project_id=project_id,
                key=clean_key,
                label=clean_label,
                type=clean_type,
                required=bool(required),
                options=clean_options,
                sort_order=sort_order,
                created_by=user.id,
            )
        except ValueError as exc:
            raise _field_invalid(
                f"A field with key '{clean_key}' already exists in this project."
            ) from exc

    def update_field(
        self,
        project_id: str,
        field_id: str,
        *,
        user: ProjectActor,
        label: object = UNSET,
        required: object = UNSET,
        options: object = UNSET,
        sort_order: object = UNSET,
        type: object = UNSET,
        key: object = UNSET,
    ) -> ProjectCustomFieldRow:
        """Patch ``label`` / ``required`` / ``options`` / ``sort_order``.

        ``type`` and ``key`` are immutable: changing either would silently
        reinterpret every value already stored against the definition, so a
        request carrying them is refused instead of ignored. Concurrent edits
        are last-write-wins (S-12) — there is no version column.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        field = self._require_field(project_id, field_id)
        if type is not UNSET or key is not UNSET:
            raise _field_invalid("A custom field's 'type' and 'key' cannot be changed.")

        clean_label: object = UNSET
        if label is not UNSET:
            clean_label = normalize_field_label(label)
        clean_required: object = UNSET
        if required is not UNSET:
            clean_required = bool(required)
        clean_sort_order: object = UNSET
        if sort_order is not UNSET:
            if isinstance(sort_order, bool) or not isinstance(sort_order, int):
                raise _field_invalid("'sort_order' must be an integer.")
            clean_sort_order = sort_order

        clean_options: object = UNSET
        if options is not UNSET:
            clean_options = normalize_field_options(field.type, options)
            self._assert_option_removal_is_safe(field, clean_options)

        updated = self._fields.update(
            field.field_id,
            label=clean_label,
            required=clean_required,
            options=clean_options,
            sort_order=clean_sort_order,
        )
        if updated is None:
            raise _field_not_found(f"Unknown custom field: '{field_id}'.")
        return updated

    def delete_field(self, project_id: str, field_id: str, *, user: ProjectActor) -> bool:
        """Delete a definition; its values disappear through the FK cascade."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        field = self._require_field(project_id, field_id)
        return self._fields.delete(field.field_id)

    # ── values (rings ② ③) ───────────────────────────────────────────────────

    def get_task_fields(
        self, project_id: str, task_id: str, *, user: ProjectActor
    ) -> tuple[list[ProjectCustomFieldRow], dict[str, str]]:
        """The read ring: definitions plus the values stored on one task."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        self._projects.get_task(project_id, task_id, user=user)
        return (
            self._fields.list_by_project(project_id),
            self._fields.list_values_for_task(task_id),
        )

    def set_task_values(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        values: Mapping[str, object],
    ) -> dict[str, str]:
        """Replace a task's values (``PUT …/tasks/{tid}/custom-fields``).

        All ``required`` definitions are validated on every call, because this
        endpoint always carries the task's complete value set.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        self._projects.get_task(project_id, task_id, user=user)
        normalized = self.validate_task_values(project_id, values, require_complete=True)
        self._fields.set_task_values(task_id, normalized)
        return normalized

    def apply_task_values(
        self,
        project_id: str,
        task_id: str,
        *,
        user: ProjectActor,
        values: Mapping[str, object],
    ) -> dict[str, str]:
        """Upsert the given values, then re-check required against the merge.

        This is the entry point for ``POST /tasks`` and ``PATCH /tasks/{tid}``
        when the body carries a ``custom_fields`` key (PLAN §6.3). Values already
        on the task are kept, so a partial body never clears a sibling field.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_WRITE)
        self._projects.get_task(project_id, task_id, user=user)
        incoming = self._normalize_given(project_id, values)
        merged = self._fields.list_values_for_task(task_id)
        merged.update(incoming)
        self._assert_required_present(project_id, merged)
        self._fields.upsert_values(task_id, incoming)
        return merged

    def validate_task_values(
        self,
        project_id: str,
        values: Mapping[str, object],
        *,
        require_complete: bool,
    ) -> dict[str, str]:
        """Validate a value payload without writing it.

        ``require_complete=True`` demands every ``required`` definition be
        present (the ``PUT`` ring). ``False`` only checks what was given — the
        caller merges first if it needs the full required check.

        Exposed so the task routes can apply the *same* validation when their
        body carries a ``custom_fields`` key; a second implementation of these
        rules is a defect.
        """
        normalized = self._normalize_given(project_id, values)
        if require_complete:
            self._assert_required_present(project_id, normalized)
        return normalized

    def resolve_task_values(self, task_ids: Sequence[str]) -> dict[str, dict[str, str]]:
        """Batch read for embedding values in task responses.

        Permission is deliberately not re-checked: callers reach this only after
        the task list was authorized, and re-asserting per task would be N+1.
        """
        return self._fields.list_values_for_tasks([str(task_id) for task_id in task_ids])

    # ── internals ────────────────────────────────────────────────────────────

    def _require_field(self, project_id: str, field_id: str) -> ProjectCustomFieldRow:
        field = self._fields.get(field_id)
        if field is None or field.project_id != project_id:
            raise _field_not_found(f"Unknown custom field: '{field_id}'.")
        return field

    def _normalize_given(self, project_id: str, values: Mapping[str, object]) -> dict[str, str]:
        definitions = {row.field_id: row for row in self._fields.list_by_project(project_id)}
        out: dict[str, str] = {}
        for field_id, raw in values.items():
            row = definitions.get(str(field_id))
            if row is None:
                # A definition from another project is indistinguishable from a
                # missing one to the caller.
                raise _field_not_found(f"Unknown custom field: '{field_id}'.")
            out[row.field_id] = normalize_field_value(row, raw)
        return out

    def _assert_required_present(self, project_id: str, values: Mapping[str, str]) -> None:
        for row in self._fields.list_by_project(project_id):
            if row.required and row.field_id not in values:
                raise _value_invalid(f"'{row.label}' is required.")

    def _assert_option_removal_is_safe(
        self, field: ProjectCustomFieldRow, new_options: list[str]
    ) -> None:
        """S-2: never drop an option that stored values still reference.

        The patch is refused as a whole — no value is rewritten, and the old
        option list stays intact, so nothing is silently destroyed.
        """
        dropped = [option for option in field.options if option not in new_options]
        for option in dropped:
            used = self._fields.count_values_for_option(field.field_id, option)
            if used:
                raise _field_invalid(
                    f"The option '{option}' is still used by {used} task value(s); "
                    "clear those values before removing it."
                )
