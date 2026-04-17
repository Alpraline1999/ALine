"""
统一数据模型 — ALine + PyLine 兼容

兼容策略：
- PyLine 原有模型（CalibrationData / Curve / MaskData / ImageWork）完全保留，字段不变
- ALine 新增字段全部带默认值，Pydantic 加载旧 .pyline 文件不会报错
- v0.2 新增：ProjectTree（树形结构）、DataFile、SavedPipeline、ReportTemplate、AI* 模型
- v0.3 新增：FolderNode.group_type、AIPromptNode/AISkillNode/AIAgentNode 拆分、FigureConfig 完整字段
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────
# PyLine 原有模型（保持原样，不做任何修改）
# ─────────────────────────────────────────────────────────────

class CalibrationData(BaseModel):
    """像素坐标 → 真实坐标的校准参数。

    线性/对数坐标系 (coord_type="linear" | "log"):
        x_start/x_end: X 轴两端像素坐标
        y_start/y_end: Y 轴两端像素坐标
        x_range/y_range: 对应的真实数值范围

    极坐标系 (coord_type="polar"):
        x_start: 极点像素坐标
        x_end:   参考点A像素坐标
        angle_A: 参考点A的真实角度（度）
        radius_A: 参考点A的真实极径
    """
    x_start: Tuple[float, float] = (0.0, 0.0)
    x_end: Tuple[float, float] = (1.0, 0.0)
    y_start: Tuple[float, float] = (0.0, 0.0)
    y_end: Tuple[float, float] = (0.0, 1.0)
    x_range: Tuple[float, float] = (0.0, 1.0)
    y_range: Tuple[float, float] = (0.0, 1.0)
    coord_type: str = "linear"
    angle_A: float = 0.0
    radius_A: float = 1.0


class Curve(BaseModel):
    """一条数字化曲线（含像素坐标 + 校准后真实坐标）。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    x_data: List[float] = []
    y_data: List[float] = []
    x_actual: List[float] = []
    y_actual: List[float] = []
    color: str = "#0078D4"
    point_shape: str = "circle"
    source_image_id: Optional[str] = None
    calibration: Optional[CalibrationData] = None


class MaskData(BaseModel):
    """图像遮罩（多边形区域）。"""
    include_mode: bool = False
    polygons: List[List[Tuple[int, int]]] = []


class ImageWork(BaseModel):
    """一张待数字化的图像及其提取曲线。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    image_path: str = ""
    source_image_path: Optional[str] = None
    curves: List[Curve] = []
    mask: Optional[MaskData] = None


# ─────────────────────────────────────────────────────────────
# ALine 新增模型
# ─────────────────────────────────────────────────────────────

class DataSeries(BaseModel):
    """ALine 独立数据系列（区别于从图像提取的 Curve，直接存储数值）。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    x: List[float] = []
    y: List[float] = []
    y_err: Optional[List[float]] = None     # 误差棒
    x_label: str = "x"
    y_label: str = "y"
    color: str = "#0078D4"
    visible: bool = True
    source: str = "manual"
    # "manual" | "imported_file" | "computed" | "pyline_curve_copy"
    source_curve_id: Optional[str] = None  # 来源于 PyLine Curve 时记录原始 id


class Dataset(BaseModel):
    """ALine 数据集（多个 DataSeries 的容器）。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    series: List[DataSeries] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


class AnalysisResult(BaseModel):
    """一次分析任务的完整结果。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    analysis_type: str = ""
    # "curve_fit" | "peak_detect" | "statistics" | "correlation"
    input_series_ids: List[str] = []
    params: Dict[str, Any] = {}
    result_series_id: Optional[str] = None  # 计算结果曲线 → DataSeries.id
    summary: Dict[str, Any] = {}            # 拟合参数、R²、峰值列表等
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ─────────────────────────────────────────────────────────────
# v0.3 FigureConfig 完整字段
# ─────────────────────────────────────────────────────────────

class AxisConfig(BaseModel):
    """坐标轴配置。"""
    model_config = ConfigDict(extra="ignore")

    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    x_label: str = "X"
    y_label: str = "Y"
    x_log: bool = False
    y_log: bool = False
    secondary_y: bool = False          # 是否启用双 Y 轴
    secondary_y_label: str = "Y2"


class SeriesRef(BaseModel):
    """图表中一条曲线的引用及样式。"""
    model_config = ConfigDict(extra="ignore")

    series_id: Optional[str] = None    # DataSeries.id 或 Curve.id
    series_name: Optional[str] = None  # 显示名称
    color: Optional[str] = None
    linestyle: str = "-"
    marker: str = ""
    linewidth: float = 1.5
    alpha: float = 1.0
    label: Optional[str] = None
    use_secondary_y: bool = False      # 是否使用右 Y 轴


