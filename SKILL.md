---
name: yuntu-industry-content-rankings-list
description: Use when Yuntu industry-content-ranking entries must be retrieved through the Yuce RPA connector with page filters preserved or explicitly supplied.
---

# Yuntu Industry Content Rankings List

Use this standalone skill to retrieve a Yuntu industry content rankings list
through the fixed Yuce/预策 RPA connector
`rpa.conn.juliang.yt.industry.content.rankings.list`. The connector metadata is
fixed by `scripts/rpa_connector.py`; do not supply or override it.

## Runtime Requirements

Before invoking the gateway, set these environment variables:

- `ENV_BACKEND_HOST`: a bare trusted HTTPS gateway URL without an IP literal, userinfo, query, or fragment.
- `YUCE_AUTHORIZATION`: the gateway authorization value.
- `YUCE_SESSION_ID`: the gateway agent session ID.

Credentials remain in the environment. Do not put credentials in commands,
input JSON, or output paths.

When `shop_id` is not known, run `list-accounts` and use the returned shop
identifier for `--shop-id`.

## Parameters

`schema` emits reference metadata for the available business parameters. It is
useful for discovering accepted values, while `fetch` is authoritative validator for all field, cross-field, date-window, and multivalue constraints.

For `fetch`, `--shop-id` and `--output` are required. Empty parameters preserve the page's current selection.

- `--industry` accepts a nonblank industry name.
- `--time-range-type` accepts `LAST_7_DAYS`, `LAST_30_DAYS`, or `CUSTOM`.
- For `CUSTOM`, pass both `--custom-start-date` and `--custom-end-date` in
  `YYYYMMDD` or `YYYY-MM-DD` form. In the `Asia/Shanghai` business timezone,
  the inclusive window is today-369 through today-4 and the span may not exceed
  44 days.
- `--ages`, `--genders`, and `--crowd-groups` are multivalue inputs. Each
  accepts a comma-separated list or JSON array, with no blanks or duplicates.
- `--brand-scope-type` accepts `ALL_INDUSTRY` or `SPECIFIED_BRANDS`. With
  `SPECIFIED_BRANDS`, `--brands` is required and must contain 3 to 10 values;
  `--brands` otherwise requires `SPECIFIED_BRANDS`.
- `--ranking-limit-type` selects the ranking limit.

The connector enforces its documented enumeration sets for age, gender, crowd,
and ranking inputs. Use `schema` to inspect the current enumeration values
before constructing a request.

## Commands

Run commands from the workspace root. The connector requires Python,
`requests>=2.28,<3`, and `PyYAML>=6,<7` for its contract tests.

List authorized accounts when a suitable `shop_id` is unknown:

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py list-accounts
```

Print the reference metadata:

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py schema
```

Run offline checks without accessing the gateway:

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py self-test
```

Retrieve with no filter parameters, preserving the current page selection:

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --output "RPA数据汇总/yuntu-rankings-current-selection.json"
```

Retrieve a custom filtered list:

```bash
python yuntu-industry-content-rankings-list/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "CUSTOM" \
  --custom-start-date "20260701" \
  --custom-end-date "2026-07-20" \
  --ages "AGE_24_30,AGE_31_35" \
  --genders "FEMALE" \
  --crowd-groups '["REFINED_MOM", "NEW_WHITE_COLLAR"]' \
  --brand-scope-type "SPECIFIED_BRANDS" \
  --brands "燕之屋,王老吉,Oreo/奥利奥" \
  --ranking-limit-type "CTR_TOP1000" \
  --output "RPA数据汇总/yuntu-rankings-custom.json"
```

## Response Handling

The raw gateway response is retained at `--output`, which atomically replaces
an existing path. Use a dedicated path for each request. The response can use
the `payload` or `files` form. No external artifacts are retrieved and no result contents are interpreted.
