# astrbot_plugin_ccb_plus

> CCB 增强版 —— 基于 [灵煞 / ccb](https://github.com/Koikokokokoro/astrbot_plugin_ccb) 改进的 AstrBot 群娱乐插件

> ⚠️ 免责声明：本插件内容纯属群友互动娱乐，请遵守当地法律法规及平台社区规范使用。

## ✨ 功能特性

- **荆州容量检查**：数据更真实，不再出现 `0.00000001ml` 的失真数值
- **群组分离**：每个群独立计算，互不干扰
- **北朝记录**：保留每次 ccbtop 上榜的人与次数
- **养胃系统**：过于频繁的 ccb 会触发"养胃"限流（时长可配置）
- **暴击系统**：有一定概率注入量翻倍（概率可配置）
- **单次最大注入量记录**：自动记录单次 max 及其产生者（旧数据缺失时回退用平均值）
- **max 排行榜**：新增 max 排行命令维度
- **可配置完整日志**：选择是否保留每一条 ccb 记录（默认关闭）
- **白名单**：名单内对象脱离七情六欲，无法被 ccb

## 📋 命令列表

| 命令     | 说明           |
| -------- | -------------- |
| ccbtop   | 艾草排行榜     |
| ccbvol   | 失荆州排行榜   |
| ccbinfo  | 查询 ccb 信息  |
| xnn      | xnn 榜         |
| max 排行 | 单次最大注入量排行 |

> 说明：根据群友使用量反馈，原「海王榜」命令已默认注释，如需启用请自行修改源码。

## 🚀 安装

### 方式一：AstrBot 插件市场

1. 打开 AstrBot 管理面板 → 插件管理
2. 搜索 `astrbot_plugin_ccb_plus` 并安装
3. 重载插件，在配置页调整参数后即可使用

### 方式二：手动安装

```bash
cd <AstrBot>/data/plugins
git clone https://github.com/Bamboorat0908/astrbot_plugin_ccb_plus.git
```

然后在 AstrBot 管理面板中重载插件。

> 💡 本插件无额外 Python 依赖（`dependencies: []`），开箱即用。

## ⚙️ 配置说明

插件支持在 AstrBot 管理面板中修改以下参数：

| 配置项             | 类型  | 默认值    | 说明                                       |
| ------------------ | ----- | --------- | ------------------------------------------ |
| `yw_ban_duration`  | int   | `3600`    | 养胃时长（秒），触发限流后禁用的时长       |
| `yw_reset_timeout` | int   | `300`     | 连续 ccb 计数重置时间（秒）                |
| `white_list`       | list  | `[]`      | 不能进行 ccb 的 id 列表                    |
| `self_ccb`         | bool  | `false`   | 是否允许 0721（指令未指定对象时）          |
| `crit_prob`        | float | `0.2`     | 暴击概率                                   |
| `is_log`           | bool  | `false`   | 是否独立保留每一条 ccb 完整记录（含双方与注入量） |

## 💾 数据存储

- **主数据文件**：`<AstrBot>/data/ccb.json`（长期化保存，重载/重启不丢失）
- **完整日志**：当 `is_log` 开启时，每一条 ccb 记录将独立保留

> 更新前建议备份数据文件（如有历史数据），以防出现意料外的格式变化。

## 📜 更新日志

### 24/8/2025

- 根据群友使用量，注释了海王榜命令
- 新增：记录单次最大注入量 `max` 及其产生者（不存在该项的旧数据使用平均值兜底）
- 新增：可通过配置选择是否保留每一次 ccb 的记录（默认 `false`）
- `ccbinfo` 新增展示 `max`、cb 次数
- 新增 max 排行榜

### Previous

- ☑ 荆州容量检查，不再出现 `0.00000001ml` 的失真数据
- ☑ 群组分离，每个群独立数据
- ☑ 添加北朝记录，保留 ccbtop 的人及次数
- ☑ 添加养胃系统：过于频繁的 ccb 会触发养胃
- ☑ 添加暴击系统：有一定概率翻倍
- ☑ `ccbtop` 艾草排行榜
- ☑ `ccbvol` 失荆州排行榜
- ☑ `ccbinfo` 查询 ccb 信息
- ☑ `haiwang` 海王榜
- ☑ `xnn` xnn 榜
- ☑ 添加 AstrBot 配置文件，可在插件管理中修改部分参数
- ☑ 添加白名单：名单内 id 不能被执行 ccb
- ☑ `ccb.json` 长期化，存储位置迁移至 `astrbot/data`

## 🧩 TODO

- 排行榜过多时支持以图片格式发送（视群友反馈决定）

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 开源。

## 👤 致谢

- 原版插件：[灵煞 / ccb](https://github.com/Koikokokokoro/astrbot_plugin_ccb)
- 维护发布：[@Bamboorat0908](https://github.com/Bamboorat0908)

---

绝赞更新中 ⭐ 如有额外需要的功能欢迎提 Issue，随缘更新。
