========
扩展系统
========

ALine 的扩展系统支持四类扩展：处理（processing）、分析（analysis）、绘图（plot）和数字化（digitize）。
所有扩展通过统一的注册表管理，支持内置扩展和外部扩展的动态加载。

核心模块
--------

:mod:`core.extension_definition`
    扩展类型定义 — 所有扩展 Dataclass、Handler Protocol、标签字典、类型规范化函数。

:mod:`core.extension_types`
    扩展运行时的中性类型与共享帮助函数（TaskProgress、PatchAuthority、PlotExtensionContext）。

:mod:`core.extension_registry`
    扩展注册表 — 管理所有已注册扩展的增删查改和冲突检测。

:mod:`core.extension_loader`
    扩展加载器 — 扫描目录、加载内置和外部扩展，生成加载报告。

:mod:`core.extension_validator`
    扩展校验器 — 对注册的扩展做完整性、兼容性和参数校验。

:mod:`core.extension_api`
    扩展 API 兼容重导出层，统一对外接口。

:mod:`core.extension_runtime`
    扩展运行时契约层，提供请求/结果对象和执行面板。

----

扩展类型定义
------------

.. autoclass:: core.extension_definition.ProcessingExtension
   :members:
   :undoc-members:

.. autoclass:: core.extension_definition.AnalysisExtension
   :members:
   :undoc-members:

.. autoclass:: core.extension_definition.PlotExtension
   :members:
   :undoc-members:

.. autoclass:: core.extension_definition.DigitizeExtension
   :members:
   :undoc-members:

.. autoclass:: core.extension_definition.ExtensionConfigField
   :members:
   :undoc-members:

Handler Protocol
~~~~~~~~~~~~~~~~

每个扩展类型对应一个 Handler Protocol，定义 handler 函数的标准签名：

.. autoclass:: core.extension_definition.ProcessingHandler
   :members:

.. autoclass:: core.extension_definition.AnalysisHandler
   :members:

.. autoclass:: core.extension_definition.PlotHandler
   :members:

.. autoclass:: core.extension_definition.DigitizeHandler
   :members:

类型别名
~~~~~~~~

.. autodata:: core.extension_definition.Point
.. autodata:: core.extension_definition.Line

核心工具函数
~~~~~~~~~~~~

.. autofunction:: core.extension_definition.normalize_extension_version
.. autofunction:: core.extension_definition.normalize_extension_source_kind
.. autofunction:: core.extension_definition.normalize_extension_lines_number
.. autofunction:: core.extension_definition.extension_lines_number
.. autofunction:: core.extension_definition.extension_lines_support_text
.. autofunction:: core.extension_definition.extension_config_fields
.. autofunction:: core.extension_definition.extension_resolved_default_options
.. autofunction:: core.extension_definition.build_extension_entry
.. autofunction:: core.extension_definition.extension_function_category

----

扩展注册表
----------

.. autoclass:: core.extension_registry.ExtensionRegistry
   :members:
   :undoc-members:

.. autofunction:: core.extension_registry.builtin_extension_files
.. autofunction:: core.extension_registry.list_builtin_extension_specs
.. autofunction:: core.extension_registry.list_external_extension_specs

全局注册表实例
~~~~~~~~~~~~~~

.. autodata:: core.extension_registry.extension_registry

----

扩展加载器
----------

.. autoclass:: core.extension_loader.LoadReport
   :members:

.. autofunction:: core.extension_loader.scan_directory
.. autofunction:: core.extension_loader.load_builtin_extensions
.. autofunction:: core.extension_loader.load_configured_extensions
.. autofunction:: core.extension_loader.reload_extensions

----

扩展校验器
----------

.. autoclass:: core.extension_validator.ExtensionValidator
   :members:
   :undoc-members:

----

扩展运行时
----------

.. autoclass:: core.extension_runtime.ExtensionExecutionRequest
   :members:
   :undoc-members:

.. autoclass:: core.extension_runtime.ExtensionExecutionResult
   :members:
   :undoc-members:

.. autofunction:: core.extension_runtime.invoke_processing_extension_handler
.. autofunction:: core.extension_runtime.invoke_analysis_extension_handler
.. autofunction:: core.extension_runtime.invoke_plot_extension_handler
.. autofunction:: core.extension_runtime.invoke_digitize_extension_handler

----

类型与帮助函数
--------------

.. autoclass:: core.extension_types.TaskProgress
   :members:

.. autoclass:: core.extension_types.PatchAuthority
   :members:
   :undoc-members:

.. autoclass:: core.extension_types.PlotExtensionContext
   :members:
   :undoc-members:

.. autofunction:: core.extension_types.merge_nested_dict
.. autofunction:: core.extension_types.normalize_plot_extension_phases

----

使用示例
--------

注册一个处理扩展::

    from core.extension_definition import ProcessingExtension
    from core.extension_registry import extension_registry

    def my_processor(lines, params):
        # 对每条曲线执行自定义处理
        return lines[0]

    ext = ProcessingExtension(
        type="my_processor",
        name="我的处理器",
        handler=my_processor,
        description="自定义数据处理示例",
    )
    extension_registry.register_processing(ext)

加载所有扩展::

    from core.extension_loader import load_configured_extensions

    load_configured_extensions()
