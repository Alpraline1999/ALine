# Phase 4：扩展协议与注册机制现代化

## 目标与完成定义

目标：

- 在保留现有四类扩展体系可用性的前提下，补齐长期扩展生态所需的协议元数据与注册抽象。
- 让扩展作者声明的内容、运行时验证的内容、UI 设置页消费的内容尽量趋于同一个模型。

完成定义：

- 扩展具备更明确的 compatibility / capability / authority 元数据。
- 加载前或加载时，应用能更准确地提示兼容性、风险和能力边界。
- 扩展注册方式对内保持兼容，对外更易理解、更利于后续扩展生态增长。

## 当前审查结论

### 当前设计的合理部分

- 四类扩展入口是清晰的：
  - `ProcessingExtension`
  - `AnalysisExtension`
  - `PlotExtension`
  - `DigitizeExtension`
- `ExtensionRegistry` 已具备：
  - type/name 唯一性校验
  - 基础 contract validation
  - load report / load detail
- `extensions/README.md` 和接口示例扩展已经形成了可执行、可测试的作者文档。
- 对“当前仅有内置扩展 + 严格内部协议”的阶段来说，这套设计不是错误的，也不需要推倒重来。

### 当前设计仍需优化的部分

- 注册抽象仍然偏命令式：
  - 文件扫描后执行 `register_extensions(registry)`
  - 更适合内部使用，不利于做更强的预检查、兼容性提示和生态化管理
- 协议元数据缺口明显：
  - 没有 API 兼容版本声明
  - 没有能力声明，如 `supports_progress`、`supports_cancel`
  - 没有统一的 authority 声明，如 plot 扩展对样式的接管策略
- 四类 extension dataclass 结构高度相似，但重复维护较多。
- `build_extension_entry()` 产出的 UI 消费模型与扩展作者侧声明模型不是同一抽象层。
- 后续若要支持更多外部扩展、批量检查、迁移升级、设置页诊断，当前模型会逐步吃力。

## 推荐方向

### 1. 保留兼容入口，不做一次性推翻

推荐保留：

- 文件扫描
- `register_extensions(registry)`
- 现有四类 handler 签名

原因：

- 当前仓库已存在大量内置扩展与测试。
- 直接切换到全新插件系统，收益不如代价大。

### 2. 先补“声明层”，再补“加载层”

推荐顺序：

1. 先统一扩展声明模型
2. 再增强 loader / settings / runtime 对这些声明的消费
3. 最后再考虑是否需要更 declarative 的注册 helper

## 建议优化项

### A. 兼容性元数据

建议补充：

- `api_version`
  - 扩展按哪个 ALine 扩展协议编写
- `min_app_version`
  - 最低支持应用版本
- `max_app_version` 或 `tested_app_range`
  - 可选，帮助提示风险

目标：

- 扩展升级时，设置页和加载器能说清楚“为什么不能加载”。
- 避免以后只靠导入异常或 handler 行为异常判断兼容性问题。

### B. capability 元数据

建议以统一字段声明：

- `supports_multiline`
- `supports_background`
- `supports_progress`
- `supports_cancel`
- `supports_settings_preset`
- `produces_line`
- `produces_tables`
- `produces_report_placeholders`
- `mutates_artists`

目标：

- UI 能基于能力声明决定显示哪些提示、控制项和保护措施。
- 后续 Phase 5 的异步执行和进度反馈有正式挂点。

### C. authority 元数据

这部分与当前 Phase 2 强关联，但 scope 更大。

建议声明：

- `style_authority`
  - `advisory`
  - `authoritative`
- `authoritative_fields`
  - 用于 plot 扩展声明它真正接管的字段
- `post_render_mutation`
  - 标记 `after_plot` 是否直接修改最终 artist

目标：

- 用户能在 UI 中看到扩展是否“建议修改”还是“接管修改”。
- 设置页和图表页能统一说明该扩展的影响范围。

### D. 统一声明模型

推荐引入共享的 base spec 或 manifest model，而不是长期维持四套近似重复的结构。

推荐方向：

- 保留四类具体 extension type
- 但在其上共享一层元数据模型，例如：
  - id / type / name / description
  - version / source_kind / tool_tier
  - compatibility / capability / authority
  - config schema

目标：

- 降低维护重复
- 让 loader、settings、chart/process/analysis 页面消费的信息来源更统一

### E. 注册 helper 现代化

不建议直接废弃 `register_extensions(registry)`，但建议新增更规范的 helper。

例如可考虑：

- `registry.register(spec)`
- `registry.register_many([...])`
- 或 `build_extension_spec(...)` 这类显式构建器

收益：

- 内置扩展和外部扩展的声明风格更一致
- 更利于静态检查和批量迁移

### F. warnings / progress / cancel 正式承载

当前协议中：

- processing 扩展不返回 warnings
- analysis 扩展可返回 dict，但没有统一 progress/cancel 约定
- plot/digitize 也没有正式的执行反馈通道

建议：

- 先不改变 handler 签名
- 但为运行时结果和 capability 建立正式出口

例如：

- 运行时包装层承载 warnings
- capability 声明支持 progress/cancel
- 后台执行框架承载状态上报

## 验收标准

- 扩展兼容性、能力和 authority 信息可以被 settings 页和运行时统一读取。
- 新增元数据后，不需要在多个页面分别重复猜测扩展行为。
- 旧扩展仍可通过兼容路径继续加载，不要求一次性全部重写。
- 扩展作者文档可以更明确地说明：
  - 我支持什么
  - 我可能覆盖什么
  - 我是否适合后台执行

## 本阶段不纳入的范围

- 重写为全新的外部插件系统
- 网络扩展商店
- 沙箱隔离执行
- 大规模重写全部内置扩展

## 风险与回退

风险：

- 若一次性把协议变成过度复杂的 manifest，会让内置扩展迁移成本过高。
- 若 capability/authority 命名不清晰，后续 UI 和 runtime 仍会各说各话。

回退方式：

- 先引入元数据字段和统一 helper，不立即强制所有旧扩展全部声明。
- 兼容保留 `register_extensions(registry)` 和现有 handler 签名。
