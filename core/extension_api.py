"""扩展 API 兼容重导出层。新代码请直接引用对应模块。"""
from core.extension_definition import *  # noqa: F401, F403
from core.extension_definition import (  # noqa: F401
    _EXTENSION_CATEGORY_LABELS,
    _EXTENSION_SOURCE_LABELS,
)

from core.extension_loader import (  # noqa: F401
    LoadReport, ensure_configured_extensions_loaded,
    format_extension_load_report, get_extension_load_status,
    get_last_extension_load_details, get_last_extension_load_report,
    load_builtin_extensions, load_configured_extensions,
    reload_builtin_extensions, reload_extensions, scan_directory,
)
reload_configured_extensions = reload_extensions

from core.extension_registry import (  # noqa: F401
    ExtensionRegistry, builtin_extension_files,
    configured_builtin_extension_files, configured_external_extension_files,
    configured_extension_directories, default_extensions_directory,
    extension_registry, external_extension_files,
    list_builtin_extension_specs, list_external_extension_specs,
)

from core.extension_runtime import (  # noqa: F401
    invoke_analysis_extension_handler, invoke_digitize_extension_handler,
    invoke_plot_extension_handler, invoke_processing_extension_handler,
)

from core.extension_types import (  # noqa: F401
    PlotExtensionContext, merge_nested_dict, normalize_plot_extension_phases,
)

from core.extension_validator import ExtensionValidator  # noqa: F401

from core.extension_registry import extension_registry as _reg

def register_processing_extension(extension): _reg.register_processing(extension)
def register_analysis_extension(extension): _reg.register_analysis(extension)
def register_plot_extension(extension): _reg.register_plot(extension)
def register_digitize_extension(extension): _reg.register_digitize(extension)

__all__ = [
    "AnalysisExtension", "CurveStyleExtension", "DigitizeExtension",
    "ExtensionConfigField", "ExtensionRegistry", "ExtensionValidator", "LoadReport",
    "PlotExtension", "PlotExtensionContext", "PlotStyleExtension",
    "ProcessingExtension",
    "build_extension_entry",
    "builtin_extension_files",
    "configured_builtin_extension_files",
    "configured_external_extension_files",
    "configured_extension_directories",
    "default_extensions_directory",
    "ensure_configured_extensions_loaded",
    "extension_entry_display_info",
    "extension_entry_parameter_help_text",
    "extension_lines_number",
    "extension_lines_picker_visible",
    "extension_lines_support_text",
    "extension_registry",
    "extension_resolved_default_options",
    "external_extension_files",
    "format_extension_load_report",
    "get_extension_load_status",
    "get_last_extension_load_details",
    "get_last_extension_load_report",
    "invoke_analysis_extension_handler",
    "invoke_digitize_extension_handler",
    "invoke_plot_extension_handler",
    "invoke_processing_extension_handler",
    "list_builtin_extension_specs",
    "list_external_extension_specs",
    "load_builtin_extensions",
    "load_configured_extensions",
    "merge_nested_dict",
    "normalize_extension_field_type",
    "normalize_extension_lines_config",
    "normalize_extension_lines_list",
    "normalize_extension_lines_number",
    "normalize_extension_source_kind",
    "normalize_extension_tool_tier",
    "normalize_extension_version",
    "normalize_plot_extension_phases",
    "register_analysis_extension",
    "register_digitize_extension",
    "register_plot_extension",
    "register_processing_extension",
    "reload_builtin_extensions",
    "reload_configured_extensions",
    "reload_extensions",
    "scan_directory",
    "validate_extension_lines_list",
]
