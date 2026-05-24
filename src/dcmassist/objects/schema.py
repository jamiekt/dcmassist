"""Schema plugin.

The DDL is synthesized from `SHOW SCHEMAS` (not `GET_DDL`, which is recursive
over every contained object — see `_schema_ddl.py`). The macro accepts every
documented `CREATE SCHEMA` clause as a structured kwarg; `parse_schema_ddl`
walks the DEFINE block produced by the rewrite chain and extracts each clause.
Anything unrecognised raises so the orchestrator surfaces it as an export
error.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.objects._schema_ddl import (
    SchemaNotExportable,
    synthesize_schema_ddl,
)
from dcmassist.objects._show_paging import paginated_show
from dcmassist.plugin import ProgressCallback
from dcmassist.rewrite import JinjaExpr
from dcmassist.types import FQN


class SchemaParseError(ValueError):
    """Raised when a DEFINE SCHEMA block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+(?P<transient>TRANSIENT\s+)?SCHEMA\s+"
    r"(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_MANAGED_ACCESS_RE = re.compile(r"\s*WITH\s+MANAGED\s+ACCESS\b", re.IGNORECASE)
_DATA_RETENTION_RE = re.compile(
    r"\s*DATA_RETENTION_TIME_IN_DAYS\s*=\s*(?P<v>\d+)", re.IGNORECASE
)
_MAX_EXTENSION_RE = re.compile(
    r"\s*MAX_DATA_EXTENSION_TIME_IN_DAYS\s*=\s*(?P<v>\d+)", re.IGNORECASE
)
_DEFAULT_DDL_COLLATION_RE = re.compile(
    r"\s*DEFAULT_DDL_COLLATION\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE
)
_EXTERNAL_VOLUME_RE = re.compile(
    r"\s*EXTERNAL_VOLUME\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE
)
_CATALOG_RE = re.compile(r"\s*CATALOG\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)
_LOG_LEVEL_RE = re.compile(r"\s*LOG_LEVEL\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)
_TRACE_LEVEL_RE = re.compile(
    r"\s*TRACE_LEVEL\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE
)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)


def parse_schema_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE SCHEMA block.

    Returns a dict with `name`, optional `transient`, and any clauses present.
    The `database` kwarg is supplied by the plugin so it arrives as a
    JinjaExpr.
    """
    text = ddl.strip().rstrip(";").strip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise SchemaParseError(f"could not parse DEFINE SCHEMA header: {ddl!r}")
    name = _name_from_fqn(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"name": name}
    if header.group("transient"):
        kwargs["transient"] = True

    pos = header.end()
    matchers: list[tuple[re.Pattern[str], str, Any]] = [
        (_MANAGED_ACCESS_RE, "managed_access", lambda _m: True),
        (
            _DATA_RETENTION_RE,
            "data_retention_time_in_days",
            lambda m: int(m.group("v")),
        ),
        (
            _MAX_EXTENSION_RE,
            "max_data_extension_time_in_days",
            lambda m: int(m.group("v")),
        ),
        (
            _DEFAULT_DDL_COLLATION_RE,
            "default_ddl_collation",
            lambda m: m.group("v").replace("''", "'"),
        ),
        (
            _EXTERNAL_VOLUME_RE,
            "external_volume",
            lambda m: m.group("v").replace("''", "'"),
        ),
        (_CATALOG_RE, "catalog", lambda m: m.group("v").replace("''", "'")),
        (_LOG_LEVEL_RE, "log_level", lambda m: m.group("v").replace("''", "'")),
        (_TRACE_LEVEL_RE, "trace_level", lambda m: m.group("v").replace("''", "'")),
        (_COMMENT_RE, "comment", lambda m: m.group("v").replace("''", "'")),
    ]
    while pos < len(text):
        matched = False
        for pattern, key, extractor in matchers:
            m = pattern.match(text, pos)
            if m is not None:
                kwargs[key] = extractor(m)
                pos = m.end()
                matched = True
                break
        if matched:
            continue
        if text[pos:].strip() == "":
            break
        raise SchemaParseError(
            f"unrecognised content in DEFINE SCHEMA at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    return kwargs


def _name_from_fqn(fqn_text: str, original_ddl: str) -> str:
    """Extract the schema name from a 1- or 2-part FQN. The database part
    is dropped because the plugin passes `database` as a separate JinjaExpr."""
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 2:
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    raise SchemaParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE SCHEMA: {original_ddl!r}"
    )


class SchemaPlugin(V1ObjectPlugin):
    type_name = "Schema"
    file_slug = "schema"
    SHOW_FORM = "SHOW SCHEMAS"
    # GET_DDL_TYPE retained for symmetry; unused. GET_DDL('SCHEMA', ...) is
    # recursive and unworkable on busy schemas — see _schema_ddl.py.
    GET_DDL_TYPE = "SCHEMA"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_schema(\n"
        "    database,\n"
        "    name,\n"
        "    transient=False,\n"
        "    managed_access=False,\n"
        "    data_retention_time_in_days=None,\n"
        "    max_data_extension_time_in_days=None,\n"
        "    default_ddl_collation=None,\n"
        "    external_volume=None,\n"
        "    catalog=None,\n"
        "    log_level=None,\n"
        "    trace_level=None,\n"
        "    comment=None\n"
        ") %}\n"
        "DEFINE {% if transient %}TRANSIENT {% endif %}SCHEMA "
        "{{ database }}.{{ name }}\n"
        "{%- if managed_access %}\n"
        "  WITH MANAGED ACCESS\n"
        "{%- endif %}\n"
        "{%- if data_retention_time_in_days is not none %}\n"
        "  DATA_RETENTION_TIME_IN_DAYS = {{ data_retention_time_in_days }}\n"
        "{%- endif %}\n"
        "{%- if max_data_extension_time_in_days is not none %}\n"
        "  MAX_DATA_EXTENSION_TIME_IN_DAYS = "
        "{{ max_data_extension_time_in_days }}\n"
        "{%- endif %}\n"
        "{%- if default_ddl_collation is not none %}\n"
        "  DEFAULT_DDL_COLLATION = '{{ default_ddl_collation }}'\n"
        "{%- endif %}\n"
        "{%- if external_volume is not none %}\n"
        "  EXTERNAL_VOLUME = '{{ external_volume }}'\n"
        "{%- endif %}\n"
        "{%- if catalog is not none %}\n"
        "  CATALOG = '{{ catalog }}'\n"
        "{%- endif %}\n"
        "{%- if log_level is not none %}\n"
        "  LOG_LEVEL = '{{ log_level }}'\n"
        "{%- endif %}\n"
        "{%- if trace_level is not none %}\n"
        "  TRACE_LEVEL = '{{ trace_level }}'\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{% endmacro %}\n"
    )

    def discover(
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        # SHOW SCHEMAS returns `name` (schema) and `database_name`; there is no
        # `schema_name`. The schema's FQN is db.schema.schema since the schema's
        # name is its own schema component.
        # PUBLIC and INFORMATION_SCHEMA are always present in a Snowflake
        # database, so we skip emitting DEFINE SCHEMA for them — DCM rejects
        # defining a schema that already exists. Objects *inside* PUBLIC are
        # still exported by the per-type plugins.
        rows: list[dict[str, Any]] = []
        if schemas:
            # Snowflake LIKE doesn't accept arbitrary lists; enumerate explicitly.
            total = len(schemas)
            for index, name in enumerate(schemas, start=1):
                if progress is not None:
                    count = f" {index}/{total}" if total > 1 else ""
                    progress(f"discovering Schema{count} {database}.{name}")
                cursor.execute(f"SHOW SCHEMAS LIKE '{name}' IN DATABASE {database}")
                rows.extend(cursor.fetchall())
        else:
            rows.extend(paginated_show(cursor, f"SHOW SCHEMAS IN DATABASE {database}"))

        out = [
            FQN(database=database, schema=row["name"], name=row["name"])
            for row in rows
            if row["name"] not in ("PUBLIC", "INFORMATION_SCHEMA")
        ]
        return sorted(out, key=lambda f: f.name)

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        # Synthesize from SHOW rather than GET_DDL: GET_DDL('SCHEMA', ...) is
        # recursive over every contained object. See _schema_ddl.py.
        cursor.execute(f"SHOW SCHEMAS LIKE '{fqn.name}' IN DATABASE {fqn.database}")
        rows = cursor.fetchall()
        if not rows:
            raise SchemaNotExportable(
                f"schema {fqn}: SHOW SCHEMAS LIKE returned no rows"
            )
        return synthesize_schema_ddl(fqn, rows[0])

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_schema_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = SchemaPlugin()
