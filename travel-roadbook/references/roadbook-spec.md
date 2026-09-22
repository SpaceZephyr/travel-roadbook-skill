# 路书内容规范与发布流程

## 一、需求询问（动手前一次问清）

用提问工具（豆包工作是 `interaction.ask`，Claude Code 是 `AskUserQuestion`）一次性问齐关键项（最多 4 个问题，可多选），不要边做边问：

1. **出发地、目的地**（单一目的地/环线/多目的地）、**具体出发日期与总天数**。
2. **出行方式**：自驾（车型、能否接受单日 700km+ 赶路日、几位司机）/ 高铁或飞机+当地租车 / 公共交通。
3. **人数与构成**：成人、老人、小孩；是否有人未上高原、慢性病或行动限制。
4. **旅行目的与偏好**：自然风光/人文古迹/美食/摄影/亲子/休闲；必去清单、**明确不想去的地方**（并澄清是"可过境"还是"完全绕开"，见 planning-rules.md）；住宿档次与总预算。

出境游把目的地的选项和当季情况一起给出（例如"10 月初泰国安达曼海一侧海况不稳，北部天气最好"）。
用户给了现成行程表/文档时，先完整读取，再进入核实环节，不要让用户重述。

## 二、路书 JSON 字段

完整示例：`assets/roadbook.sample.json`（国庆 7 天清迈 + 曼谷）。复制后逐项改写。
构建：`python3 scripts/build_roadbook.py <data.json> [out.html] [--fragment]`。
设计原则与换国家的做法见 `references/design-guide.md`。

| 字段 | 说明 |
|---|---|
| `title` | 网页标题（浏览器标签、长图文件名默认值），2–4 个词的名字 |
| `eyebrow` / `h1[]` / `lede` | 页眉小字；主标题按词组拆成数组（防止城市名断行）；一段话概括行程 |
| `theme.ornament` | 文化装饰预设：`thai` / `none`，新国家在脚本 `ORNAMENTS` 里加 |
| `theme.ornament_color` | 装饰线条颜色 `{light, dark}` |
| `theme.local_lang` | 当地文字语言：`th` / `ja` / `ko` / `vi`，决定字体 |
| `theme.farewell` | 页脚的一路平安 `{local, zh}`，可省略 |
| `regions{}` | 区域（通常是城市）：`name`、`local`（当地文字名）、`light`/`dark` 两套颜色（必须过配色校验） |
| `overview[]` | 七天一览：`date`、`weekday`、`region`、`flight`、`night`、`local_num`（当地数字）、`tip`（悬停说明） |
| `route` | 路线示意图：`nodes[]`（`id`、`name`、`lon`、`lat`、`region`、`note`、`label_dx/dy`）、`legs[]`（`from`、`to`、`label`、`bend`、`dashed`、`label_dx/dy`）、`lines[]`（纬线，如北回归线）、`caption` |
| `amap_uri` / `amap_note` | 高德行程链接与说明；空字符串则不显示按钮 |
| `weather` | `note`、`rows[]`（`name`、`sub`、`region`、`low`、`high`、`tip`）、`fine`（数据口径） |
| `plan.cities[]` | `region`、`span`、`intro`、`days[]` |
| `days[]` | `date`、`weekday`、`local_label`、`title`、`plan[[时段, 内容]]`、`meta[[标签, 内容, 可选提醒]]` |
| `plan.transits[]` | 城市之间的转场：`after_city`（第几个城市之后，从 0 数）、`date`、`title`、`text` |
| `tickets` | 每日门票条形图：`note`、`unit`、`max`、`ticks`、`rows[]`（`label`、`region`、`value`、`text`、`tip`；没有 `value` 就只显示 `text`）、`total_label`、`total`、`table[[日期, 地方, 金额]]` |
| `budget` | 花费区间图：`max`、`ticks`、`prefix`、`rows[]`（区间用 `min`/`max`，单值用 `value`）、`total`、`fine` |
| `todo` | 出发前清单：`key`（本机存储键）、`items[]`（`by`、`urgent`、`text`、`sub`） |
| `wear[]` / `tips[]` | 穿着（`{title, text}`）、注意事项（字符串）；`wear_heading` / `tips_heading` 可改标题 |
| `sources[]` / `sources_label` / `footer_note` | 资料来源链接、查询日期、数据口径说明 |
| `share` | 长图：`filename`、`footer`（长图底部一句话） |

