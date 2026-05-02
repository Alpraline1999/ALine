# Phase 13 Task 1: 项目树拖放 helper 命名修复与最小守护

## 目标

修复 `ProjectTreeDragDropHelper` 内部仍引用旧私有方法名导致的拖放回归，并补一个最小行为守护，避免同类接口漂移再次进入运行时。

## 实施

1. 统一拖放 helper 的调用命名
   - 让 `perform_drop_move()` 使用 helper 自身的公开/现有方法
   - 保持 widget / view / helper 三层链路命名一致
2. 补充最小拖放测试
   - 覆盖 remembered source 下的单节点拖放路径
   - 让测试直接落在 helper/owner 链路上，防止旧私有方法名回流
3. 校验基础拖放行为不回退
   - 单节点拖放
   - 多节点拖放
   - 非法目标阻止
4. 产出阶段收尾文档
   - 记录本阶段完成内容和接口守护边界

