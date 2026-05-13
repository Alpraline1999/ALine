# Phase 30 Task 1: 搭建 Sphinx API 参考文档

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 30`

## 目标

基于 docstring 使用 Sphinx + autodoc 自动构建 API 参考文档，覆盖 core/ 和 models/ 的核心模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `docs/source/conf.py` | **新建** |
| `docs/source/index.rst` | **新建** |
| `docs/source/api/*.rst` | **新建** |
| `docs/Makefile` | **新建** |
| `README.md` | 增加文档索引链接 |

## Sphinx 配置

```python
# docs/source/conf.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

project = "ALine"
copyright = "2026, ALine Contributors"
version = "0.3"
release = "0.3.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",     # Google/NumPy style docstring
    "sphinx.ext.viewcode",     # 源码链接
    "sphinx.ext.intersphinx",  # 跨引用
]

templates_path = ["_templates"]
exclude_patterns = []
language = "zh_CN"

# autodoc 配置
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "special-members": "__init__",
}
```

## API 文档页面

```rst
# docs/source/index.rst
ALine API Reference
===================

.. toctree::
   :maxdepth: 2
   :caption: 目录

   api/models
   api/extensions
   api/processing
   api/analysis
   api/export
```

每模块一个 rst：

```rst
# docs/source/api/models.rst
数据模型 (models.schemas)
=======================

.. automodule:: models.schemas
   :members:
   :undoc-members:
   :show-inheritance:
```

```rst
# docs/source/api/extensions.rst
扩展系统 (core.extension_*)
=========================

.. automodule:: core.extension_definition
   :members:
   :undoc-members:

.. automodule:: core.extension_registry
   :members:

.. automodule:: core.extension_loader
   :members:
```

```rst
# docs/source/api/processing.rst
数据处理 (processing)
====================

.. automodule:: processing.data_engine
   :members:

.. automodule:: processing.downsample
   :members:

.. automodule:: processing.calibration
   :members:
```

```rst
# docs/source/api/analysis.rst
分析引擎 (core.analysis_engine)
==============================

.. automodule:: core.analysis_engine
   :members:
```

```rst
# docs/source/api/export.rst
数据导出 (core.exporter)
======================

.. automodule:: core.exporter
   :members:
```

## Makefile

```makefile
# docs/Makefile
SPHINXBUILD = sphinx-build
SOURCEDIR = source
BUILDDIR = build

html:
	$(SPHINXBUILD) -M html $(SOURCEDIR) $(BUILDDIR)

clean:
	rm -rf $(BUILDDIR)

.PHONY: html clean
```

## 要求

```bash
pip install sphinx sphinx-autobuild
```

## 验证清单

- [ ] `cd docs && make html` 无错误
- [ ] `docs/build/html/index.html` 可访问
- [ ] 核心模块的类和函数正确生成文档
- [ ] docstring 中 `:param:`、`:return:` 等标记正确渲染
- [ ] 导航索引正常工作

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
