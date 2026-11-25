"""Reads uploaded CSV / TSV / Excel / JSON files into pandas DataFrames."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd

from config.settings import settings


class FileLoadError(Exception):
    """Raised when an uploaded file cannot be turned into tabular data."""


def save_upload(filename: str, data: bytes) -> Path:
    """Keep a copy of the raw upload in uploads/ (sanitised file name)."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", Path(filename).name)
    path = settings.upload_dir / safe
    path.write_bytes(data)
    return path


def _read_csv(data: bytes, sep: str | None) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), sep=sep, engine="python", encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise FileLoadError(f"Could not decode the file: {last_error}")


def load_uploaded_file(filename: str, data: bytes) -> dict[str, pd.DataFrame]:
    """Return {table_name: DataFrame}. Excel files give one table per sheet."""
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise FileLoadError(
            f"'{ext}' files are not supported. Use: {', '.join(settings.allowed_extensions)}"
        )
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise FileLoadError(f"'{filename}' is larger than {settings.max_upload_mb} MB.")

    stem = Path(filename).stem
    frames: dict[str, pd.DataFrame] = {}
    try:
        if ext in (".csv", ".txt"):
            frames[stem] = _read_csv(data, sep=None)  # auto-detect delimiter
        elif ext == ".tsv":
            frames[stem] = _read_csv(data, sep="\t")
        elif ext in (".xlsx", ".xls"):
            sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
            for sheet_name, df in sheets.items():
                key = stem if len(sheets) == 1 else f"{stem}_{sheet_name}"
                frames[key] = df
        elif ext == ".json":
            try:
                frames[stem] = pd.read_json(io.BytesIO(data))
            except ValueError:
                frames[stem] = pd.json_normalize(json.loads(data))
    except FileLoadError:
        raise
    except Exception as exc:  # pandas raises many different error types
        raise FileLoadError(f"Could not read '{filename}': {exc}") from exc

    frames = {k: v for k, v in frames.items() if not v.empty and v.shape[1] > 0}
    if not frames:
        raise FileLoadError(f"'{filename}' does not contain any data.")
    return frames
