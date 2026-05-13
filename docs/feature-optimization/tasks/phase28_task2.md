# Phase 28 Task 2: 翻译文件管理与构建集成

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 28`

## 目标

建立翻译文件的规范管理流程，包括字符串提取、翻译、编译、构建集成。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `locale/aline.pot` | **新建** |
| `locale/zh_CN/LC_MESSAGES/aline.po` | **新建** |
| `locale/zh_CN/LC_MESSAGES/aline.mo` | **新建**（编译后） |
| `pyproject.toml` | 添加 i18n 脚本命令 |
| `Makefile` 或 `scripts/i18n.sh` | 翻译工作流脚本 |

## 文件结构

```
locale/
├── aline.pot                  # 模板文件（从源码提取）
├── zh_CN/
│   └── LC_MESSAGES/
│       ├── aline.po           # 中文翻译源文件
│       └── aline.mo           # 编译后的二进制
└── en_US/                      # 未来扩展
    └── LC_MESSAGES/
        ├── aline.po
        └── aline.mo
```

## 脚本工具

```bash
# scripts/i18n.sh
#!/bin/bash
# 提取字符串
find ui core processing -name "*.py" | xargs xgettext \
  --language=Python --keyword=_ --keyword=_n:1,2 \
  --output=locale/aline.pot

# 合并到现有翻译
msgmerge --update locale/zh_CN/LC_MESSAGES/aline.po locale/aline.pot

# 编译
msgfmt --output-file=locale/zh_CN/LC_MESSAGES/aline.mo \
  locale/zh_CN/LC_MESSAGES/aline.po

echo "i18n: 更新完成"
echo "  POT: $(grep -c msgid locale/aline.pot) 条目"
echo "  PO:  $(grep -c msgid locale/zh_CN/LC_MESSAGES/aline.po) 条目"
```

## pyproject.toml 入口

```toml
[tool.aline.scripts]
i18n-extract = "bash scripts/i18n.sh"
```

## 翻译文件内容示例

```po
# Chinese translations for ALine
# Copyright (C) 2026 ALine
# This file is distributed under the same license as the ALine package.
#
msgid ""
msgstr ""
"Project-Id-Version: ALine 0.3\n"
"Language: zh_CN\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"

msgid "首页"
msgstr "首页"

msgid "数据管理"
msgstr "数据管理"

msgid "保存项目"
msgstr "保存项目"

msgid "名称不能为空"
msgstr "名称不能为空"
```

## 验证清单

- [ ] `bash scripts/i18n.sh` 无错误
- [ ] `.pot` 文件包含所有 `_()` 包裹的字符串
- [ ] `.po` 文件已合并新字符串
- [ ] `.mo` 文件正确编译
- [ ] 构建脚本包含 locale 目录（PyInstaller 打包）

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
