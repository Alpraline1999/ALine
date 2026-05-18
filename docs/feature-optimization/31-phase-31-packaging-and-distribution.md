# Phase 31：打包与分发

## 目标与完成定义

**目标**：明确源码公开、Windows 轻量启动包、Linux 源码运行三条分发路径，并为 Windows bootstrap launcher 建立可实现的设计边界。

**完成定义**：
- GitHub Public 仓库只承担源码、文档、Issue 和源码版本里程碑发布
- Linux 不再作为安装包交付目标，默认通过源码构建/运行
- Windows 提供 bootstrap launcher 方案：分发轻量包，首次启动自动修补内嵌 runtime 并安装依赖
- 打包、首次启动、失败恢复、更新和外部分发策略文档化

## 当前代码现状

- `build.py` — 164 行，已有 PyInstaller 构建脚本
- `aline.spec` — PyInstaller spec 文件
- 有 `build/` 和 `dist/` 目录（构建产出）
- GitHub Actions 已有 `CI` 和源码 `Release` workflow
- 当前 Linux onedir 压缩包体积约 563 MB，主因不是源码，而是运行时依赖体积

## 优化方案

### 1. 分发策略重新划分

- **GitHub**：公开源码、文档、Issue、源码 tag/release
- **Windows 外部分发**：提供 bootstrap launcher 压缩包，不直接把完整依赖打进包内
- **Linux**：不提供安装包，用户通过源码和 `requirements.txt` 运行

这样可以把“源码协作”和“终端用户安装体验”拆开，避免 GitHub Releases 同时承担源码与大体积桌面包分发。

### 2. 为什么不继续优先完整 PyInstaller 包

当前依赖体积的主要来源是：

- `PySide6`
- `scipy`
- `numpy`
- `opencv-python-headless`
- `matplotlib`

完整 onedir/zip 分发会把这些依赖全部提前打进安装包，导致 Windows / Linux 双平台产物都偏大。相比之下，bootstrap 方案把体积从“下载阶段”后移到“首次启动安装阶段”。

### 3. Windows bootstrap launcher

推荐方案：

- 分发一个 **Windows 轻量启动包**
- 包中仅包含：
  - ALine 源码
  - Windows 启动器
  - Python embeddable/runtime
  - 依赖清单与 bootstrap manifest
- 第一次启动时：
  - 检查本地运行环境
  - 修补 embeddable runtime 的 `site-packages`
  - 使用预设镜像安装依赖
  - 安装完成后启动 ALine
- 之后启动：
  - 直接复用已安装环境

详见任务设计文档：
- [phase31_task2.md](tasks/phase31_task2.md)

### 4. Linux 分发策略

Linux 不再追求“下载即用”的安装包交付，默认使用源码运行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

因此：
- 不再把 AppImage 作为当前阶段必须目标
- `build.py --appimage` 可保留为后备实验入口，但不作为发布承诺

### 5. 完整 PyInstaller 路径保留为后备

虽然主策略转为 bootstrap，但完整打包仍应保留为以下场景的后备能力：

- 离线安装
- 首次联网安装失败时的人工补救
- 内部演示或封闭环境分发

当前 spec 与 build 脚本仍有保留价值，但它们不再是首发主路线。

### 6. CI / Release 角色

- `CI`：持续执行源码质量门
- GitHub `Source Release`：只发布源码里程碑，不上传安装包
- Windows 安装包：通过外部分发渠道独立托管

### 7. 当前需要补足的工程能力

Windows bootstrap 方案至少需要以下能力：

- 首次启动状态检测
- 包内 embeddable runtime 目录规划
- `pip` 镜像源与重试策略
- 安装进度与错误提示
- 运行日志落盘
- 版本升级时的依赖修复/补装
- 失败后“修复环境 / 重新安装 / 打开日志”入口

### 8. 构建命令标准化

保留两类构建入口：

- `python build.py`
  - 保留为完整打包/内部演示/离线包入口
- `python scripts/build_bootstrap_windows.py`
  - 作为 Windows 轻量启动包构建入口

## 验收要点

- GitHub 公开仓库可只发布源码，不依赖二进制附件
- Windows bootstrap 包体积明显低于当前完整 PyInstaller zip
- Windows 首次启动可自动安装依赖并进入应用
- 首次启动失败时有明确日志与重试/修复路径
- Linux 用户文档默认走源码运行，不再承诺安装包

## 边界与约束

- 不要求 macOS 打包
- 当前阶段不要求 Linux 安装包
- Windows bootstrap 仅考虑联网安装依赖，不保证完全离线安装
- 自动更新机制不是本轮强制项，但 launcher 必须具备“检测运行环境并修复”的基本能力