class FigureConfig(BaseModel):
    """可视化页的图表配置（可保存多套布局）。"""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    # v0.2 字段（保留向后兼容）
    series_refs: List[Any] = []        # 兼容旧 dict 格式；v0.3 推荐用 typed_series_refs
    axis_config: Any = {}              # 兼容旧 dict 格式；v0.3 推荐用 typed_axis_config
    legend_config: Dict[str, Any] = {}
    theme: str = "default"
    # v0.3 新增
    typed_series_refs: List[SeriesRef] = []
    typed_axis_config: AxisConfig = Field(default_factory=AxisConfig)
    figure_size: Tuple[float, float] = (7.0, 5.0)   # 英寸
    dpi: int = 150
    font_size: int = 10
    font_family: str = ""
    legend_font_size: int = 8
    show_errbar: bool = False
    grid: bool = True
    grid_alpha: float = 0.7
    grid_line_width: float = 0.5
    line_width: float = 1.4
    marker_size: float = 5.0
    legend_position: str = "best"      # matplotlib loc 字符串


class FigureState(BaseModel):
    """图表页运行时唯一状态源。"""
    model_config = ConfigDict(extra="ignore")

    theme: str = "默认"
    x_label: str = "X"
    y_label: str = "Y"
    figure_width: float = 7.0
    figure_height: float = 5.0
    dpi: int = 150
    show_errbar: bool = False
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    x_log: bool = False
    y_log: bool = False
    grid: bool = True
    grid_alpha: float = 0.7
    grid_line_width: float = 0.5
    legend_pos: str = "best"
    font_size: int = 10
    font_family: str = ""
    legend_font_size: int = 8
    line_width: float = 1.4
    marker_size: float = 5.0


# ─────────────────────────────────────────────────────────────
# Project 根节点（同时兼容 .pyline 格式）
# ─────────────────────────────────────────────────────────────

class Project(BaseModel):
    """项目根节点。

    兼容性保证：
    - PyLine 旧字段（images / imported_curves）全部保留
    - ALine 新字段（datasets / analyses / figures）全部带默认值
    - Pydantic 加载旧 .pyline 文件时新字段取默认值，不崩溃
    - `aline_version` 为 None 时表示纯 PyLine 项目
    """
    # ── PyLine 字段（保持原样）─────────────────────
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    images: List[ImageWork] = []
    imported_curves: List[Curve] = []
    created_at: str = ""
    updated_at: str = ""
    file_path: Optional[str] = None     # 运行时字段，序列化时排除
    is_modified: bool = False           # 运行时脏标记，序列化时排除

    # ── ALine 新增字段 ─────────────────────────────
    datasets: List[Dataset] = []
    analyses: List[AnalysisResult] = []
    figures: List[FigureConfig] = []
    aline_version: Optional[str] = None

    # ── v0.2 新增字段（全部带默认值，旧文件打开不报错）──
    data_files: List["DataFile"] = []
    saved_pipelines: List["SavedPipeline"] = []
    report_templates: List["ReportTemplate"] = []
    ai_prompts: List["AIPrompt"] = []
    ai_skills: List["AISkill"] = []
    ai_agents: List["AIAgent"] = []
    tree: Optional["ProjectTree"] = None  # None = 旧文件，migrate_to_v2 时自动构建

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def create_new(cls, name: str) -> "Project":
        now = datetime.now().isoformat()
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=now,
            updated_at=now,
            aline_version="0.3",
        )

    def is_aline_project(self) -> bool:
        return self.aline_version is not None

    # ── 便捷查找方法 ───────────────────────────────

    def find_dataset(self, dataset_id: str) -> Optional[Dataset]:
        for ds in self.datasets:
            if ds.id == dataset_id:
                return ds
        return None

    def find_series(self, series_id: str) -> Optional[DataSeries]:
        """在所有 Dataset 和 DataFile 中查找 DataSeries。"""
        for ds in self.datasets:
            for s in ds.series:
                if s.id == series_id:
                    return s
        for df in getattr(self, "data_files", []):
            s = df.find_series(series_id)
            if s:
                return s
        return None

    def find_analysis(self, analysis_id: str) -> Optional[AnalysisResult]:
        for a in self.analyses:
            if a.id == analysis_id:
                return a
        return None

    def iter_all_series(self):
        """遍历项目中所有 DataSeries（跨 Dataset）。"""
        for ds in self.datasets:
            yield from ds.series

    def iter_all_curves(self):
        """遍历项目中所有图像提取曲线（images[*].curves）。"""
        for img in self.images:
            yield from img.curves

    def find_data_file(self, df_id: str) -> Optional["DataFile"]:
        for df in self.data_files:
            if df.id == df_id:
                return df
        return None

    def find_saved_pipeline(self, pipeline_id: str) -> Optional["SavedPipeline"]:
        for sp in self.saved_pipelines:
            if sp.id == pipeline_id:
                return sp
        return None

    def find_figure(self, figure_id: str) -> Optional[FigureConfig]:
        for f in self.figures:
            if f.id == figure_id:
                return f
        return None

    def find_report_template(self, template_id: str) -> Optional["ReportTemplate"]:
        for t in self.report_templates:
            if t.id == template_id:
                return t
        return None


