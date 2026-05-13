# Phase 28：i18n 国际化

## 目标与完成定义

**目标**：为 ALine 建立多语言支持基础设施，提取所有用户可见字符串，使后续添加新语言不再需要修改代码。

**完成定义**：
- 所有用户可见的 UI 字符串从代码中提取到 `.po` / `.properties` 资源文件
- 引入 `gettext` 或等效的运行时字符串查找机制
- 建立翻译文件管理流程
- 当前版本以中文为默认语言，为后续英文版本做好准备

## 当前代码现状

- 用户界面字符串全部硬编码在 Python 代码中，散布在 `ui/`、`core/`、`extension_api.py` 等各处
- 典型例子：`"数据集"`、`"处理扩展"`、`"保存项目"`、`"名称不能为空"` 等
- 没有统一的字符串抽取机制
- 错误提示文案和信息提示文案混合在业务逻辑和 UI 代码中

## 优化方案

### 1. 引入 gettext 方案

推荐使用标准库 `gettext`：
```python
import gettext
_ = gettext.gettext  # 基础翻译函数

# 在 UI 代码中使用
label = _("数据集")
```

### 2. 字符串提取策略

优先级分层：

第一层（高优先级）— 用户频繁看到的 UI 文本：
- 页面标题、按钮文字、菜单项
- 提示信息、错误消息
- 设置项标签和说明

第二层（中优先级）— 面向开发者的界面文本：
- 扩展管理中的类别/来源标签
- 日志/调试输出

第三层（低优先级）— 文档和帮助：
- README、用户手册等 markdown 文档

### 3. 建立翻译管理流程

```bash
# 提取字符串
xgettext --language=Python --keyword=_ --output=locale/aline.pot ui/**/*.py core/**/*.py

# 创建中文翻译
msginit --locale=zh_CN --input=locale/aline.pot --output=locale/zh_CN/LC_MESSAGES/aline.po

# 编译翻译
msgfmt --output-file=locale/zh_CN/LC_MESSAGES/aline.mo locale/zh_CN/LC_MESSAGES/aline.po
```

### 4. 不需要翻译的例外

- 扩展名称和描述（由扩展作者提供）
- 日志记录（面向开发者）
- 模型字段名称（序列化不涉及显示）
- 配置文件键名

## 验收要点

- 核心 UI 文本 100% 通过 `_()` 函数访问，无硬编码中文
- 切换语言环境后 UI 文本正确切换
- 所有测试通过
- 翻译文件管理流程文档化

## 边界与约束

- 不要求一次性翻译所有语言
- 默认语言为中文，资源缺失时优雅回退到源码字符串
- 不侵入业务逻辑层的国际化（只做 UI 层）