文本里写 `{{สวัสดี}}` 会用当地文字字体显示。所有文本都会转义，不要写 HTML。

内容口径（硬要求）：

- **不编造**：天气、里程、门票价格必须来自工具或可追溯来源；查不到就写"以官方为准"或留空，禁止杜撰具体数字。
  预算这类估算要在页面上写明"粗估，不是报价"。
- 门票价格标注查询日期与"可能调整"；区间车、索道、缆车等二次消费单列。出境游标出"只收现金"的地方和汇率及其日期。
- 天气超出预报窗口时用历年同期气候，并写明"不是预报"。
- 美食按当地真实特色与**当季**写；每站 3–4 项即可。
- 穿着按**最低温 + 场景**给建议；出境游补上宗教场所着装要求。
- 每天按时段（上午/下午/晚上）写，时段样式一致，不给某个时段单独上色。
- 出境游补上入境政策（免签/签证、入境卡），以使馆或官方来源为准并写查询日期。

## 三、构建与自检

1. 建语义化任务目录（如 `thailand-roadbook/`），JSON 与输出 HTML 放其中，文件名语义化（如 `泰国国庆路书.html`）。
2. 运行 `build_roadbook.py` 生成单文件 HTML。
3. 看一次移动端截图（任选其一）：
   - 豆包工作：`python3 <html技能目录>/scripts/shot.py <html路径>`，关注 `consoleErrors`、`horizontalOverflow`。
   - Claude Code：`"<Chrome>" --headless=new --window-size=500,1500 --screenshot=out.png file://<html>`（Chrome 无头窗口最窄 500px）。
   重点看：标题是否断词、路线图标签是否压线或出界、图表数值标签是否重叠。

## 四、发布成手机可打开的链接（任选其一）

**A. 飞书（豆包工作环境）**

1. `cd` 到 HTML 所在目录（路径只接受相对路径）。
2. 首发：`lark-cli apps +deploy --file-path ./xxx.html`；记住返回的 `app_id`。迭代：加 `--app-id app_xxx` 复发布（链接不变）。
3. 用 `lark-cli apps +release-get --app-id <id> --release-id <rid>` 轮询（间隔 ≥3s）到 `status=finished`，取 `online_url`；`curl -sL -o /dev/null -w "%{http_code}"` 验证 200。

**B. claude.ai Artifact（Claude Code 环境）**

1. 用 `--fragment` 构建（Artifact 会自动包 `<html>` 外壳）。
2. 用 Artifact 工具发布，首次带 `icon: "map"` 和一句 `description`，并声明 `capabilities: {"downloads": true}`（长图"保存图片"要用）。
3. 之后同一路径重新发布即可更新，链接不变。链接默认私有，提醒用户用页面的 Share 菜单分享给同行的人。

## 五、二维码（可选，用户要手机扫码时）

`python3 scripts/make_qr.py <online_url> 二维码.png`（依赖 `pip3 install 'qrcode[pil]'`）。
**编码发布后的 https 链接**，不要编码 amapuri（手机相机扫自定义协议不可靠）。

## 六、交付

- 交付发布后的 https 链接（和二维码 PNG，如有）。amapuri 原始链接只能写在网页按钮里，不能作为交付链接。
- 最终回复简短：页面有哪些模块、数据查询日期；远期天气、价格、航班时刻等不确定项一句话提示；
  没在手机上实测过的功能（高德按钮、长图保存）要请用户自己试。
