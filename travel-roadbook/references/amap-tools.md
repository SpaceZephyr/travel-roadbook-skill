# 高德地图工具链（旅行路书专用）

> 调用任何高德 MCP 工具前，若其参数 schema 不在当前上下文，先用 `tool_search` 搜工具名取回真实 schema，禁止凭记忆构造参数。本文记录的字段以实战返回为准，若与 schema 冲突以 schema 为准。

## 工具总览

| 用途 | 工具 | 关键入参（约） | 取什么 |
|---|---|---|---|
| 地名→坐标 | `maps_geo` | `address`，可选 `city` | `geocodes[].location`，形如 `"114.05,22.54"`（GCJ-02 经纬度，逗号分隔） |
| 驾车里程/时长 | `maps_direction_driving` | `origin`、`destination`，均为 `"经度,纬度"` | `route.paths[0]` 的 `distance`（米）、`duration`（秒），换算 km/h |
| 城市天气 | `maps_weather` | `city`（城市名或 adcode） | `forecasts[]`：`date`、`dayweather`/`nightweather`、`daytemp`/`nighttemp` |
| POI 检索 | `maps_text_search` | `keywords`、`city`、可选 `citylimit` | `pois[].id`（即 poiId）、`name`、`address` |
| 生成行程地图 | `maps_schema_personal_map` | `orgName`、`lineList` | 一段 `amapuri://workInAmap/createWithToken?polymericId=...` 链接 |

## 标准作业顺序

1. **列节点**：从行程草案提取全部过夜城市/景区节点（去程、游玩、返程按时间顺序）。
2. **取坐标**：对每个节点调 `maps_geo`（城市锚点优先用"XX市人民政府"，景区用全称，如"香格里拉虎跳峡景区"）。
3. **取 poiId**：对每个节点调 `maps_text_search`，取 `pois[0].id`。注意 text_search **不返回坐标**，坐标必须另调 geo；geo 与 text_search 是两条独立数据。
4. **逐段实测里程**：对相邻节点依次调 `maps_direction_driving`，把 km 与小时数写进路书 JSON 的 `km` 字段（格式 `"643km · 约6.7h"`）。多节点可并行调用。
5. **查天气**：对沿途城市调 `maps_weather`，组装天气卡片。
6. **生成行程地图**：见下。

## maps_schema_personal_map 的 lineList 结构

```json
{
  "orgName": "深圳→香格里拉14天自驾",
  "lineList": [
    {
      "title": "去程",
      "pointInfoList": [
        {"name": "深圳", "lon": 114.057951, "lat": 22.543550, "poiId": "B02F300691"}
      ]
    }
  ]
}
```

- `lon`/`lat` 是**数字**（不是字符串），`poiId` 来自 text_search。
- 可按去程/游玩/返程拆多条 line，也可一条线串全程；节点顺序必须与行程一致。
- 返回的 `amapuri://...` 链接**直接给用户、不要改写或二次编码**。

## 已知坑（实测）

1. **天气只有未来约 4 天预报**。行程更长时，覆盖不到的日期用"同期气候参考"（可搜索历年同期气温），并在 `weather_note` 显式注明查询日期与"出发前再更新"。
2. **amapuri 是自定义协议，不是 http(s)**：交付工具 `present_files` 会拒绝（invalid-link）。正确做法是把它写进路书网页的按钮 href（HTML 中 `&` 要转义为 `&amp;`，构建脚本已自动处理），发布网页后交付 https 链接。
3. **里程不要信用户给的表格或直线估算**，必须逐段驾车实测。真实案例：用户表"丽江→广南 480km"，实测 863km（低估 80%）；"广南→阳朔 380km"，实测 804km（低估 112%）。
4. 景区节点 geo 不到时，改用景区大门/游客中心全称或就近城镇锚点。
5. 驾车时长是理想路况，节假日需人工上浮（拥堵省界、热门景区周边按 +20%~40% 估）。
6. **境外目的地查不到数据**（2026-09 实测泰国）：`maps_text_search`、`maps_geo` 搜"大皇宫"返回的是深圳的地点；
   `maps_around_search`、`maps_regeocode` 用曼谷坐标查返回空；`maps_weather` 查"曼谷"返回 null。因此：
   - 境外的里程、天气、景点要改用网络搜索，并注明来源；天气用历年同期气候。
   - 行程地图仍可生成：`maps_schema_personal_map` 要求每个点都有 `poiId`，境外点填占位值 `"0"`，
     经纬度自己核实后填（境外不做 GCJ-02 偏移，直接用 WGS-84）。国内的点（如出发机场）照常用 text_search 的真实 poiId。
     这样生成的链接在电脑上无法验证，交付时要请用户在手机上试一下，并在页面注明"位置可能差几百米"。

7. **季节性/分时段限行的道路会被绕开**（2026-09 实测独库公路北段）：`maps_direction_driving` 从独山子到那拉提
   绕走连霍高速，测出 500–600 公里。做法：用 `maps_text_search` 找路上的地点（哈希勒根隧道、乔尔玛旅游点、
   `独库公路` 道路坐标），分段测再相加（45 + 31 + 107 = 183 公里），并和公开资料（约 185 公里）核对；
   高德算不了的那一小段如实写"无法计算"。
8. **留意 POI 名里的状态**：text_search 返回的名字可能带"(暂停营业)"，如"新源那拉提机场(暂停营业)"。
   机场、景区、服务区要看一眼，别把停运的机场写成备用方案。
9. **QPS 限流**：连续快速调用会返回 `CUQPS_HAS_EXCEEDED_THE_LIMIT`，批量调用时每次间隔 1–1.5 秒。

## 没有加载 MCP 工具时

高德 MCP 刚配置、当前会话还没加载时，可以直接用 HTTP 调用（JSON-RPC）：

```bash
curl -s -X POST "https://mcp.amap.com/mcp?key=<KEY>" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"maps_weather","arguments":{"city":"成都"}}}'
```

返回是 SSE 格式，取 `data:` 行解析 JSON，结果在 `result.content[].text`。`method` 换成 `tools/list` 可以看全部工具和参数。