# ─────────────────────────────────────────────────────────────
# v0.3 树节点模型（Pydantic v2 Discriminated Union）
# ─────────────────────────────────────────────────────────────

class _NodeBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    parent_id: Optional[str] = None   # None = 挂在项目根下
    order: int = 0                    # 同层排序


# group_type 语义：
#   None / "user"            = 用户创建的普通文件夹
#   "datasets"/"dataset_set" = 系统数据集容器（兼容旧值）
#   "images"/"image_set"    = 系统图片集容器（兼容旧值）
#   "tools"/"tool_set"      = 系统工具集容器（兼容旧值）
#   "pipeline_group"         = 工具集内 Pipelines 子文件夹
#   "template_group"         = 旧版绘图模板组（兼容）
#   "figure_template_group"  = 绘图模板组
#   "report_template_group"  = 报告模板组
#   "ai_group"               = AI 工具总分组
#   "prompt_group"           = Prompts 子分组
#   "skill_group"            = Skills 子分组
#   "agent_group"            = Agents 子分组
_GROUP_TYPE = Literal[
    "user",
    "datasets", "images", "tools",
    "dataset_set", "image_set", "tool_set",
    "pipeline_group",
    "template_group", "figure_template_group", "report_template_group",
    "ai_group", "prompt_group", "skill_group", "agent_group"
]


class FolderNode(_NodeBase):
    kind: Literal["folder"] = "folder"
    group_type: Optional[_GROUP_TYPE] = None  # None 向后兼容 v0.2


class DataFileNode(_NodeBase):
    kind: Literal["data_file"] = "data_file"
    data_file_id: str = ""


class ImageWorkNode(_NodeBase):
    kind: Literal["image_work"] = "image_work"
    image_work_id: str = ""


class PipelineNode(_NodeBase):
    kind: Literal["pipeline"] = "pipeline"
    pipeline_id: str = ""


class FigureTemplateNode(_NodeBase):
    kind: Literal["figure_template"] = "figure_template"
    figure_id: str = ""


class ReportTemplateNode(_NodeBase):
    kind: Literal["report_template"] = "report_template"
    template_id: str = ""


# v0.3 新增：AI 工具节点拆分
class AIPromptNode(_NodeBase):
    kind: Literal["ai_prompt"] = "ai_prompt"
    prompt_id: str = ""


class AISkillNode(_NodeBase):
    kind: Literal["ai_skill"] = "ai_skill"
    skill_id: str = ""


class AIAgentNode(_NodeBase):
    kind: Literal["ai_agent"] = "ai_agent"
    agent_id: str = ""


# v0.2 兼容节点（保留以便读取旧文件）
class AIToolNode(_NodeBase):
    kind: Literal["ai_tool"] = "ai_tool"
    tool_type: Literal["prompt", "skill", "agent"] = "prompt"
    tool_id: str = ""


TreeNodeUnion = Annotated[
    Union[
        FolderNode, DataFileNode, ImageWorkNode,
        PipelineNode, FigureTemplateNode, ReportTemplateNode,
        AIPromptNode, AISkillNode, AIAgentNode,
        AIToolNode,   # 保留用于读取 v0.2 旧文件
    ],
    Field(discriminator="kind")
]


class ProjectTree(BaseModel):
    """扁平节点列表，通过 parent_id 反向引用构建树形结构。"""
    model_config = ConfigDict(extra="ignore")

    nodes: List[TreeNodeUnion] = []

    def get_children(self, parent_id: Optional[str]) -> List[TreeNodeUnion]:
        return sorted(
            [n for n in self.nodes if n.parent_id == parent_id],
            key=lambda n: n.order,
        )

    def get_node(self, node_id: str) -> Optional[TreeNodeUnion]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_siblings_max_order(self, parent_id: Optional[str]) -> int:
        orders = [n.order for n in self.nodes if n.parent_id == parent_id]
        return max(orders, default=-1)


# ─────────────────────────────────────────────────────────────
# v0.2 数据载体模型
# ─────────────────────────────────────────────────────────────

class DataFile(BaseModel):
    """一次文件导入的记录（取代旧 Dataset 作为直接容器）。"""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_path: str = ""
    import_time: str = Field(default_factory=lambda: datetime.now().isoformat())
    series: List[DataSeries] = []
    notes: str = ""

    def find_series(self, series_id: str) -> Optional[DataSeries]:
        for s in self.series:
            if s.id == series_id:
                return s
        return None


class SavedPipeline(BaseModel):
    """可保存/加载的操作链（与 data_engine.py ops 格式完全一致）。"""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    ops: List[Dict[str, Any]] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    description: str = ""


class ReportTemplate(BaseModel):
    """Markdown 格式的分析报告模板。"""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    content: str = ""
    is_builtin: bool = False   # 内置模板不可删除


# ─────────────────────────────────────────────────────────────
# v0.2 AI 工具模型
# ─────────────────────────────────────────────────────────────

class AIPrompt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    content: str = ""
    description: str = ""


class AISkill(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    code: str = ""
    description: str = ""


class AIAgent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    system_prompt: str = ""
    description: str = ""
