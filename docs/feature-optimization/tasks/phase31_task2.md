# Phase 31 Task 2：Windows Bootstrap Launcher 设计与落地

## 任务目标

为 Windows 设计并落地一个轻量启动包分发方案，替代“完整 PyInstaller 依赖全打包”的首发路线。

当前仓库已经完成首版实现。本文件同步记录真实实现边界，而不再停留在纯设计假设。

目标包括：

- 包内目录结构
- 首次启动状态机
- 启动器职责边界
- 失败恢复路径
- 与现有 `run.py` / `main.py` 的衔接方式

## 设计结论

推荐采用：

- **Windows bootstrap launcher**
- **包内嵌入式 Python runtime**
- **首次联网安装依赖**
- **源码与运行环境分离**

不采用：

- 用户系统 Python 直接启动
- 首发阶段继续以完整 PyInstaller 包为主分发
- Linux 同步做 bootstrap

## 目录结构

建议的 Windows 分发目录：

```text
ALine-bootstrap/
├── ALine Launcher.exe            # 轻量 GUI/CLI 启动器
├── ALine Launcher.bat            # 控制台回退入口
├── bootstrap/
│   ├── bootstrap_manifest.json   # 启动包版本、Python 版本、依赖策略
│   ├── requirements-lock.txt     # 锁定依赖版本
│   ├── get-pip.py                # embeddable Python 缺 pip 时用于补装
│   └── windows_launcher.py       # 实际 bootstrap 逻辑
├── runtime/
│   └── python/                   # Windows embeddable Python 运行时
├── app/
│   ├── run.py
│   ├── main.py
│   ├── aline_metadata.py
│   ├── app/
│   ├── core/
│   ├── models/
│   ├── ui/
│   ├── processing/
│   ├── digitize/
│   ├── extensions/
│   ├── assets/
│   ├── locale/
│   └── requirements.txt
├── logs/
│   └── bootstrap.log
└── user-data/
    ├── config/
    └── cache/
```

说明：

- `runtime/python/` 放最小 Python 运行时，不依赖系统 Python。
- 首版实现不再创建单独 `runtime/env/`，而是直接把依赖安装到 `runtime/python/Lib/site-packages`。
- `app/` 保持与你当前源码树尽量一致，减少 bootstrap 方案对主工程的侵入。
- `user-data/` 独立于 `app/`，避免升级时覆盖用户状态。

## 启动器职责

启动器只负责四件事：

1. 检查运行环境状态
2. 必要时安装/修复依赖
3. 记录日志与展示错误
4. 启动 `app/run.py`

启动器**不应该**负责：

- 应用业务逻辑
- 项目文件迁移
- 扩展加载逻辑重写
- 与主程序重复维护配置系统

## 首次启动状态机

```text
启动
  -> 检查 bootstrap manifest
  -> 检查 runtime/python 是否存在
  -> 检查内嵌 runtime 状态文件
      -> 不存在：初始化 embedded site / pip
      -> 存在：检查版本戳与依赖戳
  -> 若依赖未安装或版本不匹配：执行安装/修复
  -> 校验关键依赖可导入
  -> 启动 app/run.py
```

更具体的状态：

1. `BOOTSTRAP_INIT`
2. `CHECK_RUNTIME`
3. `PREPARE_EMBEDDED_RUNTIME`
4. `INSTALL_DEPS`
5. `VERIFY_RUNTIME`
6. `LAUNCH_APP`
7. `RECOVERABLE_ERROR`
8. `FATAL_ERROR`

## 依赖安装策略

首发阶段建议：

- `requirements-lock.txt` 固定版本
- 优先从配置镜像源安装
- 允许后续切换备用源
- 安装命令写入日志

建议的安装优先级：

1. 项目预设镜像源
2. 备用镜像源
3. 官方 PyPI

这样做是因为 Windows 首次安装成功率比“绝对最纯粹的官方源”更重要。

## Manifest 结构

建议 `bootstrap/bootstrap_manifest.json` 至少包含：

```json
{
  "app_name": "ALine",
  "app_version": "0.1.0",
  "bootstrap_version": "1",
  "python_version": "3.12.10",
  "requirements_file": "bootstrap/requirements-lock.txt",
  "entrypoint": "app/run.py",
  "runtime_mode": "embedded",
  "runtime_dir": "runtime/python",
  "base_python": "runtime/python/python.exe",
  "launch_python": "runtime/python/pythonw.exe",
  "embedded_pth": "runtime/python/python312._pth",
  "embedded_site_dir": "runtime/python/Lib/site-packages",
  "get_pip_file": "bootstrap/get-pip.py",
  "log_file": "logs/bootstrap.log"
}
```

作用：

- 让启动器不把版本和路径写死在代码里
- 后续升级 bootstrap 时可以做兼容判断

## 关键校验项

安装后至少校验以下模块可导入：

- `PySide6`
- `qfluentwidgets`
- `numpy`
- `scipy`
- `matplotlib`
- `cv2`

如果任一关键模块导入失败：

- 写日志
- 提示“修复环境”
- 不直接进入主程序

## 错误恢复设计

建议提供三类恢复动作：

1. `重试安装`
2. `重装嵌入式 runtime 内依赖`
3. `打开日志目录`

恢复逻辑：

- 普通下载失败：先重试安装
- 依赖损坏或版本戳异常：清理 `Lib/site-packages` 后重装
- 多次失败：引导用户提交日志或下载离线完整包

## 升级策略

首发阶段不做自动更新器，但 launcher 需要能识别：

- 应用版本变化
- `requirements-lock.txt` 变化
- bootstrap 版本变化

若检测到变化：

- 可以先尝试 `pip install -r requirements-lock.txt --upgrade`
- 若失败，再回退到“重装依赖”

## 与现有代码的衔接

现有入口：

- `run.py`
- `main.py`

bootstrap 方案不要求修改业务入口，只要求启动器最终执行：

```text
<runtime/python/pythonw.exe> app/run.py
```

因此现有 UI、扩展、项目系统仍保持主工程内演进，不需要为 bootstrap 重写一套入口。

## 实现建议

推荐拆成两个实现面：

### A. 构建脚本

新增：

```text
scripts/build_bootstrap_windows.py
```

负责：

- 组装 `ALine-bootstrap/`
- 复制源码、资源、manifest
- 注入 Python runtime
- 生成最终 zip

### B. 启动器

当前实现采用：

1. `bootstrap/windows_launcher.py` 负责安装、校验、日志和启动
2. 使用 `distlib` Windows launcher stub 生成极小 `ALine Launcher.exe`

## 不在本任务解决的内容

- 完整离线安装体验
- Linux bootstrap
- macOS 分发
- 自动更新服务端
- 安装包签名

## 当前实现补充

当前仓库已新增：

- `bootstrap/windows_launcher.py`
- `scripts/build_bootstrap_windows.py`

构建脚本支持：

- 下载并缓存官方 Windows embeddable Python zip
- 下载 `get-pip.py`
- 复制当前源码树到分发目录
- 生成锁定版 `requirements-lock.txt`
- 生成 `ALine Launcher.exe` 与 `.bat` 回退入口
- 打包为最终 zip

## 验收口径

- 文档与当前实现一致
- 目录结构、状态机、恢复路径不再依赖临场决定
- 启动器职责边界清晰，不侵入主程序业务层
