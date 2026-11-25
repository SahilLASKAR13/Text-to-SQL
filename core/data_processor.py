"""Cleans raw DataFrames so they load into SQLite predictably."""
from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd

from utils.helpers import make_unique, to_snake_case

_DATE_PATTERN = (
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
    r"([ T]\d{1,2}:\d{2}(:\d{2})?)?\s*$"
)
# Columns like phone / zip / id keep their text form (leading zeros matter)
_ID_HINT = re.compile(r"(^|_)(id|code|zip|zipcode|pin|pincode|phone|mobile|ssn|sku|number|no)($|_)")
_CURRENCY_NOISE = r"[,$€£₹\s]"
_DMY_PARTS = re.compile(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}")

# For dates like 03/04/2024 where nothing in the column settles the order,
# assume day-first (common in India/UK/EU). Set to False for US-style data.
DAYFIRST_WHEN_AMBIGUOUS = True


def _infer_dayfirst(values: pd.Series) -> bool:
    """Decide dd/mm vs mm/dd from the data itself (e.g. a value like 25/03/2024)."""
    parts = values.astype(str).str.extract(_DMY_PARTS).dropna().astype(int)
    if parts.empty:
        return False  # ISO-style dates, order irrelevant
    if (parts[0] > 12).any():
        return True
    if (parts[1] > 12).any():
        return False
    return DAYFIRST_WHEN_AMBIGUOUS


def _format_datetimes(series: pd.Series) -> pd.Series:
    """Store dates as ISO text so SQLite's date functions work on them."""
    non_null = series.dropna()
    only_dates = non_null.empty or (non_null == non_null.dt.normalize()).all()
    return series.dt.strftime("%Y-%m-%d" if only_dates else "%Y-%m-%d %H:%M:%S")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = make_unique([to_snake_case(c) for c in df.columns])

    for col in df.columns:
        s = df[col]

        if pd.api.types.is_datetime64_any_dtype(s):
            df[col] = _format_datetimes(s)
            continue
        if s.dtype != object and not pd.api.types.is_string_dtype(s):
            continue  # numeric / bool columns are already fine

        s = s.map(lambda v: v.strip() if isinstance(v, str) else v).replace("", np.nan)
        df[col] = s
        non_null = s.dropna()
        if non_null.empty:
            continue
        as_str = non_null.astype(str)

        # numbers stored as text, e.g. "1,200" or "$45"
        if not _ID_HINT.search(col) and not as_str.str.match(r"^0\d").any():
            num = pd.to_numeric(
                s.astype(str).str.replace(_CURRENCY_NOISE, "", regex=True), errors="coerce"
            )
            if num.notna().sum() / len(non_null) >= 0.95:
                df[col] = num
                continue

        # dates stored as text
        if as_str.str.match(_DATE_PATTERN).mean() >= 0.9:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(
                    s, errors="coerce", format="mixed", dayfirst=_infer_dayfirst(non_null)
                )
            if parsed.notna().sum() / len(non_null) >= 0.9:
                df[col] = _format_datetimes(parsed)

    return df.reset_index(drop=True)


def process_tables(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Clean every table and give each a unique, SQL-safe name."""
    out: dict[str, pd.DataFrame] = {}
    for name, df in raw.items():
        table = to_snake_case(name, prefix="table", suffix="_table")
        base, i = table, 2
        while table in out:
            table, i = f"{base}_{i}", i + 1
        cleaned = clean_dataframe(df)
        if not cleaned.empty and cleaned.shape[1] > 0:
            out[table] = cleaned
    return out
