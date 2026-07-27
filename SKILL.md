---
name: 云图行业内容榜单列表
description: 适用于需要通过预策 RPA 连接器获取云图行业内容榜单条目，并保留或显式提供页面筛选条件的场景。
---

# 云图行业内容榜单列表

使用此独立技能，通过固定的预策 RPA 连接器 `rpa.conn.juliang.yt.industry.content.rankings.list` 获取云图行业内容榜单。连接器元数据由 `scripts/rpa_connector.py` 固定；不要提供或覆盖。

## 运行环境要求

调用网关前，设置以下环境变量：

- `ENV_BACKEND_HOST`：受信任的纯 HTTPS 网关 URL，不得使用 IP 字面量、userinfo、查询参数或片段。
- `YUCE_AUTHORIZATION`：网关授权值。
- `YUCE_SESSION_ID`：网关代理会话 ID。

凭证应保留在环境变量中。不要将凭证写入命令、输入 JSON 或输出路径。

未知 `shop_id` 时，运行 `list-accounts`，并将返回的店铺标识用于 `--shop-id`。

## 参数

`schema` 会输出可用业务参数的参考元数据，可用于发现可接受的值；`fetch` 是所有字段、跨字段、日期窗口和多值约束的权威校验器。

对于 `fetch`，`--shop-id` 和 `--output` 必填。空参数会保留页面当前选择。

- `--industry` 接受非空行业名称。
- `--time-range-type` 接受 `LAST_7_DAYS`、`LAST_30_DAYS` 或 `CUSTOM`。
- 对于 `CUSTOM`，同时传入 `--custom-start-date` 和 `--custom-end-date`，格式为 `YYYYMMDD` 或 `YYYY-MM-DD`。在业务时区 `Asia/Shanghai` 中，闭区间为 today-369 至 today-4，跨度不得超过 44 天。
- `--ages`、`--genders` 和 `--crowd-groups` 为多值输入。每项接受逗号分隔列表或 JSON 数组，且不能有空值或重复项。
- `--brand-scope-type` 接受 `ALL_INDUSTRY` 或 `SPECIFIED_BRANDS`。使用 `SPECIFIED_BRANDS` 时，`--brands` 必填且必须包含 3 至 10 个值；其他情况下提供 `--brands` 也必须同时使用 `SPECIFIED_BRANDS`。
- `--ranking-limit-type` 选择榜单限制。

连接器会强制执行年龄、性别、人群和榜单限制的枚举值。使用 `schema` 查看当前枚举和业务参数参考元数据。

## 命令

从工作区根目录运行命令。此技能需要 Python 和 `requests>=2.31,<3`。

列出已授权账户：

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py list-accounts
```

输出业务参数参考元数据：

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py schema
```

运行不访问网关的离线检查：

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py self-test
```

获取最近七天的食品饮料榜单：

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" \
  --output "RPA数据汇总/yuntu-rankings-list.json"
```

## 响应处理

原始网关响应会原子保留在 `--output` 指定位置，并原子替换已有文件。响应可能包含 `payload` 或 `files` 结果。此技能不会检索外部产物，也不会解读结果内容；它只为调用方保留响应。
