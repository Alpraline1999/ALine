# Phase 37 Task 3: 翻译资源与打包链路补齐

## 目标

确保语言切换功能具备完整的翻译资源提取、编译和打包链路。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `locale/` | `.pot` / `.po` / `.mo` 更新 |
| `build.py` / `aline.spec` | 打包包含 locale |
| `scripts/` 或 `pyproject.toml` | i18n 工作流脚本 |

## 验收清单

- [ ] locale 资源能被正确提取和编译
- [ ] 打包产物包含语言资源
