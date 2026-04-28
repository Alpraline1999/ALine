"""兼容导入层。

正式的扩展工具已迁移到 extensions.processing.extension_tools。
此文件仅保留仓库内部过渡期转发，避免一次性打断历史导入路径。
"""

from extensions.processing.extension_tools import *  # noqa: F401,F403