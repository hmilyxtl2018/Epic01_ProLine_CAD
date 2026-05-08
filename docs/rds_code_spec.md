# RDS Code 编码规范 (Reference Designation System)

> 适用范围：`hierarchy_nodes.rds_code` 列、所有引用层级节点的 API 入参 / 文件
> 命名 / UI 显示。
> 标准基础：IEC/ISO 81346（参考标识系统）+ ISA-95 / IEC 62264（企业控制层级）。
> 决策来源：[ADR-0009 时空约束本体](adr/0009-spacetime-constraint-ontology.md)。

## 0. 一句话定义

`rds_code` 是**层级节点的全局唯一可读地址**，由"视角前缀 + 大写段落 . 大写段落"组成，
取代不稳定的 UUID 作为人和系统之间的契约。

例：`-ENT.AC.SH01.A2.L1.S20` 表示"AC 集团 / 上海基地 / A2 厂房 / L1 线 / S20 工位"。

## 1. 三视角与前缀

IEC 81346 规定一个实体可同时被三个互相正交的视角描述。每条 `rds_code` 必须以下列前缀之一开头：

| 前缀 | 视角         | aspect 枚举   | 描述              | 例                                 |
| ---- | ------------ | ------------- | ----------------- | ---------------------------------- |
| `-`  | 场所/位置     | `LOCATION`    | 这东西**在哪里** | `-ENT.AC.SH01.A2.L1.S20`           |
| `+`  | 物理产品/设备 | `PRODUCT`     | 这东西**是什么** | `+EQ.WELD.01` / `+TPL.WELDING_ROBOT` |
| `=`  | 功能/工序     | `FUNCTION`    | 这东西**做什么** | `=PROC.TS-ASSY-01` / `=DOC.SOP-WELD-001` |

> 同一物理实体（如一台焊接机器人）通常会出现在三个视角下：作为 `+EQ.WELD.01`
> 注册其铭牌身份，作为 `-ENT.AC.SH01.A2.L1.S20` 落到 S20 工位，作为
> `=PROC.TS-ASSY-01` 参与 TS-ASSY-01 工序。三者通过 `parent_id` / `asset_guid` /
> `process_step_id` 互相挂接。

## 2. 段落与分隔符

| 元素           | 规则                                                           |
| -------------- | -------------------------------------------------------------- |
| 段间分隔符     | 英文句点 `.`（U+002E），不允许 `_` / `-` / `/`                  |
| 段内字符       | `[A-Z0-9]+`：大写英文字母 + 阿拉伯数字。**不允许小写、汉字、空格** |
| 段长建议       | 单段 1~10 字符；总长 ≤ 64 字符（DB 列为 `VARCHAR(64)`）          |
| 视角前缀       | 出现且仅出现一次，位于第 1 个字符                               |

正则（生效中，作为 M1.5 校验函数的实现依据）：

```regex
^[-+=][A-Z0-9]+(\.[A-Z0-9]+)*$
```

## 3. node_kind 与层级语义

`hierarchy_nodes.node_kind` 是闭集枚举，并且与 `aspect` 必须满足 INV-16 矩阵：

### 3.1 LOCATION（`-` 前缀，强烈推荐用作树形主轴）

| 段位 | node_kind     | 段示例 | 业务含义                  | 典型节点数  |
| ---- | ------------- | ------ | ------------------------- | ----------- |
| 1    | `Enterprise`  | `ENT`  | 集团/法人实体              | 1–2         |
| 2    | `Site`        | `SH01` | 基地/工厂                  | 3–10        |
| 3    | `Area`        | `A2`   | 厂房/车间/分区             | 5–30        |
| 4    | `Line`        | `L1`   | 产线/工段/脉动节拍线       | 10–100      |
| 5    | `WorkCenter`  | `WC1`  | 工作中心/单元（可选中间层） | 0–N         |
| 6    | `Station`     | `S20`  | 工位/机台位/检验点（叶子） | 100–1000    |

> 推荐保持 LOCATION 段位与 node_kind 顺序一致，便于人眼识别。`WorkCenter` 是
> 可选层 —— 没有可直接 `Line → Station`。

### 3.2 PRODUCT（`+` 前缀，平面注册，不强制树形）

| node_kind            | 段示例                | 含义                         |
| -------------------- | --------------------- | ---------------------------- |
| `Equipment`          | `EQ.PRESS.01`         | 单台设备实例（带序列号）     |
| `Tool`               | `TOOL.WRENCH.M16`     | 刀具/工具                    |
| `Fixture`            | `FIX.CHASSIS.A`       | 夹具/定位工装                |
| `Material`           | `MAT.STEEL.S355`      | 物料/原材料/半成品           |
| `AssetTypeTemplate`  | `TPL.WELDING_ROBOT`   | 设备类型模板（约束按类型绑） |

### 3.3 FUNCTION（`=` 前缀，平面）

| node_kind   | 段示例              | 含义                 |
| ----------- | ------------------- | -------------------- |
| `Procedure` | `PROC.TS-ASSY-01`   | 工艺规程 / 工序步骤 |
| `Document`  | `DOC.SOP-WELD-001`  | 作业指导书/标准文档 |

> FUNCTION 段允许出现 `-` 作为业务编码内部分隔（如 `TS-ASSY-01`）—— 这是
> **段内**字符，不是段间分隔符。但仍只允许 `[A-Z0-9-]`，不允许小写。

