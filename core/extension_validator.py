from __future__ import annotations

from typing import Any, List, Optional

from core.extension_definition import (
    _EXTENSION_SOURCE_KINDS,
    AnalysisExtension,
    DigitizeExtension,
    PlotExtension,
    ProcessingExtension,
    normalize_extension_lines_number,
    normalize_extension_source_kind,
    normalize_extension_version,
)


class ExtensionValidator:
    """扩展校验器 — 对注册的扩展做完整性、兼容性和参数校验。"""

    @staticmethod
    def validate_extension(ext: Any) -> List[str]:
        """对单个扩展做完整校验，返回错误列表（空 = 通过）。"""
        errors: List[str] = []

        # 1. 基础字段
        if not getattr(ext, "type", None):
            errors.append("扩展缺少 type")
        if not getattr(ext, "name", None):
            errors.append("扩展缺少 name")
        if not callable(getattr(ext, "handler", None)):
            errors.append("扩展 handler 不可调用")

        # 2. 版本
        version = getattr(ext, "version", None)
        if version:
            try:
                normalize_extension_version(version)
            except ValueError as e:
                errors.append(f"版本格式错误: {e}")

        # 3. source_kind
        source_kind = getattr(ext, "source_kind", None)
        if source_kind:
            clean = str(source_kind).strip().lower()
            if clean and clean not in _EXTENSION_SOURCE_KINDS:
                errors.append(f"source_kind 无效: {source_kind}")
        else:
            # Still normalize to ensure no hidden issues
            try:
                normalize_extension_source_kind(source_kind)
            except ValueError as e:
                errors.append(f"source_kind 无效: {e}")

        # 4. lines_number（处理/分析/绘图扩展）
        if hasattr(ext, "lines_number") and getattr(ext, "lines_number", None) is not None:
            try:
                normalize_extension_lines_number(getattr(ext, "lines_number"))
            except ValueError as e:
                errors.append(f"lines_number 无效: {e}")

        # 5. config_fields
        config_fields = getattr(ext, "config_fields", None) or []
        for i, field in enumerate(config_fields):
            if not getattr(field, "key", None):
                errors.append(f"config_fields[{i}] 缺少 key")
            if not getattr(field, "label", None):
                errors.append(f"config_fields[{i}] 缺少 label")

        depends_on = getattr(ext, "depends_on", None) or []
        for i, item in enumerate(depends_on):
            if not str(item).strip():
                errors.append(f"depends_on[{i}] 不能为空")

        return errors

    @staticmethod
    def check_api_compatibility(aline_api_version: str, aline_version: str) -> str:
        """检查扩展声明的 API 版本是否兼容当前 ALine 版本。

        Args:
            aline_api_version: 扩展声明的版本要求 (e.g. ">=0.3", ">=0.3,<0.5", "0.3", "")
            aline_version: 当前 ALine 版本 (e.g. "0.3.0")

        Returns:
            "compatible" | "warning" | "incompatible"
        """
        if not aline_api_version:
            return "compatible"

        try:
            current = tuple(int(x) for x in aline_version.split("."))

            # 处理逗号分隔的多条件 (e.g. ">=0.3,<0.5")
            parts = aline_api_version.split(",")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if part.startswith(">="):
                    req = tuple(int(x) for x in part[2:].strip().split("."))
                    if current < req:
                        return "incompatible"
                elif part.startswith("<="):
                    req = tuple(int(x) for x in part[2:].strip().split("."))
                    if current > req:
                        return "incompatible"
                elif part.startswith("<"):
                    req = tuple(int(x) for x in part[1:].strip().split("."))
                    if current >= req:
                        return "incompatible"
                elif part.startswith(">"):
                    req = tuple(int(x) for x in part[1:].strip().split("."))
                    if current <= req:
                        return "incompatible"
                elif part.startswith("=="):
                    req = tuple(int(x) for x in part[2:].strip().split("."))
                    if current != req:
                        return "incompatible"
                # 精确版本号: 前缀匹配 (e.g. "0.3" 兼容 "0.3.0", "0.3.1" 等)
                elif len(parts) == 1 and not any(p.startswith((">=", "<=", "<", ">", "==")) for p in parts):
                    exact = tuple(int(x) for x in part.split("."))
                    if current[:len(exact)] != exact:
                        return "incompatible"
                else:
                    # 无法识别的版本声明
                    return "warning"

        except (ValueError, IndexError):
            return "warning"

        return "compatible"

    @staticmethod
    def check_compatibility(arg1: Any, arg2: str) -> Any:
        if isinstance(arg1, str):
            return ExtensionValidator.check_api_compatibility(arg1, arg2)
        ext = arg1
        aline_version = arg2
        api_version = getattr(ext, "aline_api_version", None) or getattr(ext, "api_version", None)
        if not api_version:
            return []
        warnings: List[str] = []
        try:
            current = tuple(int(x) for x in aline_version.split("."))
            required = tuple(int(x) for x in api_version.lstrip(">=").split("."))
            if api_version.startswith(">=") and current < required:
                warnings.append(f"需要 ALine {api_version}，当前版本 {aline_version}")
            elif api_version.startswith("<") and current >= required:
                warnings.append(f"不支持 ALine {api_version} 以上版本")
        except (ValueError, TypeError, AttributeError):
            warnings.append(f"无法解析版本要求: {api_version}")
        return warnings

    @staticmethod
    def validate_param_value(key: str, value: Any, field_def: Any) -> Optional[str]:
        """校验单个参数值是否符合字段定义。

        Returns:
            None 表示通过；否则返回错误描述字符串。
        """
        field_type = getattr(field_def, "field_type", "string")

        if field_type == "integer":
            if not isinstance(value, int):
                return f"{key} 应为整数"
            min_v = getattr(field_def, "min_value", None)
            max_v = getattr(field_def, "max_value", None)
            if min_v is not None and value < min_v:
                return f"{key} 不能小于 {min_v}"
            if max_v is not None and value > max_v:
                return f"{key} 不能大于 {max_v}"

        elif field_type == "number":
            try:
                val = float(value)
            except (TypeError, ValueError):
                return f"{key} 应为数值"
            min_v = getattr(field_def, "min_value", None)
            max_v = getattr(field_def, "max_value", None)
            if min_v is not None and val < min_v:
                return f"{key} 不能小于 {min_v}"
            if max_v is not None and val > max_v:
                return f"{key} 不能大于 {max_v}"

        elif field_type == "selective":
            choices = getattr(field_def, "choices", [])
            if choices and value not in choices:
                return f"{key} 的值不在可选范围内"

        elif field_type == "boolean":
            if not isinstance(value, bool):
                return f"{key} 应为布尔值"

        return None


