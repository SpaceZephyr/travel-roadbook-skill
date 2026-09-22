# Travel Roadbook Skill · 旅行路书规划

一个面向 AI Agent 的旅行规划 Skill：把一句“帮我规划国庆自驾”变成**经过里程核实的行程**，并产出手机可打开的路书网页——高德地图一键打开、沿途天气、逐日路书、门票预算、穿着建议、注意事项，最终发布为可分享链接。

## 工作流

1. **需求询问**：一次问齐出发地/目的地、日期天数、出行方式、人数构成、偏好与禁忌、预算。
2. **合理性质疑**：逐段用高德驾车规划实测里程（不信用户估算，实测低估是常态）；校验单日驾驶时长、高原海拔阶梯、节假日错峰；“不想去 X 地”区分“可过境”与“完全绕开”，两条线里程都算给用户。
3. **信息采集**：沿途天气、POI、景点美食、门票预约与价格、分层穿搭。
4. **高德行程地图**：生成 `amapuri://` 路线链接。
5. **构建网页**：填写结构化 JSON，由 `build_roadbook.py` 渲染成自包含手机端 HTML。
6. **发布交付**：发布为 doubao-html 网页链接，必要时生成二维码。

## 路书网页模块

- 高德地图“一键打开行程”按钮（含微信内打开指引、链接复制兜底）
- 沿途天气速览（数据查询日期与预报窗口说明）
- 逐站路书时间轴：天气 / 景点 / 美食 / 门票 / 贴士
- 门票与花费参考表（票价、预约提示、人均合计）
- 穿着建议（按场景与最低夜温分层）
- 注意事项（行车安全、高反、车况、预约、应急）

## 目录结构

```
travel-roadbook/
├── SKILL.md                        # 技能入口：触发条件与 6 步流程
├── references/
│   ├── amap-tools.md               # 高德 MCP 工具链、lineList 结构与实测坑
│   ├── planning-rules.md           # 行程合理性校验规则
│   └── roadbook-spec.md            # 需求清单、JSON 字段、发布与交付流程
├── scripts/
│   ├── build_roadbook.py           # 路书 JSON → 自包含 HTML
│   └── make_qr.py                  # 发布链接 → 二维码 PNG
└── assets/
    └── roadbook.sample.json        # 路书数据模板（字段示例）
```

## 安装

把 `travel-roadbook/` 目录放入 Agent 的技能目录（例如豆包工作的 `workspace/.user_skills/`），新会话中说“帮我做旅行/自驾路书”“X 天去 Y 地怎么玩”即自动触发。

快速验证页面构建：

```bash
python3 travel-roadbook/scripts/build_roadbook.py travel-roadbook/assets/roadbook.sample.json roadbook.html
```

## 运行依赖

- 高德地图 MCP：地理编码、驾车规划、天气、POI 检索、行程地图
- 豆包 html 技能（`shot.py` 截图自检）与 `lark-cli apps +deploy`（网页发布）
- Python 3；二维码需 `pip install 'qrcode[pil]'`

## 设计原则

- 里程、天气、门票价格必须来自工具或可追溯来源，不编造；超出预报窗口的天气、浮动的票价显式标注口径。
- 非自驾场景（高铁/飞机 + 当地租车、公共交通）同样适用，字段写法见 `references/roadbook-spec.md`。

## License

[MIT](LICENSE)