## 4. 完整性与不变量

DB 层强制：

- `uq_hn_rds_code_live` 部分唯一索引：`rds_code` 在 `deleted_at IS NULL` 的行
  里全局唯一。
- `ck_hn_no_self_parent`：`parent_id <> id`。
- INV-16：`(aspect, node_kind)` 必须落在第 3 节的矩阵里。
- `parent_id` ON DELETE RESTRICT：父节点存在子节点时禁止物理删除。

Service 层（M1.5 待落地）追加：

- 正则白名单（第 2 节）。
- 父子 aspect 一致性：LOCATION 子节点的 parent 必须也是 LOCATION（PRODUCT /
  FUNCTION 同理）。**禁止跨视角嵌套**，跨视角关系用 `asset_guid` /
  `process_step_id` 字段表达。
- 父子段位前缀连续：LOCATION 子的 `rds_code` 必须以父的 `rds_code` 为前缀
  + `.` + 新段。例：`-ENT.AC.SH01` 的 child 必须形如 `-ENT.AC.SH01.{SEG}`。
- 环检测：递归 CTE 校验 `parent_id` 不形成环。
- 深度上限：LOCATION 主轴 ≤ 6 层（Enterprise..Station）。

## 5. 生成约定（推荐，不强制）

### 5.1 LOCATION 段命名

| 层级       | 推荐风格                | 示例           |
| ---------- | ----------------------- | -------------- |
| Enterprise | 集团代号（2–3 字母）    | `AC` / `BAC`   |
| Site       | 城市拼音首字母 + 序号   | `SH01` / `BJ02`|
| Area       | `A` + 数字              | `A2` / `A12`   |
| Line       | `L` + 数字              | `L1` / `L7`    |
| WorkCenter | `WC` + 数字             | `WC1`          |
| Station    | `S` + 两位数字（10 进位）| `S10` `S20` `S30` |

> Station 推荐使用 `S10` `S20` `S30` 而非 `S1` `S2` `S3` —— 留出十位数字插槽
> 方便后续在两个工位之间插入新工位（`S15`），避免大面积重编号。

### 5.2 PRODUCT / FUNCTION 段命名

- 使用业务领域已经稳定的代号：MES 设备号、PLM 物料号、SOP 编号。
- 以双段开头声明子类型（`EQ.` / `TPL.` / `PROC.` / `DOC.`），便于人眼分类与 SQL `LIKE`。

### 5.3 不要在 rds_code 里编码

- 时间戳（用 `valid_from / valid_to`）。
- 阶段（用 `applicable_phases`）。
- 状态（用 `deleted_at` / 业务表 `status`）。
- 中文名（用 `name_zh` 列）。

`rds_code` 一旦写入，**视为长期稳定**；改名走"软删除 + 新建"，留下审计痕迹。

## 6. 查询模式

```sql
-- 取整棵树（带祖先路径）
SELECT rds_code, depth, ancestor_path
  FROM v_hierarchy_tree
 WHERE root_rds_code = '-ENT.AC';

-- 某工位继承到的所有约束
SELECT * FROM v_active_constraints_at_node
 WHERE target_rds_code = '-ENT.AC.SH01.A2.L1.S20'
   AND applicable_phases ? 'OPERATION';

-- 找子树（直接用前缀匹配 LOCATION 段）
SELECT rds_code FROM hierarchy_nodes
 WHERE aspect = 'LOCATION'
   AND deleted_at IS NULL
   AND (rds_code = '-ENT.AC.SH01.A2.L1'
        OR rds_code LIKE '-ENT.AC.SH01.A2.L1.%');
```

> 第三条提示：LOCATION 系借助"段连续"约定可以用 `LIKE` 跑子树查询，免递归。
> PRODUCT / FUNCTION **不要**这样做（命名是平面的，前缀不蕴含父子）。

## 7. 反模式（一律 reject）

| 错误                                | 理由                                           |
| ----------------------------------- | ---------------------------------------------- |
| `-ent.ac.sh01.a2.l1.s20` (小写)     | 第 2 节正则                                    |
| `-ENT.AC.SH01/A2/L1/S20` (斜杠分隔) | 第 2 节分隔符                                  |
| `+TPL.焊接机器人` (中文)            | 段内字符；中文用 `name_zh`                     |
| `-ENT.AC > +EQ.PRESS.01` 父子       | 第 4 节跨视角禁止；改用 `asset_guid` 关联      |
| `=PROC.TS-ASSY-01.S20`              | FUNCTION 与 LOCATION 混编                      |
| 改 rds_code 而不软删                | 第 5.3 节；破坏审计与外部引用                  |

## 8. 相关文件

- 表定义：[shared/db_schemas.py](../shared/db_schemas.py) `class HierarchyNode`
- 迁移：[db/alembic/versions/0022_hierarchy_nodes.py](../db/alembic/versions/0022_hierarchy_nodes.py)
- 视图：[db/alembic/versions/0026_data_architect_views.py](../db/alembic/versions/0026_data_architect_views.py)
- Demo：[scripts/seed_constraint_demo.py](../scripts/seed_constraint_demo.py)
- ADR：[docs/adr/0009-spacetime-constraint-ontology.md](adr/0009-spacetime-constraint-ontology.md)
