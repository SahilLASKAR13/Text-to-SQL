"""Builds the compact schema description that is sent to the LLM."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ColumnInfo:
    name: str
    sql_type: str
    nulls: int
    unique: int
    samples: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None
    is_date: bool = False


@dataclass
class TableInfo:
    name: str
    rows: int
    columns: list[ColumnInfo]


class SchemaAnalyzer:
    def __init__(self, max_categories: int = 15, sample_size: int = 3):
        self.max_categories = max_categories
        self.sample_size = sample_size

    @staticmethod
    def _sql_type(series: pd.Series) -> str:
        if pd.api.types.is_bool_dtype(series) or pd.api.types.is_integer_dtype(series):
            return "INTEGER"
        if pd.api.types.is_float_dtype(series):
            return "REAL"
        return "TEXT"

    @staticmethod
    def _short(value, limit: int = 40) -> str:
        text = str(value)
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _analyze_column(self, series: pd.Series) -> ColumnInfo:
        sql_type = self._sql_type(series)
        non_null = series.dropna()
        info = ColumnInfo(
            name=str(series.name),
            sql_type=sql_type,
            nulls=int(series.isna().sum()),
            unique=int(non_null.nunique()),
            samples=[self._short(v) for v in non_null.head(self.sample_size).tolist()],
        )
        if non_null.empty:
            return info

        if sql_type == "TEXT":
            head = non_null.astype(str).head(50)
            info.is_date = bool(head.str.match(r"^\d{4}-\d{2}-\d{2}").all())
            if info.is_date:
                info.min_value, info.max_value = str(non_null.min()), str(non_null.max())
            elif info.unique <= self.max_categories:
                counts = non_null.astype(str).value_counts()
                info.categories = [self._short(v) for v in counts.index.tolist()]
        else:
            info.min_value, info.max_value = str(non_null.min()), str(non_null.max())
        return info

    def analyze(self, tables: dict[str, pd.DataFrame]) -> list[TableInfo]:
        return [
            TableInfo(
                name=name,
                rows=len(df),
                columns=[self._analyze_column(df[c]) for c in df.columns],
            )
            for name, df in tables.items()
        ]

    @staticmethod
    def describe(infos: list[TableInfo]) -> str:
        lines: list[str] = []
        for table in infos:
            lines.append(f"Table: {table.name} ({table.rows} rows)")
            for c in table.columns:
                detail = ""
                if c.is_date:
                    detail = f"dates stored as YYYY-MM-DD text, range {c.min_value} to {c.max_value}"
                elif c.categories:
                    detail = "values: " + ", ".join(c.categories)
                elif c.min_value is not None:
                    detail = f"range {c.min_value} to {c.max_value}"
                sample = f"e.g. {', '.join(c.samples)}" if c.samples else ""
                extras = "; ".join(x for x in (detail, sample) if x)
                null_note = f" [{c.nulls} nulls]" if c.nulls else ""
                lines.append(f"  - {c.name} ({c.sql_type}){null_note}" + (f": {extras}" if extras else ""))
            lines.append("")
        return "\n".join(lines).strip()

    def build_schema_text(self, tables: dict[str, pd.DataFrame]) -> str:
        return self.describe(self.analyze(tables))
