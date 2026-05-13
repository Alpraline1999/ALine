# Phase 28 Task 1: 提取核心 UI 字符串到 gettext

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 28`

## 目标

建立 `gettext` 国际化基础设施，提取所有用户可见的 UI 字符串为翻译函数调用。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/i18n.py` | **新建**：gettext 初始化 |
| `ui/main_window.py` | 字符串替换为 `_()` 调用 |
| `core/extension_definition.py` | 标签字典替换 |
| `core/project_manager.py` | 错误消息替换 |
| `ui/pages/*.py` | 页面标题和按钮文本替换 |

## I18n 初始化

```python
# core/i18n.py
from __future__ import annotations
import gettext
import os
import sys
from pathlib import Path


def _get_locale_dir() -> str:
    """获取 locale 目录路径（支持 PyInstaller 打包后）。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = Path(__file__).resolve().parent.parent
    return str(Path(base) / "locale")


_locale_dir = _get_locale_dir()
_translations = gettext.translation(
    "aline",
    localedir=_locale_dir,
    languages=["zh_CN"],  # 默认中文
    fallback=True,
)

_ = _translations.gettext

# 导出翻译函数
gettext_translate = _
```

## 字符串替换优先级

### 第一优先级：核心 UI

```python
# ui/main_window.py
# 修改前
self._nav_items = [
    ("homePage", "首页", FIF.HOME),
    ("dataPage", "数据管理", ...),
]

# 修改后
from core.i18n import _
self._nav_items = [
    ("homePage", _("首页"), FIF.HOME),
    ("dataPage", _("数据管理"), ...),
]
```

### 第二优先级：扩展标签

```python
# core/extension_definition.py
from core.i18n import _

_EXTENSION_CATEGORY_LABELS = {
    "processing": _("处理扩展"),
    "analysis": _("分析扩展"),
    "plot": _("绘图扩展"),
    "digitize": _("数字化扩展"),
}
```

### 第三优先级：错误和提示消息

```python
# core/project_manager.py
from core.i18n import _

def _ensure_non_empty_name(self, name, *, label="名称"):
    if self._normalize_name_key(name):
        return True
    return self._fail_operation(_("名称不能为空"))
```

## 生成 .pot 模板

```bash
# 从项目提取字符串
xgettext --language=Python --keyword=_ \
  --output=locale/aline.pot \
  ui/**/*.py core/**/*.py processing/**/*.py

# 创建中文翻译
msginit --locale=zh_CN \
  --input=locale/aline.pot \
  --output=locale/zh_CN/LC_MESSAGES/aline.po

# 编译
msgfmt --output-file=locale/zh_CN/LC_MESSAGES/aline.mo \
  locale/zh_CN/LC_MESSAGES/aline.po
```

## 验收清单

- [ ] `core/i18n.py` 初始化正确，`_("中文")` 返回"中文"（回退到源码）
- [ ] 所有 UI 页面标题通过 `_()` 翻译
- [ ] 扩展标签正确翻译
- [ ] 错误消息可翻译
- [ ] `.mo` 文件生成后，修改翻译可反映在 UI 中

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
