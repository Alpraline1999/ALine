# Phase 22 Task 4: 抽取 AnalysisManager

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 22`

## 目标

从 `core/project_manager.py` 中提取与分析结果管理相关的方法为独立的 `core/analysis_manager.py` 模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/project_manager.py` | 移除分析管理方法，改为委托 |
| `core/analysis_manager.py` | **新建** |
| `ui/pages/analysis_page.py` | 迁移引用 |
| `tests/test_backend.py` | 补充 `TestAnalysisManager` |

## 需要提取的方法

```python
# 从 ProjectManager 中提取:
create_analysis(name, analysis_type, input_series_ids, params, result_series_id, summary) -> AnalysisResult
delete_analysis(analysis_id) -> bool
find_analysis(analysis_id) -> Optional[AnalysisResult]
get_analyses_for_series(series_id) -> List[AnalysisResult]
```

## AnalysisManager 接口设计

```python
# core/analysis_manager.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from models.schemas import AnalysisResult


class AnalysisManager:
    """分析结果的 CRUD 与查询。
    
    只处理 AnalysisResult 对象自身的管理，
    不涉及分析算法的执行（由 core/analysis_engine.py 负责）。
    """

    def __init__(self, project_manager):
        self._pm = project_manager

    @property
    def _project(self):
        return self._pm.current_project

    def create_analysis(self, name: str, analysis_type: str,
                        input_series_ids: List[str],
                        params: Dict[str, Any],
                        result_series_id: Optional[str] = None,
                        summary: Optional[Dict[str, Any]] = None) -> AnalysisResult:
        result = AnalysisResult(
            name=name, analysis_type=analysis_type,
            input_series_ids=input_series_ids, params=params,
            result_series_id=result_series_id, summary=summary or {},
        )
        self._project.analyses.append(result)
        from core.tree_manager import TreeManager
        tm = TreeManager()
        tm.ensure_tree(self._project)
        tm.ensure_root_groups(self._project)
        ar_group = tm.ensure_group(self._project, "analysis_result_group", "分析结果")
        from models.schemas import AnalysisResultNode
        tm.add_node(self._project, AnalysisResultNode(
            name=result.name, analysis_id=result.id
        ), parent_id=ar_group.id)
        return result

    def delete_analysis(self, analysis_id: str) -> bool:
        result = self.find_analysis(analysis_id)
        if result is None:
            return False
        self._project.analyses = [a for a in self._project.analyses if a.id != analysis_id]
        from core.tree_manager import TreeManager
        tm = TreeManager()
        tree_node = tm.find_linked_node(self._project, "analysis_result", "analysis_id", analysis_id)
        if tree_node:
            tm.delete_node(self._project, tree_node.id)
        return True

    def find_analysis(self, analysis_id: str) -> Optional[AnalysisResult]:
        for a in self._project.analyses:
            if a.id == analysis_id:
                return a
        return None

    def get_analyses_for_series(self, series_id: str) -> List[AnalysisResult]:
        return [a for a in self._project.analyses
                if series_id in a.input_series_ids]
```

## 单元测试

```python
class TestAnalysisManager(unittest.TestCase):
    def setUp(self):
        self.project = Project.create_new("test")
        self.pm = MagicMock()
        self.pm.current_project = self.project
        self.mgr = AnalysisManager(self.pm)
    
    def test_create_analysis_appends_to_project(self):
        ar = self.mgr.create_analysis(
            name="test fit", analysis_type="curve_fit",
            input_series_ids=["s1"], params={"model": "linear"},
            result_series_id="r1", summary={"r2": 0.99},
        )
        self.assertEqual(len(self.project.analyses), 1)
        self.assertEqual(ar.analysis_type, "curve_fit")
    
    def test_delete_analysis_removes_from_project(self):
        ar = self.mgr.create_analysis(name="a1", analysis_type="stats",
                                       input_series_ids=[], params={})
        self.mgr.delete_analysis(ar.id)
        self.assertEqual(len(self.project.analyses), 0)
    
    def test_find_analysis_returns_none_for_missing(self):
        self.assertIsNone(self.mgr.find_analysis("nonexistent"))
```

## 验证清单

- [ ] `TestAnalysisManager` 全部通过
- [ ] 分析页执行分析后，结果出现在项目树"分析结果"组
- [ ] 删除分析结果后树节点同步移除

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
