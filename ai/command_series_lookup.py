from __future__ import annotations

from typing import Any, Iterator


def normalize_series_key(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if not ch.isspace())


def iter_project_series(project) -> Iterator[tuple[Any, str]]:
    seen_ids = set()
    for dataset in getattr(project, "datasets", []):
        for series in dataset.series:
            if series.id in seen_ids:
                continue
            seen_ids.add(series.id)
            yield series, dataset.name
    for data_file in getattr(project, "data_files", []):
        for series in data_file.series:
            if series.id in seen_ids:
                continue
            seen_ids.add(series.id)
            yield series, data_file.name


def resolve_series(project, series_key: str):
    clean_key = str(series_key or "").strip()
    if not clean_key:
        return None, "缺少系列标识"

    series = project.find_series(clean_key)
    if series is not None:
        return series, None

    exact_matches = []
    normalized_matches = []
    normalized_key = normalize_series_key(clean_key)
    for item, owner_name in iter_project_series(project):
        scoped_name = f"{owner_name} / {item.name}" if owner_name else item.name
        if item.name == clean_key or scoped_name == clean_key:
            exact_matches.append(item)
            continue
        item_name_key = normalize_series_key(item.name)
        scoped_name_key = normalize_series_key(scoped_name)
        if normalized_key in {item_name_key, scoped_name_key}:
            normalized_matches.append(item)

    matches = exact_matches or normalized_matches
    unique_matches = []
    seen_ids = set()
    for item in matches:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        unique_matches.append(item)

    if len(unique_matches) == 1:
        return unique_matches[0], None
    if len(unique_matches) > 1:
        names = "、".join(item.name for item in unique_matches[:5])
        return None, f"系列标识不唯一: {clean_key}，匹配到 {names}"
    return None, f"找不到系列: {clean_key}"
