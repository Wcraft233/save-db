# save-db

SteamSweep 的众包存档路径数据库（SaveDB）。纯 JSON，按 AppID 分片存放，客户端编译期内置快照 + 启动时按 ETag 增量更新。

## 结构

```
db/<appid 前三位>/<appid>.json   # 每个游戏一条记录
graylist.json                    # 启发式扫描误报灰名单
```

记录格式（见 [技术方案](https://github.com/Wcraft233/SteamSweep) §8）：

```json
{
  "appid": 1086940,
  "name": null,
  "installed_at_scan": false,
  "save_paths": [
    {"root": 0, "pattern": "_SAVE_Public/Savegames/**", "files_seen": 12, "verdict": "save"}
  ],
  "cloud_behavior": {"observed_syncstate": 1, "cloud_files": 575, "cloud_bytes": 12345, "local_files_present": true},
  "stats": {"seen": 1, "deleted": 0},
  "source": "steamsweep-m1-coldstart"
}
```

- `root`：Steam Cloud Root 编号（0=Default/userdata remote，2=文档，3=AppData\Local，6=AppData\Roaming，9=Saved Games，11=SteamCloudDocuments，12=AppData\LocalLow）
- `pattern`：相对该 root 的路径模式（目录级 `/**`）
- `stats`：匿名统计（seen=被扫描到的次数，deleted=用户选择删除的次数），删除率 = deleted / seen，用于社区参考与反向校验
- 隐私：只含 appid 与路径模式，不含任何用户名、绝对路径、账号信息

## 冷启动数据

首批 55 条记录来自开发机实测（284 个已卸载游戏残留中带云索引的全部应用）+ 误报灰名单，随 SteamSweep 发布自带。

## 贡献

- 应用内「贡献路径 / 修正判定」按钮 → 预填 GitHub Issue 模板（规划中）
- 直接 PR：按上述格式新增/修改 `db/**/*.json`，CI 自动校验格式（结构 + 隐私红线），推送到 main 后自动合并出 savedb.json 并以滚动 Release 资产发布
