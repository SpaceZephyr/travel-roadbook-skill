# Travel Roadbook Skill · 旅行路书规划

一个面向 AI Agent 的旅行规划 Skill：把一句"帮我规划国庆自驾""十一七天去泰国"变成**经过核实的行程**，并产出手机可打开的路书网页——简约的版式配上目的地的文化装饰，行程、路线、气温、花费都做成图，逐日行程可以一键生成长图发给同行的人。

## 工作流

1. **需求询问**：一次问齐出发地/目的地、日期天数、出行方式、人数构成、偏好与禁忌、预算。
2. **合理性质疑**：国内逐段用高德驾车规划实测里程（不信用户估算，实测低估是常态）；校验单日驾驶时长、高原海拔阶梯、节假日错峰；出境游核实入境政策、当季气候、开口程机票。
3. **信息采集**：天气（超出预报用历年同期气候）、景点美食、门票与只收现金的地方、分层穿搭。
4. **高德行程地图**：生成 `amapuri://` 路线链接（境外点用经纬度 + 占位 poiId）。
5. **构建网页**：填写结构化 JSON，由 `build_roadbook.py` 渲染成自包含手机端 HTML。
6. **发布交付**：发布到飞书或 claude.ai，必要时生成二维码。

## 路书网页模块

- 开头：标题 + 目的地文化线描装饰（泰国：寺庙山墙、莲花苞纹样）
- 七天一览：每天在哪座城、哪天坐飞机、哪天有夜市
- 路线示意图：城市按真实经纬度摆放，标出每段航程
- 高德地图"一键打开行程"按钮（含微信内打开指引、链接复制兜底）
- 气温区间图（写明是历年平均还是预报）
- 逐日行程：按上午/下午/晚上排，门票、吃什么、注意事项；城市名和日期带当地文字
- **生成长图**：把七天一览和逐日行程画成 PNG，预览后保存或分享
- 每日门票条形图 + 明细表、整趟花费区间图
- 出发前清单（带截止日期，可勾选）、穿着建议、注意事项、资料来源

示例：`travel-roadbook/assets/roadbook.sample.json`（2026 国庆，广州出发，清迈 4 天 + 曼谷 3 天）。

## 目录结构

```
travel-roadbook/
├── SKILL.md                        # 技能入口：触发条件与 6 步流程
├── references/
│   ├── amap-tools.md               # 高德 MCP 工具链、lineList 结构、实测坑（含境外无数据）、HTTP 直连
│   ├── planning-rules.md           # 行程合理性校验规则（含出境游）
│   ├── roadbook-spec.md            # 需求清单、JSON 字段、发布与交付流程
│   └── design-guide.md             # 页面设计原则、文化装饰、配色校验、图表与长图
├── scripts/
│   ├── build_roadbook.py           # 路书 JSON → 自包含 HTML（--fragment 输出 Artifact 片段）
│   └── make_qr.py                  # 发布链接 → 二维码 PNG
└── assets/
    └── roadbook.sample.json        # 路书数据示例（泰国 7 天）
```

## 安装

把 `travel-roadbook/` 目录放入 Agent 的技能目录（Claude Code 是 `~/.claude/skills/`，豆包工作是 `workspace/.user_skills/`），新会话中说"帮我做旅行/自驾路书""X 天去 Y 地怎么玩"即自动触发。

快速验证页面构建：

```bash
python3 travel-roadbook/scripts/build_roadbook.py travel-roadbook/assets/roadbook.sample.json roadbook.html
```

## 运行依赖

- 高德地图 MCP（`https://mcp.amap.com/mcp?key=<KEY>`）：地理编码、驾车规划、天气、POI 检索、行程地图。境外目的地查不到数据，改用网络搜索。
- 网络搜索：节假日、入境政策、门票价格、境外气候。
- 发布：豆包工作用 `lark-cli apps +deploy`；Claude Code 用 Artifact 发布（声明 `downloads` 能力以支持保存长图）。
- Python 3；二维码需 `pip install 'qrcode[pil]'`。网页运行时从 Google Fonts 加载字体，生成长图时从 cdnjs 加载 html2canvas。

## 设计原则

- 里程、天气、门票价格必须来自工具或可追溯来源，不编造；超出预报窗口的天气、浮动的票价、估算的预算显式标注口径。
- 页面简约：黑灰加 1–2 个区域色，颜色只用来区分真实类别；目的地特色靠少量线描装饰和当地文字，不靠色块。
- 非自驾场景（高铁/飞机 + 当地租车、公共交通）与出境游同样适用，写法见 `references/`。

## License

[MIT](LICENSE)
