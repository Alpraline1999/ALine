# Phase 2：ProjectSession 与领域服务

## 目标与完成定义

目标：

- 拆解 `ProjectManager` 的职责。
- 固定项目级运行时状态边界。
- 冻结正式领域模型，停止 `Dataset` 与 `DataFile` 双轨运行。

完成定义：

- 形成 `ProjectSession + Repository + TreeService + AssetService + MigrationService + BackupService` 的组合。
- `DataFile + DataSeries` 成为唯一正式数据容器。
- 旧项目只通过迁移路径进入新运行时模型。

## 进入前提

- `Phase 1` 已完成。
- 壳层、命令、共享树边界已稳定。

## 本阶段纳入的状态与边界

- 纳入：
  - 当前项目
  - 当前项目脏标记
  - 项目树上下文
  - 项目级资产读写
  - 项目文件迁移状态
- 不纳入：
  - 页面自己的业务工作区状态

## 本阶段禁止改动的区域

- 禁止提前把页面业务状态塞回 `ProjectSession`。
- 禁止在新结构之外继续增加 `ProjectManager` 公共方法。

## 目标接口/类型/运行时对象

- `ProjectSession`
  - 持有当前项目、当前项目标识、脏标记与项目级事件
- `ProjectRepository`
  - 打开、保存、序列化、反序列化
- `ProjectMigrationService`
  - 历史项目迁移到新模型
- `ProjectTreeService`
  - 节点查找、移动、重命名、路径解析、虚拟叶映射
- `ProjectAssetService`
  - `DataFile/ImageWork/Picture/AnalysisResult` 的业务读写
- `ProjectBackupService`
  - 备份、清理、磁盘同步

## 实施顺序

1. 从 `ProjectManager` 中抽出文件存取和迁移逻辑。
2. 抽出树结构逻辑和资产 CRUD 逻辑。
3. 建立 `ProjectSession` 作为唯一项目运行时入口。
4. 清理运行时模型：
   - `Dataset` 退出主链路
   - 页面、树、分析、处理全部只使用 `DataFile + DataSeries`
5. 将旧 `.aline` 数据在打开时统一迁移到新结构。

## 兼容/迁移策略

- 保留旧项目文件的打开能力。
- 不保留旧运行时数据路径，不再允许新逻辑继续写入 `Dataset`。
- 所有旧结构都通过迁移服务转换后再进入系统。

## 验收标准

- 新代码不再依赖超级 `ProjectManager` 作为直接调用面。
- `Dataset` 不再参与运行时正式路径。
- 项目打开、保存、树操作、资产操作都能通过分离后的服务完成。

## 提交检查点

- 检查点 1：`ProjectRepository` 与 `ProjectMigrationService` 落地。
- 检查点 2：`ProjectTreeService` 与 `ProjectAssetService` 落地。
- 检查点 3：`ProjectSession` 成为唯一项目运行时入口。
- 检查点 4：`Dataset` 从运行时主链路退出。

## 风险与回退办法

风险：

- 迁移逻辑与树结构适配不一致，导致旧项目打开后节点错位。
- `Dataset` 清理不彻底，形成隐式双轨。

回退办法：

- 若旧项目迁移不稳定，先收窄支持范围并补迁移测试，再继续推进。
- 如果某模块仍依赖 `Dataset`，必须先记录并在本阶段消除，不允许带入下一阶段。