def _validate_extension_contract(category: str, extension: Any) -> None:
    from core.extension_definition import (
        DEFAULT_EXTENSION_VERSION,
        extension_config_fields,
        extension_lines_number,
        normalize_extension_tool_tier,
        validate_extension_lines_list,
    )
    from core.extension_types import normalize_plot_extension_phases

    normalize_extension_version(
        getattr(extension, "version", DEFAULT_EXTENSION_VERSION)
    )
    normalize_extension_tool_tier(getattr(extension, "tool_tier", "tool"))
    if not isinstance(getattr(extension, "settings", False), bool):
        raise ValueError("settings 必须是布尔值")
    if category == "plot":
        normalize_plot_extension_phases(getattr(extension, "phases", None))
    lines_number = (
        extension_lines_number(extension)
        if category in {"processing", "analysis", "plot"}
        else None
    )
    extension_config_fields(extension, include_implicit_lines=False)
    legacy_defaults = dict(getattr(extension, "default_options", {}) or {})
    if category in {"processing", "analysis", "plot"}:
        if "lines_number" in legacy_defaults:
            raise ValueError(
                "lines_number 已改为扩展注册参数，不能放在 default_options 中"
            )
        if "lines" in legacy_defaults:
            raise ValueError(
                "lines 内嵌协议已废弃，请改用扩展注册参数 lines_number 与顶层 lines_list"
            )
        if "lines_list" in legacy_defaults:
            validate_extension_lines_list(
                legacy_defaults.get("lines_list"), lines_number, present=True
            )
        elif lines_number is not None:
            validate_extension_lines_list([], lines_number, present=False)
    if category == "analysis":
        for item in list(
            getattr(extension, "report_placeholders", []) or []
        ):
            if not isinstance(item, dict):
                raise ValueError(
                    "report_placeholders 必须使用包含 token / label / description 的字典列表"
                )
            token = str(item.get("token") or "").strip()
            label = str(item.get("label") or "").strip()
            description = str(item.get("description") or "").strip()
            if not token.startswith("{{") or not token.endswith("}}"):
                raise ValueError(
                    "report_placeholders.token 必须使用 {{token}} 形式"
                )
            if not label or not description:
                raise ValueError(
                    "report_placeholders 必须显式提供 label 与 description"
                )
