"""全局资产管理。

为所有项目共享以下资源：
- Pipeline 模板
- 绘图样式
- 报告模板
- 曲线样式模板
- 内置绘图样式预设
- AI Prompt / Skill / Agent
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from core.extension_api import normalize_extension_version
from models.schemas import (
    AIAgent,
    AIPrompt,
    AISkill,
    CurveStyle,
    CurveStyleTemplate,
    FigureConfig,
    FigureState,
    PlotTheme,
    ReportTemplate,
    SavedPipeline,
)
from core.analysis_engine import _DEFAULT_REPORT_TEMPLATE

_GLOBAL_ASSET_VERSION = "1"
_BUILTIN_DEFAULT_REPORT_TEMPLATE_ID = "builtin:default-report-template"
_DEFAULT_EXTENSION_CONFIG_NAME = "默认配置"
_KNOWN_TEST_REPORT_TEMPLATE_SIGNATURES = {
    ("tmpl1", "# Hello"),
    ("tmpl1", "# Template"),
    ("tmpl1", "# Hello {{date}}"),
}


def make_plot_style_asset_key(style_type: str, asset_id: str) -> str:
    return f"{style_type}:{asset_id}"


def parse_plot_style_asset_key(asset_key: str) -> tuple[str, str]:
    if ":" in asset_key:
        style_type, asset_id = asset_key.split(":", 1)
        return style_type, asset_id
    return ("theme", asset_key)


def _default_asset_path() -> Path:
    return Path.home() / ".config" / "aline" / "global_assets.json"


def _builtin_plot_themes() -> List[PlotTheme]:
    return [
        PlotTheme(
            id="builtin:default",
            name="默认",
            description="跟随应用浅色/深色背景，保持较均衡的默认绘图样式。",
            canvas_mode="app",
            state=FigureState(theme="默认", grid=True, grid_alpha=0.55, grid_line_width=0.6,
                              font_size=10, legend_font_size=8, line_width=1.5, marker_size=5.0),
            is_builtin=True,
        ),
        PlotTheme(
            id="builtin:nature",
            name="Nature",
            description="紧凑、克制，适合论文主图。",
            canvas_mode="light",
            grid_color="#d9d9d9",
            foreground_color="#222222",
            background_color="#ffffff",
            state=FigureState(theme="Nature", grid=True, grid_alpha=0.5, grid_line_width=0.5,
                              font_size=9, legend_font_size=8, line_width=1.4, marker_size=4.2),
            is_builtin=True,
        ),
        PlotTheme(
            id="builtin:ieee",
            name="IEEE",
            description="偏工程期刊排版，细字重、较小图幅。",
            canvas_mode="light",
            grid_color="#d0d0d0",
            foreground_color="#111111",
            background_color="#ffffff",
            state=FigureState(theme="IEEE", grid=True, grid_alpha=0.45, grid_line_width=0.45,
                              font_size=8, legend_font_size=7, line_width=1.2, marker_size=3.8),
            is_builtin=True,
        ),
        PlotTheme(
            id="builtin:acs",
            name="ACS",
            description="强调线宽与标记可读性。",
            canvas_mode="light",
            grid_color="#d4d4d4",
            foreground_color="#202020",
            background_color="#ffffff",
            state=FigureState(theme="ACS", grid=True, grid_alpha=0.52, grid_line_width=0.55,
                              font_size=9, legend_font_size=8, line_width=1.8, marker_size=5.2),
            is_builtin=True,
        ),
        PlotTheme(
            id="builtin:bw",
            name="简洁黑白",
            description="黑白输出，适合打印和审稿。",
            canvas_mode="light",
            grid_color="#cfcfcf",
            foreground_color="#000000",
            background_color="#ffffff",
            state=FigureState(theme="简洁黑白", grid=True, grid_alpha=0.45, grid_line_width=0.55,
                              font_size=10, legend_font_size=8, line_width=1.5, marker_size=4.4),
            is_builtin=True,
        ),
    ]


def _builtin_report_templates() -> List[ReportTemplate]:
    return [
        ReportTemplate(
            id=_BUILTIN_DEFAULT_REPORT_TEMPLATE_ID,
            name="默认模板",
            content=_DEFAULT_REPORT_TEMPLATE,
            is_builtin=True,
        )
    ]


def _normalized_report_template_key(template: ReportTemplate) -> tuple[str, str, bool]:
    return (
        (template.name or "").strip(),
        (template.content or "").strip(),
        bool(template.is_builtin),
    )


def _sanitize_report_templates(templates: List[ReportTemplate]) -> tuple[List[ReportTemplate], bool]:
    sanitized: List[ReportTemplate] = []
    seen: set[tuple[str, str, bool]] = set()
    changed = False
    for template in templates:
        name = (template.name or "").strip()
        content = (template.content or "").strip()
        if not template.is_builtin and (name, content) in _KNOWN_TEST_REPORT_TEMPLATE_SIGNATURES:
            changed = True
            continue
        key = _normalized_report_template_key(template)
        if key in seen:
            changed = True
            continue
        seen.add(key)
        sanitized.append(template)
    return sanitized, changed


def _normalize_extension_category(category: str) -> str:
    return str(category or "").strip().lower()


def _normalize_extension_type(extension_type: str) -> str:
    return str(extension_type or "").strip()


def _normalize_extension_config_name(name: str) -> str:
    return str(name or "").strip()


def _extension_config_name_key(name: str) -> str:
    return _normalize_extension_config_name(name).casefold()


class ExtensionConfigPreset(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"extcfg:{uuid.uuid4().hex}")
    category: str
    extension_type: str
    extension_name: str
    extension_version: str = "1.0.0"
    name: str = _DEFAULT_EXTENSION_CONFIG_NAME
    options: Dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class GlobalAssets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str = _GLOBAL_ASSET_VERSION
    saved_pipelines: List[SavedPipeline] = Field(default_factory=list)
    figure_templates: List[FigureConfig] = Field(default_factory=list)
    report_templates: List[ReportTemplate] = Field(default_factory=list)
    curve_style_templates: List[CurveStyleTemplate] = Field(default_factory=list)
    plot_themes: List[PlotTheme] = Field(default_factory=list)
    extension_configs: List[ExtensionConfigPreset] = Field(default_factory=list)
    ai_prompts: List[AIPrompt] = Field(default_factory=list)
    ai_skills: List[AISkill] = Field(default_factory=list)
    ai_agents: List[AIAgent] = Field(default_factory=list)


class GlobalAssetManager:
    def __init__(self, asset_path: Optional[Path] = None) -> None:
        self._asset_path = asset_path or _default_asset_path()
        self._cache: Optional[GlobalAssets] = None

    @property
    def asset_path(self) -> Path:
        return self._asset_path

    def load(self, force: bool = False) -> GlobalAssets:
        if self._cache is not None and not force:
            return self._cache
        if not self._asset_path.exists():
            self._cache = GlobalAssets()
            self.save()
            return self._cache
        with self._asset_path.open("r", encoding="utf-8") as handle:
            self._cache = GlobalAssets(**json.load(handle))
        if self._sanitize_cached_assets():
            self.save()
        return self._cache

    def _sanitize_cached_assets(self) -> bool:
        if self._cache is None:
            return False
        report_templates, changed = _sanitize_report_templates(list(self._cache.report_templates))
        if changed:
            self._cache.report_templates = report_templates
        return changed

    def save(self) -> None:
        assets = self.load()
        self._asset_path.parent.mkdir(parents=True, exist_ok=True)
        with self._asset_path.open("w", encoding="utf-8") as handle:
            json.dump(assets.model_dump(), handle, indent=2, ensure_ascii=False)

    @property
    def data(self) -> GlobalAssets:
        return self.load()

    def _clone(self, item, model_cls):
        return model_cls(**item.model_dump())

    def list_saved_pipelines(self) -> List[SavedPipeline]:
        return list(self.data.saved_pipelines)

    def get_saved_pipeline(self, pipeline_id: str) -> Optional[SavedPipeline]:
        return next((item for item in self.data.saved_pipelines if item.id == pipeline_id), None)

    def add_saved_pipeline(self, pipeline: SavedPipeline) -> SavedPipeline:
        self.data.saved_pipelines.append(pipeline)
        self.save()
        return pipeline

    def ensure_saved_pipeline(self, pipeline: SavedPipeline) -> SavedPipeline:
        item = self.get_saved_pipeline(pipeline.id)
        if item is None:
            item = self._clone(pipeline, SavedPipeline)
            self.data.saved_pipelines.append(item)
        else:
            item.name = pipeline.name
            item.ops = list(pipeline.ops)
            item.description = pipeline.description
        self.save()
        return item

    def update_saved_pipeline(self, pipeline_id: str, *, name: Optional[str] = None,
                              ops: Optional[list[dict]] = None, description: Optional[str] = None) -> bool:
        item = self.get_saved_pipeline(pipeline_id)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if ops is not None:
            item.ops = list(ops)
        if description is not None:
            item.description = description
        self.save()
        return True

    def delete_saved_pipeline(self, pipeline_id: str) -> bool:
        before = len(self.data.saved_pipelines)
        self.data.saved_pipelines = [item for item in self.data.saved_pipelines if item.id != pipeline_id]
        if len(self.data.saved_pipelines) == before:
            return False
        self.save()
        return True

    def list_figure_templates(self) -> List[FigureConfig]:
        return list(self.data.figure_templates)

    def get_figure_template(self, template_id: str) -> Optional[FigureConfig]:
        return next((item for item in self.data.figure_templates if item.id == template_id), None)

    def add_figure_template(self, template: FigureConfig) -> FigureConfig:
        self.data.figure_templates.append(template)
        self.save()
        return template

    def ensure_figure_template(self, template: FigureConfig) -> FigureConfig:
        item = self.get_figure_template(template.id)
        if item is None:
            item = self._clone(template, FigureConfig)
            self.data.figure_templates.append(item)
        else:
            fresh = self._clone(template, FigureConfig)
            for key in FigureConfig.model_fields:
                setattr(item, key, getattr(fresh, key))
        self.save()
        return item

    def update_figure_template(self, template_id: str, *, template: Optional[FigureConfig] = None,
                               name: Optional[str] = None) -> bool:
        item = self.get_figure_template(template_id)
        if item is None:
            return False
        if template is not None:
            fresh = self._clone(template, FigureConfig)
            fresh.id = template_id
            for key in FigureConfig.model_fields:
                setattr(item, key, getattr(fresh, key))
        if name is not None:
            item.name = name
        self.save()
        return True

    def delete_figure_template(self, template_id: str) -> bool:
        before = len(self.data.figure_templates)
        self.data.figure_templates = [item for item in self.data.figure_templates if item.id != template_id]
        if len(self.data.figure_templates) == before:
            return False
        self.save()
        return True

    def list_report_templates(self, include_builtin: bool = False) -> List[ReportTemplate]:
        user_templates = list(self.data.report_templates)
        if not include_builtin:
            return user_templates
        return _builtin_report_templates() + user_templates

    def get_report_template(self, template_id: str) -> Optional[ReportTemplate]:
        return next((item for item in self.list_report_templates(include_builtin=True) if item.id == template_id), None)

    def add_report_template(self, template: ReportTemplate) -> ReportTemplate:
        existing = next(
            (
                item
                for item in self.data.report_templates
                if _normalized_report_template_key(item) == _normalized_report_template_key(template)
            ),
            None,
        )
        if existing is not None:
            return existing
        self.data.report_templates.append(template)
        self.save()
        return template

    def ensure_report_template(self, template: ReportTemplate) -> ReportTemplate:
        item = self.get_report_template(template.id)
        if item is None:
            item = self._clone(template, ReportTemplate)
            self.data.report_templates.append(item)
        else:
            item.name = template.name
            item.content = template.content
            item.is_builtin = template.is_builtin
        self.save()
        return item

    def update_report_template(self, template_id: str, *, name: Optional[str] = None,
                               content: Optional[str] = None) -> bool:
        item = self.get_report_template(template_id)
        if item is None or item.is_builtin:
            return False
        if name is not None:
            item.name = name
        if content is not None:
            item.content = content
        self.save()
        return True

    def delete_report_template(self, template_id: str) -> bool:
        item = self.get_report_template(template_id)
        if item is None or item.is_builtin:
            return False
        self.data.report_templates = [template for template in self.data.report_templates if template.id != template_id]
        self.save()
        return True

    def list_curve_style_templates(self) -> List[CurveStyleTemplate]:
        return list(self.data.curve_style_templates)

    def get_curve_style_template(self, template_id: str) -> Optional[CurveStyleTemplate]:
        return next((item for item in self.data.curve_style_templates if item.id == template_id), None)

    def add_curve_style_template(self, template: CurveStyleTemplate) -> CurveStyleTemplate:
        self.data.curve_style_templates.append(template)
        self.save()
        return template

    def update_curve_style_template(self, template_id: str, *, name: Optional[str] = None,
                                    description: Optional[str] = None,
                                    style: Optional[CurveStyle] = None) -> bool:
        item = self.get_curve_style_template(template_id)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if description is not None:
            item.description = description
        if style is not None:
            item.style = style
        self.save()
        return True

    def delete_curve_style_template(self, template_id: str) -> bool:
        before = len(self.data.curve_style_templates)
        self.data.curve_style_templates = [
            item for item in self.data.curve_style_templates if item.id != template_id or item.is_builtin
        ]
        if len(self.data.curve_style_templates) == before:
            return False
        self.save()
        return True

    def list_plot_themes(self, include_builtin: bool = True) -> List[PlotTheme]:
        user_themes = list(self.data.plot_themes)
        if not include_builtin:
            return user_themes
        return _builtin_plot_themes() + user_themes

    def list_extension_configs(
        self,
        *,
        category: Optional[str] = None,
        extension_type: Optional[str] = None,
        include_defaults: bool = True,
    ) -> List[ExtensionConfigPreset]:
        normalized_category = _normalize_extension_category(category) if category else None
        normalized_type = _normalize_extension_type(extension_type) if extension_type else None
        items = list(self.data.extension_configs)
        if normalized_category is not None:
            items = [item for item in items if _normalize_extension_category(item.category) == normalized_category]
        if normalized_type is not None:
            items = [item for item in items if _normalize_extension_type(item.extension_type) == normalized_type]
        if not include_defaults:
            items = [item for item in items if not item.is_default]
        return items

    def get_extension_config(self, config_id: str) -> Optional[ExtensionConfigPreset]:
        return next((item for item in self.data.extension_configs if item.id == config_id), None)

    def get_extension_default_config(self, category: str, extension_type: str) -> Optional[ExtensionConfigPreset]:
        normalized_category = _normalize_extension_category(category)
        normalized_type = _normalize_extension_type(extension_type)
        return next(
            (
                item
                for item in self.data.extension_configs
                if _normalize_extension_category(item.category) == normalized_category
                and _normalize_extension_type(item.extension_type) == normalized_type
                and item.is_default
            ),
            None,
        )

    def get_extension_config_by_name(self, category: str, extension_type: str, name: str) -> Optional[ExtensionConfigPreset]:
        normalized_category = _normalize_extension_category(category)
        normalized_type = _normalize_extension_type(extension_type)
        normalized_name = _extension_config_name_key(name)
        return next(
            (
                item
                for item in self.data.extension_configs
                if _normalize_extension_category(item.category) == normalized_category
                and _normalize_extension_type(item.extension_type) == normalized_type
                and _extension_config_name_key(item.name) == normalized_name
            ),
            None,
        )

    def ensure_extension_default_config(
        self,
        category: str,
        extension_type: str,
        extension_name: str,
        options: Optional[Dict[str, Any]] = None,
        extension_version: Optional[str] = None,
    ) -> ExtensionConfigPreset:
        normalized_category = _normalize_extension_category(category)
        normalized_type = _normalize_extension_type(extension_type)
        clean_extension_name = _normalize_extension_config_name(extension_name) or normalized_type
        clean_options = dict(options or {})
        clean_version = normalize_extension_version(extension_version)

        for item in self.data.extension_configs:
            if _normalize_extension_category(item.category) == normalized_category and _normalize_extension_type(item.extension_type) == normalized_type:
                item.extension_name = clean_extension_name

        existing = self.get_extension_default_config(normalized_category, normalized_type)
        if existing is None:
            existing = ExtensionConfigPreset(
                category=normalized_category,
                extension_type=normalized_type,
                extension_name=clean_extension_name,
                extension_version=clean_version,
                name=_DEFAULT_EXTENSION_CONFIG_NAME,
                options=clean_options,
                is_default=True,
            )
            self.data.extension_configs.append(existing)
            self.save()
            return existing

        changed = False
        if existing.extension_name != clean_extension_name:
            existing.extension_name = clean_extension_name
            changed = True
        if existing.extension_version != clean_version:
            existing.extension_version = clean_version
            changed = True
        if existing.name != _DEFAULT_EXTENSION_CONFIG_NAME:
            existing.name = _DEFAULT_EXTENSION_CONFIG_NAME
            changed = True
        if dict(existing.options or {}) != clean_options:
            existing.options = clean_options
            changed = True
        if not existing.is_default:
            existing.is_default = True
            changed = True
        if changed:
            self.save()
        return existing

    def add_extension_config(
        self,
        *,
        category: str,
        extension_type: str,
        extension_name: str,
        extension_version: Optional[str] = None,
        name: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> ExtensionConfigPreset:
        normalized_category = _normalize_extension_category(category)
        normalized_type = _normalize_extension_type(extension_type)
        clean_name = _normalize_extension_config_name(name)
        clean_version = normalize_extension_version(extension_version)
        if not normalized_category or not normalized_type or not clean_name:
            raise ValueError("扩展配置保存信息不完整")
        if self.get_extension_config_by_name(normalized_category, normalized_type, clean_name) is not None:
            raise ValueError("同一扩展下已存在同名配置")
        item = ExtensionConfigPreset(
            category=normalized_category,
            extension_type=normalized_type,
            extension_name=_normalize_extension_config_name(extension_name) or normalized_type,
            extension_version=clean_version,
            name=clean_name,
            options=dict(options or {}),
            is_default=False,
        )
        self.data.extension_configs.append(item)
        self.save()
        return item

    def update_extension_config(
        self,
        config_id: str,
        *,
        name: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        extension_version: Optional[str] = None,
    ) -> Optional[ExtensionConfigPreset]:
        item = self.get_extension_config(config_id)
        if item is None:
            return None
        if item.is_default and name is not None:
            return None
        changed = False
        if name is not None:
            clean_name = _normalize_extension_config_name(name)
            if not clean_name:
                return None
            duplicate = self.get_extension_config_by_name(item.category, item.extension_type, clean_name)
            if duplicate is not None and duplicate.id != item.id:
                raise ValueError("同一扩展下已存在同名配置")
            if item.name != clean_name:
                item.name = clean_name
                changed = True
        if options is not None and dict(item.options or {}) != dict(options):
            item.options = dict(options)
            changed = True
        if extension_version is not None:
            clean_version = normalize_extension_version(extension_version)
            if item.extension_version != clean_version:
                item.extension_version = clean_version
                changed = True
        if changed:
            self.save()
        return item

    def delete_extension_config(self, config_id: str) -> bool:
        target = self.get_extension_config(config_id)
        if target is None or target.is_default:
            return False
        before = len(self.data.extension_configs)
        self.data.extension_configs = [item for item in self.data.extension_configs if item.id != config_id]
        if len(self.data.extension_configs) == before:
            return False
        self.save()
        return True

    def get_plot_theme(self, theme_key: str) -> Optional[PlotTheme]:
        for item in self.list_plot_themes(include_builtin=True):
            if item.id == theme_key or item.name == theme_key:
                return item
        return None

    def add_plot_theme(self, theme: PlotTheme) -> PlotTheme:
        self.data.plot_themes.append(theme)
        self.save()
        return theme

    def update_plot_theme(self, theme_id: str, *, name: Optional[str] = None,
                          description: Optional[str] = None,
                          canvas_mode: Optional[str] = None,
                          grid_color: Optional[str] = None,
                          foreground_color: Optional[str] = None,
                          background_color: Optional[str] = None,
                          state: Optional[FigureState] = None) -> bool:
        item = next((theme for theme in self.data.plot_themes if theme.id == theme_id), None)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if description is not None:
            item.description = description
        if canvas_mode is not None:
            item.canvas_mode = canvas_mode
        if grid_color is not None:
            item.grid_color = grid_color
        if foreground_color is not None:
            item.foreground_color = foreground_color
        if background_color is not None:
            item.background_color = background_color
        if state is not None:
            item.state = state
        self.save()
        return True

    def delete_plot_theme(self, theme_id: str) -> bool:
        before = len(self.data.plot_themes)
        self.data.plot_themes = [item for item in self.data.plot_themes if item.id != theme_id]
        if len(self.data.plot_themes) == before:
            return False
        self.save()
        return True

    def list_ai_prompts(self) -> List[AIPrompt]:
        return list(self.data.ai_prompts)

    def get_ai_prompt(self, prompt_id: str) -> Optional[AIPrompt]:
        return next((item for item in self.data.ai_prompts if item.id == prompt_id), None)

    def add_ai_prompt(self, name: str, content: str = "", description: str = "") -> AIPrompt:
        item = AIPrompt(name=name, content=content, description=description)
        self.data.ai_prompts.append(item)
        self.save()
        return item

    def ensure_ai_prompt(self, prompt: AIPrompt) -> AIPrompt:
        item = self.get_ai_prompt(prompt.id)
        if item is None:
            item = self._clone(prompt, AIPrompt)
            self.data.ai_prompts.append(item)
        else:
            item.name = prompt.name
            item.content = prompt.content
            item.description = prompt.description
        self.save()
        return item

    def update_ai_prompt(self, prompt_id: str, *, name: Optional[str] = None,
                         content: Optional[str] = None,
                         description: Optional[str] = None) -> bool:
        item = self.get_ai_prompt(prompt_id)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if content is not None:
            item.content = content
        if description is not None:
            item.description = description
        self.save()
        return True

    def delete_ai_prompt(self, prompt_id: str) -> bool:
        before = len(self.data.ai_prompts)
        self.data.ai_prompts = [item for item in self.data.ai_prompts if item.id != prompt_id]
        if len(self.data.ai_prompts) == before:
            return False
        self.save()
        return True

    def list_ai_skills(self) -> List[AISkill]:
        return list(self.data.ai_skills)

    def get_ai_skill(self, skill_id: str) -> Optional[AISkill]:
        return next((item for item in self.data.ai_skills if item.id == skill_id), None)

    def add_ai_skill(self, name: str, code: str = "", description: str = "") -> AISkill:
        item = AISkill(name=name, code=code, description=description)
        self.data.ai_skills.append(item)
        self.save()
        return item

    def ensure_ai_skill(self, skill: AISkill) -> AISkill:
        item = self.get_ai_skill(skill.id)
        if item is None:
            item = self._clone(skill, AISkill)
            self.data.ai_skills.append(item)
        else:
            item.name = skill.name
            item.code = skill.code
            item.description = skill.description
        self.save()
        return item

    def update_ai_skill(self, skill_id: str, *, name: Optional[str] = None,
                        code: Optional[str] = None,
                        description: Optional[str] = None) -> bool:
        item = self.get_ai_skill(skill_id)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if code is not None:
            item.code = code
        if description is not None:
            item.description = description
        self.save()
        return True

    def delete_ai_skill(self, skill_id: str) -> bool:
        before = len(self.data.ai_skills)
        self.data.ai_skills = [item for item in self.data.ai_skills if item.id != skill_id]
        if len(self.data.ai_skills) == before:
            return False
        self.save()
        return True

    def list_ai_agents(self) -> List[AIAgent]:
        return list(self.data.ai_agents)

    def get_ai_agent(self, agent_id: str) -> Optional[AIAgent]:
        return next((item for item in self.data.ai_agents if item.id == agent_id), None)

    def add_ai_agent(self, name: str, system_prompt: str = "", description: str = "") -> AIAgent:
        item = AIAgent(name=name, system_prompt=system_prompt, description=description)
        self.data.ai_agents.append(item)
        self.save()
        return item

    def ensure_ai_agent(self, agent: AIAgent) -> AIAgent:
        item = self.get_ai_agent(agent.id)
        if item is None:
            item = self._clone(agent, AIAgent)
            self.data.ai_agents.append(item)
        else:
            item.name = agent.name
            item.system_prompt = agent.system_prompt
            item.description = agent.description
        self.save()
        return item

    def update_ai_agent(self, agent_id: str, *, name: Optional[str] = None,
                        system_prompt: Optional[str] = None,
                        description: Optional[str] = None) -> bool:
        item = self.get_ai_agent(agent_id)
        if item is None:
            return False
        if name is not None:
            item.name = name
        if system_prompt is not None:
            item.system_prompt = system_prompt
        if description is not None:
            item.description = description
        self.save()
        return True

    def delete_ai_agent(self, agent_id: str) -> bool:
        before = len(self.data.ai_agents)
        self.data.ai_agents = [item for item in self.data.ai_agents if item.id != agent_id]
        if len(self.data.ai_agents) == before:
            return False
        self.save()
        return True


global_assets = GlobalAssetManager()