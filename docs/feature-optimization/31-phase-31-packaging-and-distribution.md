# Phase 31：打包与分发

## 目标与完成定义

**目标**：完善桌面应用的构建流水线，支持主流 Linux 和 Windows 平台的安装包交付。

**完成定义**：
- PyInstaller 构建配置完善，单文件/目录打包可运行
- Linux 平台支持 AppImage 格式
- Windows 平台支持 NSIS/Inno Setup 安装包
- 构建流程文档化，可从 CI 或本地一键执行

## 当前代码现状

- `build.py` — 164 行，已有 PyInstaller 构建脚本
- `aline.spec` — PyInstaller spec 文件
- 有 `build/` 和 `dist/` 目录（构建产出）
- 但当前构建可能未完整覆盖数据资源、扩展目录路径等问题

## 优化方案

### 1. PyInstaller 配置完善

```python
# build.py — 关键需要处理的事项
a = Analysis(['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/*', 'assets'),           # 图标和背景资源
        ('extensions/*', 'extensions'),    # 内置扩展
        ('config/*', 'config'),            # 默认配置
    ],
    hiddenimports=[
        'PySide6.QtQml',                  # qfluentwidgets 依赖
        'cv2',                             # opencv-python
        'scipy.signal', 'scipy.optimize',  # scipy 子模块
        'openpyxl',
        'scienceplots',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    ...
)
```

关键问题：
- 确保扩展扫描路径在 PyInstaller 打包后正确（`sys._MEIPASS` 兼容已处理）
- 验证 opencv、scipy、qfluentwidgets 的隐含依赖完整
- 处理 Linux 平台 Qt 插件路径（已有 `_configure_linux_environment`）

### 2. AppImage 打包（Linux）

使用 `linuxdeploy` + AppImageKit：
```bash
# 先用 PyInstaller 构建目录
pyinstaller aline.spec

# 用 linuxdeploy 打包为 AppImage
linuxdeploy --appdir dist/ALine --plugin qt --output appimage
```

额外处理：
- 合并 `_configure_linux_environment` 逻辑到 AppImage 启动脚本
- 确保 fcitx/ibus 输入法插件随包分发

### 3. Windows 安装包

使用 NSIS 或 Inno Setup：
- 打包 PyInstaller 产出目录
- 注册文件关联（`.aline` 项目文件）
- 添加入口快捷方式和卸载程序

### 4. 构建命令标准化

```bash
# pyproject.toml
[project.scripts]
aline-build = "build:main"

# 使用
python -m build       # sdist + wheel
python build.py       # PyInstaller 打包
python build.py --appimage  # AppImage
python build.py --installer  # Windows installer
```

## 验收要点

- Linux 上 `python build.py` 产出的二进制直接在无 Python 环境运行
- AppImage 在 Ubuntu 22.04+ 和 Debian 12+ 上可用
- 内置扩展在打包版本中正常加载和执行
- 项目文件的新建、打开、保存功能在打包版本中正常

## 边界与约束

- 不要求 macOS 打包（qfluentwidgets 未验证 macOS 兼容性）
- 打包版本默认不包含开发测试工具
- 自动更新机制作为备选方案，不在本轮强制实现
