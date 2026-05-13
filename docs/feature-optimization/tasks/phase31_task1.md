# Phase 31 Task 1: 完善 PyInstaller 打包配置

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 31`

## 目标

确保 `build.py` 和 `aline.spec` 能产出完整的可分发二进制，覆盖所有数据资源、Qt 插件和隐含依赖。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `aline.spec` | 审查并修复 |
| `build.py` | 优化构建流程 |
| `requirements.txt` | 确保打包环境依赖完整 |

## 检查清单

### 1. Data 文件包含

```python
# aline.spec
a = Analysis(['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/**/*', 'assets'),           # 图标和背景资源
        ('extensions/**/*.py', 'extensions'), # 所有内置扩展
        ('config/*', 'config'),              # 默认配置文件
        ('locale/**/*', 'locale'),            # 翻译文件
        ('models/**/*', 'models'),           # 模型定义
    ],
    hiddenimports=[
        # qfluentwidgets 依赖
        'PySide6.QtQml',
        'PySide6.QtNetwork',
        'PySide6.QtSvg',
        
        # opencv
        'cv2',
        
        # scipy 子模块
        'scipy.signal',
        'scipy.optimize',
        'scipy.ndimage',
        'scipy.stats',
        'scipy.sparse',
        
        # 其他
        'openpyxl',
        'scienceplots',
        'pydantic',
        'pydantic.deprecated.decorator',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib.tests',
        'numpy.testing',
        'scipy.tests',
        'PIL',
        'cv2.data',  # opencv 的 haarcascades 等（不需要）
    ],
)
```

### 2. Qt 插件路径

确保 `_configure_linux_environment()` 在打包后也能正确找到 Qt 插件：
- `platforminputcontexts`（fcitx/ibus 输入法）
- `platforms`（xcb/wayland）
- `styles`（qfluentwidgets 需要的 Qt 样式）

```python
# 在 aline.spec 或 build.py 中
# 指定 Qt 插件目录
import os
from PySide6 import QtCore
qt_plugin_path = os.path.join(os.path.dirname(QtCore.__file__), 'plugins')
```

### 3. 构建测试

```bash
# 完整构建
python build.py

# 验证打包产物
dist/ALine/ALine --version

# 测试核心功能
dist/ALine/ALine           # 启动
# 新建项目 → 导入数据 → 处理 → 分析 → 绘图 → 导出
```

### 4. 常见问题排查

| 问题 | 原因 | 解决 |
|---|---|---|
| ModuleNotFoundError: PySide6 | 未正确包含 | 在 hiddenimports 中显式列出 |
| 扩展目录为空 | datas 未包含 extensions/ | 在 datas 中添加递归 glob |
| 无法输入中文 | Qt 输入法插件缺失 | 包含 platforminputcontexts |
| numpy/scipy 导入慢 | 未排除测试子模块 | 在 excludes 中排除 `*.tests` |

## 验证清单

- [ ] `python build.py` 成功完成
- [ ] 打包版本在无 Python 环境启动
- [ ] 内置扩展正常加载
- [ ] 文件导入功能正常（CSV/Excel）
- [ ] matplotlib 绘图正常
- [ ] 项目新建、保存、打开循环正常
- [ ] 输入法（fcitx/ibus）功能正常

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
