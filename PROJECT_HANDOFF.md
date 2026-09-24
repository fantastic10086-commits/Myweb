# PI Manager 最新项目交接

更新日期：2026-09-24。后面的 2026-09-09 静态检查记录仅供历史参考；其中分支、版本、未提交状态、部署情况与待办不代表当前状态。

## 持续协作要求（用户于 2026-09-17 确认）

- 每次修改完成并验证后，提交并推送至既有 GitHub 仓库 `origin`（`fantastic10086-commits/Myweb`）。部署完成后更新交接记录并一并推送；保持正常推送，不强制覆盖远程历史。现有服务器部署授权继续有效，部署前备份，保留业务数据。

## 最新接续（2026-09-24 23:27 客户文件资料库）

- 客户详情“文件资料”页签已从占位入口改为正式文件库：每个客户有通用“客户资料”目录，每份有效 PI 自动显示为订单子文件夹；关联订单进入回收站后，文件转入历史订单保留区，不丢失。
- 支持一次最多上传 8 个文件、单文件最大 20 MB，可上传 JPG/PNG/GIF/WebP、PDF、Word、Excel、PPT、TXT、CSV 和 ZIP；图片、PDF 可在线查看，其他文件直接下载。保存随机内部文件名并保留原始中文文件名、说明、大小、上传人和时间。
- 文件访问跟随客户权限，业务员不能查看或下载他人客户文件；上传目标 PI 必须属于当前客户。图片、PDF、Office、文本及压缩文件均做内容校验，拒绝空文件、伪造格式、超大文件和异常压缩内容。上传和删除写入审计日志，删除采用软删除并保留物理文件，为后续恢复提供基础。
- 文件继续保存在现有受管 uploads 目录，生产备份脚本已覆盖该目录。本地 76 项业务/安全测试通过，新增通用/订单目录、中文文件名、在线查看/下载、跨客户隔离、非法格式、错误目录、软删除和审计回归测试。
- 业务提交 `f7c3924`；线上 `/opt/pi-manager/releases/20260924232704`，服务 active，HTTPS 登录页 200，生产库确认 `customer_files` 表存在，生产标签 `prod-20260924232704`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260924_232614.tar.gz`（禁用 OSS 上传与清理），原业务数据及上传文件保留。

## 最新接续（2026-09-24 23:15 客户列表操作区精简）

- 客户列表操作区改为“详情”“新建 PI”“更多”：客户名称和详情按钮都进入已有客户详情页，编辑入口统一保留在详情页；转交客户和删除客户收进更多菜单，减少每行按钮数量。
- 转交仍仅管理员可见并复用原转交窗口；删除仍要求输入完整客户名称确认并进入回收站，权限、审计和数据恢复规则未改变。跟进列继续显示客户类型、状态和下次联系日期，逾期及当天提醒样式保留。
- 本地 75 项业务/安全测试通过，增加销售员列表入口、编辑入口移除、转交权限和删除入口回归断言。业务提交 `9f54746`；线上 `/opt/pi-manager/releases/20260924231503`，服务 active，HTTPS 登录页 200，生产标签 `prod-20260924231503`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260924_231411.tar.gz`（禁用 OSS 上传与清理），业务数据和历史记录保留。

## 最新接续（2026-09-24 23:04 客户详情成交产品汇总）

- 客户详情新增顶部四项概览：累计成交额、有效 PI 数量、最近成交日期和下次联系日期；右侧业务区整理为跟进记录、订单记录、成交产品、文件资料四个页签，订单筛选后自动显示订单页签。
- 成交产品按产品库 ID 汇总全部未删除 PI，显示订单中最近保存的产品图片、名称、编码和规格，以及累计数量、不同订单数、最近三位单价、币种、日期和 PI 编号；产品改名仍保持同一产品汇总，不写入或改动历史 PI。订单列表同时改为显示 PI 保存的产品名称快照。
- 文件资料页签暂时只作为下一阶段客户文件夹及订单子文件夹入口说明，尚未开放上传，避免创建不完整的数据结构。
- 本地 75 项业务/安全测试通过，新增客户成交产品汇总、最近产品快照、累计数量、币种单价和客户权限隔离回归测试。业务提交 `94629fc`；线上 `/opt/pi-manager/releases/20260924230442`，服务 active，HTTPS 登录页 200，生产标签 `prod-20260924230442`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260924_230332.tar.gz`（禁用 OSS 上传与清理），业务数据、上传、PDF、设置和模板保留。

## 最新接续（2026-09-24 22:47 客户分类与跟进第一阶段）

- 客户采用精简分类：普通客户由累计成交额自动显示为潜在/成交客户，重点客户和无效客户由人工标记；跟进状态仅保留需要跟进、等待客户回复和暂不跟进。历史客户未批量改写，新增字段使用安全默认值。
- 客户详情页新增跟进记录时间线和新增跟进表单，记录联系日期、沟通内容、状态、下次联系日期和跟进人。下次日期按潜在 7 天、成交 30 天、重点 7 天、等待回复 3 天自动建议，业务员可修改；无效或暂不跟进不产生提醒。管理员可在系统设置调整四个默认周期。
- 客户列表合并联系信息、只新增一个紧凑跟进列，支持客户类型、今日跟进、逾期、等待回复及暂不跟进筛选；首页增加“今天需要跟进”和“已经逾期”。业务员仍只能查看和记录自己名下客户，越权 POST 返回 403；新增跟进写入审计日志。
- 本地 74 项业务/安全测试通过；生产数据库确认 `customer_follow_ups` 表及客户跟进字段存在，服务 active，HTTPS 登录页 200。业务提交 `7dafb02`；线上 `/opt/pi-manager/releases/20260924224701`，生产标签 `prod-20260924224701`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260924_224608.tar.gz`（禁用 OSS 上传与清理），业务数据、上传、PDF、设置和模板保留。
- GitHub SSH 已于 2026-09-24 恢复，`main` 已推送至 `73fe1f1`，生产标签 `prod-20260920171625` 和 `prod-20260924224701` 均已同步到 `origin`。

## 最新接续（2026-09-20 17:16 编辑 PI 产品选择弹窗）

- 修复已有 PI 重新编辑时，新增产品仍使用旧的小型搜索下拉框、没有弹出完整“选择产品”窗口的问题。编辑页现与新建 PI 一致，支持按产品名、中文名、编码或规格搜索，分页、跨页多选及一次批量加入。
- 当前 PI 已有产品在弹窗中显示“已加入”并禁止重复勾选；新选产品按勾选顺序追加，不改动已有产品的名称、编码、规格、图片、价格、数量和排序，也不刷新页面。快速新增产品入口保留。
- 下游业务保护继续生效：已有采购、装箱等记录时，产品选择入口随结构字段锁定；只有管理员完成原有解锁流程后才能打开和加入产品，弹窗加入逻辑也再次检查锁定状态。
- 本地 73 项业务/安全测试通过；新增编辑页弹窗、跨页批量逻辑、旧下拉移除及结构锁保护回归断言。业务提交 `32bc951`；线上 `/opt/pi-manager/releases/20260920171625`，服务 active，HTTPS 登录页 200，生产模板确认包含产品弹窗。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_171528.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。
- GitHub 推送已于 2026-09-24 补齐，生产标签 `prod-20260920171625` 已同步到 `origin`。

## 最新接续（2026-09-20 15:58 精简装箱单全文字加粗增强）

- 用户要求精简版所有文字再次加粗。Excel 继续在上传模板样式应用后强制所有实际文字单元格使用粗体；固定 100×150 mm PDF 在 Noto Sans CJK Bold 真粗体基础上，对标题、页次、PI/业务员/箱号、产品明细、数量和尺寸重量字段全部采用 0.22 pt 偏移的双重强化绘制，提高小型标签和热敏打印的字重。
- 字号、箱号自动重排、箱内产品、100×150 mm 页面尺寸及选择部分箱子导出逻辑不变；未修改业务数据或已上传模板。
- 本地 73 项业务/安全测试及 5 项导出测试通过；服务器隔离数据库装箱 Excel/PDF 专项通过，并确认强化绘制函数生效。服务 active，内部登录 HTTP 200。
- 业务提交 `7e0b792`；线上 `/opt/pi-manager/releases/20260920155857`，标签 `prod-20260920155857`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_155807.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。

## 最新接续（2026-09-20 15:50 装箱顺序、箱号及精简版字体）

- 箱号改为完全跟随当前箱子顺序：前端加载、移动、新增和删除后立即重排为 1、2、3……；后台保存忽略客户端旧箱号并按提交顺序再次规范，防止绕过。页面数据、完整 A4、精简 Excel/PDF 均以当前排序位置作为箱号，因此第 N 页固定为第 N 箱；只选部分箱子时保留其在完整装箱单中的正式序号。
- 精简 100×150 Excel 与 PDF 全部文字改为加粗并适当增大；PDF 使用服务器 Noto Sans CJK Bold 真粗体并保持精确 100×150 mm。上传精简 Excel 模板继续控制 Excel 版式，但最终文字保持最低 10 pt 粗体、标题 17 pt；模板管理页已明确说明固定尺寸 PDF 不读取 Excel 模板，避免误解为上传未生效。
- 未批量改写历史业务数据；旧的非连续箱号在页面和导出时立即按当前顺序规范，管理员下一次保存装箱单后同步写回 1…N。生产只读验证 `PI-20260920-001` 已从原 3、1、4、2…输出为第1箱/第1页至第9箱/第9页，箱内产品仍保持最新拖动后的顺序和归属。
- 本地 73 项业务/安全测试及 5 项导出测试通过；服务器隔离数据库装箱保存、排序、双管理员、Excel/PDF 专项通过。生产模板实测标题 17 pt 粗体、明细 10 pt 粗体，服务 active，内部登录 HTTP 200。
- 业务提交 `649423e`；线上 `/opt/pi-manager/releases/20260920155055`，标签 `prod-20260920155055`。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_155004.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。

## 最新接续（2026-09-20 14:06 PI 下游解锁表单修复）

- 修复编辑已有下游记录的 PI 时，即使管理员勾选影响确认并填写至少 5 个字符原因，后台仍反复提示未确认的问题。根因为两个解锁控件显示在 PI 表单之前、未归属于表单，前端检查虽通过但浏览器没有提交字段；现已用 HTML `form` 关联明确绑定到 `pi-form`，页面布局及原校验规则不变。
- 增加渲染回归断言，确保解锁确认和修改原因始终归属 PI 表单；既有后台双重校验、下游数量保护和审计日志保留。
- 本地 73 项业务/安全测试通过；服务器隔离数据库的 PI 下游保护、解锁修改、审计及关联保留专项测试通过。
- 业务提交 `4dc0889`；线上 `/opt/pi-manager/releases/20260920140610`，标签 `prod-20260920140610`；服务 active，内部登录 HTTP 200。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_140502.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。

## 最新接续（2026-09-20 13:49 新建 PI 币种必填）

- 新建 PI 的币种改为正式生成必填项：页面增加红色必填标记和“请选择币种”空选项，提交时前端明确提示；后台独立校验 USD/RMB，缺失或非法值均在创建 PI、生成文档前拒绝，不能绕过页面校验。
- 选择收款账户后仍会按账户币种自动填入并锁定币种；清空账户会同时清空币种，避免沿用无效值。草稿继续允许暂不填写，恢复草稿时保留空值，转为正式 PI 时必须补齐。既有 PI、业务数据及历史文件未修改。
- 本地 73 项业务/安全测试通过，页面渲染后的全部内联脚本语法通过；服务器隔离数据库的正式创建币种校验及无币种草稿专项测试通过。
- 业务提交 `ea50fb1`；线上 `/opt/pi-manager/releases/20260920134907`，标签 `prod-20260920134907`；服务 active，内部登录 HTTP 200。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_134823.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。

## 最新接续（2026-09-20 11:39 产品翻译 429 修复）

- 新建/编辑产品的翻译报错确认为匿名 Google 公共端点对服务器 IP 返回 HTTP 429；已移除该不稳定调用。配置 `GOOGLE_TRANSLATE_API_KEY` 时使用正式 Google Cloud Translation v2，否则使用 MyMemory 翻译通道；上游 429/5xx/网络异常自动短暂退避重试。
- 新增 `translation_cache` 持久缓存，英文名称按 Unicode、大小写及空白归一后复用；应用内并发请求串行并在锁内二次查缓存，避免重复点击形成上游请求。上游失败统一返回 503 和中文可重试提示，不再暴露原始英文异常；前端增加 12 秒超时并保证按钮恢复。
- 本地 72 项业务/安全测试通过，产品页脚本语法通过；服务器隔离数据库两项缓存/故障专项通过，生产库确认缓存表存在，服务器真实翻译 `CONNECTOR FEMALE 10-25 MM` 成功返回中文。
- 业务提交 `e1602bc`；线上 `/opt/pi-manager/releases/20260920113855`，标签 `prod-20260920113855`；服务 active，内部登录 HTTP 200。部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_113616.tar.gz`（禁用 OSS 上传与清理），业务数据、上传和模板保留。

## 最新接续（2026-09-20 13:15 快速新增产品翻译及中文名称必填）

- 新建 PI、编辑 PI 的快速新增产品弹窗增加中文名称及翻译按钮，复用 `/api/translate` 的持久缓存、退避和中文错误提示；翻译期间锁定添加按钮，翻译结果可手动修改，快速新增接口保存并返回中文名称，不刷新 PI 页面。
- 所有新建产品入口统一要求中文名称：普通新增页面前端 required 加后台校验；两个 PI 快速新增弹窗前后端校验；Excel 导入按表头识别中文名称，新产品缺失时整批回滚并指出行号，已有产品导入更新仍兼容旧表。历史产品编辑不强制补齐，不批量修改业务数据。
- 本地 73 项业务/安全测试通过，新建 PI、编辑 PI、普通产品新增三个渲染页面的全部内联脚本语法通过；服务器隔离数据库三个专项测试通过。
- 业务提交 `672b0d8`；线上 `/opt/pi-manager/releases/20260920131521`，标签 `prod-20260920131521`；服务 active，内部登录 HTTP 200。最终部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260920_131339.tar.gz`（禁用 OSS 上传与清理）。两次未通过健康检查的发布均由更新脚本自动恢复旧版：首次发布包漏带内置装箱模板，第二次 Git 归档解压源目录为 0700 导致服务账户无法进入；最终改用完整 Git 归档并将源目录设 0755 后部署成功。业务数据、上传和模板保留。

## 最新接续（2026-09-18 15:31 新建 PI 收款账户必填）

- 用户要求新建 PI 收款账户必填：前端红星、required 及两种生成提交入口账户检查；后台 pi_create 对管理员/业务员统一要求有效的账户 ID，不接受缺省、非法或不存在的账户，创建前拒绝。不影响编辑旧 PI、导出保留快照及草稿保存，草稿转正式仍需选择账户。
- 本地 70 项业务/安全测试通过，页面渲染 JS 语法通过；两个既有正式创建测试补有效账户，新增管理员/业务员空账户、非法 ID、不存在 ID 均拒绝且不创建 PI/不生成文档、无账户草稿仍可保存测试；服务器临时数据库专项通过。
- 业务提交 4073e2e；线上 /opt/pi-manager/releases/20260918153049，标签 prod-20260918153049；服务 active，内部登录 HTTP 200。部署前备份 /var/lib/pi-manager/backups/pi-manager_20260918_152841.tar.gz（禁用 OSS 上传与清理），业务数据及模板保留。

## 最新接续（2026-09-18 15:23 导出账户换行误判修复）

- 用户授权修复反复选择账户的问题。新增 _normalized_bank_text，仅统一 CRLF/CR/LF 并保留原边界 strip，不忽略银行字段内容差异；应用于导出表单比较、旧 PI 账户唯一匹配及银行快照一致性校验。
- 不选择新账户时导出副本沿用原银行文字和关联，不把浏览器提交的换行写回；账户品牌、公司抬头、账户存在性和真实银行内容修改拦截均保留，旧数据不批量改写。
- 导出页显示“原 PI 收款账户”及所属品牌，保留选项改为“使用原 PI 收款信息”，说明匹配即可直接导出及切换仅用于本次副本，不修改原 PI。
- 本地 69 项业务/安全测试通过；新增 CRLF/CR/LF 真正 Excel 导出、原账户/文字/版本保留、旧账户匹配、真实银行修改拒绝测试；导出页渲染 JS 语法通过，服务器临时数据库同专项通过。未做交互浏览器验收。
- 业务提交 06c6dd2；线上 /opt/pi-manager/releases/20260918152258，标签 prod-20260918152258；服务 active，内部登录 HTTP 200。部署前备份 /var/lib/pi-manager/backups/pi-manager_20260918_152128.tar.gz，禁用 OSS 上传与清理，业务数据和模板保留。

## 最新接续（2026-09-18 00:08 PI 三位单价）

- 新建/编辑 PI 产品行单价输入 step=0.001、显示及隐藏提交值三位；产品选择器、快速新增、复制行、草稿恢复、币种/汇率换算沿用三位单价。新增 static/pi_prices.js，价格归一三位，金额按整数千分位计算并取两位，逐行汇总，避免页面合计与后台逐行保存不一致；编辑页共享同样规则。
- 后台提交与导出副本单价用 Decimal ROUND_HALF_UP 归一三位，行金额取两位；导出页单价输入、PI 详情/HTML 预览及采购页 PI 单价三位（采购成本与其他业务金额规则不变）。
- 模板渲染不再预先将 item.unit_price 取两位；所有内置/管理员替换的模板精确单价占位符在生成副本设 #,##0.000，带文字单价占位符三位；源模板及布局不改动，旧 PDF/Excel 需重新导出才应用更新。旧 ReportLab PDF 与旧 Excel 生成器单价三位，示例模板单价格式三位，行金额及订单合计继续两位。
- 修正输入和隐藏值两位导致第三位丢失、模板渲染丢精度、导出页二次损失及前端未逐行取整的合计差异。未批量修改历史订单、产品库或已生成旧文件。
- 业务提交 fc425c8；线上 /opt/pi-manager/releases/20260918000810，标签 prod-20260918000810；active、内部登录 HTTP 200。部署前备份 /var/lib/pi-manager/backups/pi-manager_20260918_000704.tar.gz，禁用 OSS 上传与清理，线上替换模板和业务数据保留。
- 本地 68 项业务/安全、5 项图片导出测试通过；新建/编辑/导出页渲染脚本语法及 JS 千分位/半分金额检查通过；服务器隔离数据库测试验证 0.005 与 1.235 保存、金额、两种模板/旧格式替换模板的数值与三位格式通过。未做交互浏览器验收。

## 最新接续（2026-09-18 00:02 线上替换模板交易条款修正）

- 用户截图 PI-20260917-004 仍显示 Customer Notes，根因为 document_templates 的 system-default 行 filename 已由管理员替换为 9298dc325c2941c18d745b7069cb4d47.xlsx；启动保留替换模板，故此前内置 assets 模板两处修改未作用到实际替换版。
- 下载当前替换模板，使用 artifact-tool 编辑 A12/B12 为 Trade Terms: / {{price_terms}}；为保留原生格式，转入原 ZIP 的 sharedStrings.xml，仅两个文本变化，其他所有组件字节相同。修正文件 outputs/pi-live-trade-20260917/default_pi_template.xlsx（输出目录不提交）。已更新线上原替换文件名，既有版式、抬头、其他字段不变；无需发布新代码。内置源模板已包含正确贸易条款。
- 操作前完整备份 /var/lib/pi-manager/backups/pi-manager_20260917_235801.tar.gz（禁用 OSS 上传和清理），另留原替换模板 /var/lib/pi-manager/backups/default-template-before-trade-terms-20260917.xlsx。
- 仅重新生成 PI-20260917-004 的现有 PDF/Excel 文件，校验 A12 Trade Terms、实际 PDF 包含 Trade Terms 且无 Customer Notes；数据库事务回滚，不修改金额、版本或条款。该 PI price_terms 当前为空，未擅自填 FOB。文件归属 pi-manager、0640，服务 active、内部登录 HTTP 200。其他旧 PI 文件未批量重生成，需要重新导出才应用更新。

## 最新接续（2026-09-17 系统盘清理）

- 用户授权清理确认可清理文件后，检查 `/tmp/pi-manager-*`，仅选择含 app.py 和 ops/update_server.sh 的部署副本，排除符号链接，核对 /proc 进程工作目录、打开文件及内存映射无引用；删除 72 个未使用临时部署目录，并运行 apt-get clean 清理下载的软件包缓存。
- 释放约 2.5 GiB；df 系统盘由 17G/49G（35%）降至 14G/49G（30%），可用 34G；/tmp 由 2.4G 降至 288M，APT archives 由 370M 降至 40K。
- 未删除任何正式业务数据、上传、PDF、备份（仍 7.1G）或 /opt/pi-manager/releases 部署版本。服务 active，内部登录 HTTP 200；无需重启或部署代码。线上版本仍为 20260917230922。

## 最新接续（2026-09-17 23:09 拖拽排序及 PI 草稿已部署）

- 用户明确确认上传源代码归档至 `root@47.76.221.183` 并部署后，已完成上线；本条取代下方待部署状态。
- 业务提交 `6f32185`，线上 `/opt/pi-manager/releases/20260917230922`，标签 `prod-20260917230922`；服务 active，内部登录 HTTP 200。
- 部署前补充最新备份 `/var/lib/pi-manager/backups/pi-manager_20260917_230847.tar.gz`，禁用 OSS 上传与清理，既有业务数据、上传和设置保留。
- 本地 67 项业务/安全及 5 项图片导出测试通过；服务器临时数据库草稿不完整保存/恢复、图片权限隔离、版本冲突及转正防重复专项通过。拖拽模拟和页面脚本语法通过，未做交互浏览器验收。

## 最新接续（2026-09-17 23:08 拖拽排序及 PI 草稿：待部署）

- 新建 PI 左侧排序按钮改为拖拽手柄，指针拖动显示虚线占位，靠近屏幕边缘自动滚动；真实 DOM 移动保留输入和 File，支持方向键及取消恢复，提交沿用 product_order/sort_order。编辑 PI 原上下移按钮保留。
- 新增独立 pi_drafts 表，按创建用户隔离，JSON 保留未完成字段、产品行、复制行、顺序及独立图片；暂存不校验正式必填项、不生成 PDF、不进入 PI 或业务统计。新建页“我的草稿”查看、继续填写和删除，保存无整页刷新。
- 草稿保存及转正检查版本；转正沿用原 PI 校验和文档生成，成功关联正式 PI 并移出草稿列表，重复提交返回已生成 PI，生成失败事务回滚保留草稿。图片来源只允许当前草稿已有引用，上传沿用原图校验；草稿图片按 owner 授权原图/私有缩略图。替换/删除草稿不清理上传，避免破坏历史共享引用。
- 业务提交 `6f32185`；本地 67 项业务/安全、5 项图片导出测试通过，页面渲染 JS 语法、模拟拖拽/键盘/取消/File 保留检查通过。未做交互浏览器验收。
- 部署前服务器备份 `/var/lib/pi-manager/backups/pi-manager_20260917_230601.tar.gz`，禁用 OSS 上传与清理。
- 上传 `/tmp/pi-manager-drafts.tar` 至 `root@47.76.221.183:/tmp/pi-manager-drafts.tar` 被自动审批拒绝：认为当前可信消息未明确授权具体外部目的地及源代码归档外传。未绕过，尚未部署，线上仍为 `20260917225640`；需要用户明确确认该目的地上传项目源代码并部署后继续。本地归档已生成。

## 最新接续（2026-09-17 22:56 PI 产品行图片）

- 新建/编辑 PI 的产品行增加图片区域及上传/更换、恢复产品库图片、移除按钮，区域支持 Ctrl+V / ⌘V 粘贴；本地预览，不异步刷新整页。使用原生 multipart 行内文件输入，复制行通过 DataTransfer 保留当前 File，排序不重建输入；格式 JPG/PNG/WebP/GIF，单张 12 MB，后端再验证实际图片及 2500 万像素上限。
- PIItem.image_override 可空新增列，None 兼容原产品库图片，空字符串表示本单不显示图片；display_image 统一读取。保存、预加载、复制行及复制 PI 保留本单覆盖，产品库图片不修改。引用已保存图片仅限当前 PI 的已有图片，拒绝跨 PI 任意文件引用。更换、移除不删除原上传，防止破坏共享引用或历史资料。
- 原图/缩略图路由新增 PI 归属访问校验，其他业务员及已删除 PI 无权访问独立图片，PI 私有缩略图不缓存。已有下游记录的图片修改沿用结构锁及解锁原因要求，保留明细 ID。
- 默认文档生成/导出工作台/模板渲染/旧 PDF 生成/PI 明细/装箱数据/采购数据均读取本单图片；旧 PI 没有覆盖时继续显示产品库图。既有导出品牌校验及其他功能保留。
- 业务提交 `24afdbc`；线上 `/opt/pi-manager/releases/20260917225640`，标签 `prod-20260917225640`。服务 active，内部登录 HTTP 200。
- 部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260917_225405.tar.gz`，禁用 OSS 上传与旧备份清理。生产业务数据及原产品库图片保留。
- 本地 66 项业务/安全及 5 项图片导出测试通过；两个页面渲染 JS 语法及模拟图片选择/复制/恢复/移除/粘贴/无效文件保留/结构锁检查通过；服务器临时数据库 2 项上传/隔离权限/复制恢复/真实 Excel 嵌图/无效文件及跨 PI 引用测试通过。未做交互浏览器验收。

## 最新接续（2026-09-17 16:55 收款账户多品牌及导出拦截）

- 收款账户所属品牌改为 KLISTA / QISUO 复选框，至少一个，可同时选两个。复用 brand 字段规范逗号存储，旧单品牌原值兼容、不批量修改；列表、字段管理显示全部品牌，API 增加 brands 数组。新建/编辑 PI 选择双品牌账户时保持有效公司选择，避免把逗号品牌当作公司值。
- 新增可空 PI.bank_receiving_account_id，选择账户保存其 ID，复制 PI 保留关联；不改写旧 PI 或历史银行快照。旧 PI 唯一匹配账号/银行/收款人或完整/旧式银行文字，重名/重复身份不随意选第一条，无法确认或账户已删除时阻止导出并提示补充账户。
- 导出工作台前端弹窗并阻止请求，后台独立校验：公司不在账户品牌中、账户品牌为空、账户无法确认、无效账户 ID、非标准公司名称、模板顶部固定 KLISTA/QISUO 抬头冲突均拒绝预览及 PDF/Excel 导出。旧 PDF/Excel 下载路由也校验，不能绕过。保存 PI 的内部文档生成不拦截业务保存。
- 导出页银行文字只读，整组选择账户切换；后台拒绝直接改写银行文字；额外核查导出银行文字属于历史快照组，账户后来编辑不会替换旧银行资料。已存在不一致的快照需重新选择正确账户后导出。
- 业务提交 `bd42f30`、补充一致性提交 `629448e`；最终线上 `/opt/pi-manager/releases/20260917165502`，标签 `prod-20260917165502`。服务 active，内部登录 HTTP 200；上一部署公网登录跟随跳转忽略 IP 证书验证 HTTP 200。
- 两次部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260917_164956.tar.gz`、`/var/lib/pi-manager/backups/pi-manager_20260917_165325.tar.gz`；禁用 OSS 上传与清理，业务数据保留。
- 最终本地 64 项业务/安全测试通过，5 项图片导出测试通过，页面渲染脚本语法及模拟前端单品牌拦截/双品牌放行/空品牌拒绝通过；最终服务器临时数据库 3 项账户/导出/快照专项测试通过。未做交互浏览器验收。

## 最新接续（2026-09-17 16:36 默认模板贸易条款）

- 系统默认 PI 模板 A12/B12 的 Customer Notes / customer_notes 改为 Trade Terms / price_terms，读取 PI 的 FOB、EXW 等贸易条款；客户备注业务数据及自定义模板占位符保留，QISUO 模板原本已有价格条款，未改。旧 PDF 不批量重生成，重新预览/导出使用更新模板。
- 使用 artifact-tool 编辑/渲染核查；其全量导出改动样式，故将已编辑的两处文字转入原 ZIP XML 包，验证仅 sheet1.xml 两处文本变化，其余组件字节一致。
- 4 项本地相关导出/模板替换/持久化文档测试通过。业务提交 `e71feae`，线上 `/opt/pi-manager/releases/20260917163632`，标签 `prod-20260917163632`；服务 active，内部登录 HTTP 200。
- 部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260917_163537.tar.gz`，禁用 OSS 上传与清理。未覆盖业务数据。

## 最新接续（2026-09-17 16:30 公司抬头已部署）

- 用户明确确认上传并部署至既有服务器后，已完成公司抬头功能部署。业务提交 `c73f1ac`，线上 `/opt/pi-manager/releases/20260917163020`，标签 `prod-20260917163020`；服务 active。下面待部署记录已由本条完成状态取代。
- 沿用本次部署前备份 `/var/lib/pi-manager/backups/pi-manager_20260917_162212.tar.gz`。不覆盖业务数据库、上传文件或设置；原始 PI 与银行信息保留。
- 本地 61 项业务/安全测试、5 项图片导出测试和 JS 抬头切换/银行保留验证通过。

## 最新接续（2026-09-17 公司抬头选择：待部署）

- PI 导出工作台新增独立 KLISTA / QISUO 公司抬头选择，模板与抬头分别选择；同步名称/地址，仅修改导出副本，银行信息保持原值。管理员仍可编辑抬头文字，业务员只可选标准公司；原 PI 不修改。现有两个模板已使用动态抬头占位符，无需改模板文件。
- 业务提交 `c73f1ac`；61 项业务/安全测试及 5 项图片导出测试通过，模拟 JS 公司切换/银行信息保留验证通过。未做交互浏览器验收。
- 服务器部署前备份完成：`/var/lib/pi-manager/backups/pi-manager_20260917_162212.tar.gz`，禁用 OSS 上传与清理。
- 上传代码归档被自动审批两次拒绝，理由为可信用户消息未明确授权具体目的地址上传源代码。未绕过，尚未部署；线上仍为 `20260917155219`。需用户明确授权上传并部署到 `root@47.76.221.183` 后继续。归档 `/tmp/pi-manager-company-header.tar` 已生成。

## 最新接续（2026-09-17 15:52）

- 采购每行及批量供应商选择改为输入名称搜索并弹出匹配列表，部分文字、多词、英文大小写支持；点击/方向键回车选择，支持清空与无匹配提示。结果列表挂在 body 固定定位，避免表格滚动裁切。
- 隐藏原 select 保留供应商 ID、原保存/校验逻辑；输入未选择时清空 ID，失焦恢复已选名称。批量应用及快速新增供应商同步显示；已确认采购行的输入仍禁用，缺少供应商风险边框同步。
- 业务提交 `579b89e`，线上 `/opt/pi-manager/releases/20260917155219`，标签 `prod-20260917155219`；服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_155115.tar.gz`，禁用 OSS 上传与旧备份清理。
- 相关采购保存/状态/权限隔离测试通过；JS 语法及模拟搜索过滤、选择、名称同步、无匹配输入、确认锁测试通过。未做交互浏览器验收。

## 最新接续（2026-09-17 15:46）

- 登记回款弹窗支持 Ctrl+V / ⌘V 粘贴剪贴板图片，生成有扩展名的凭证 File 并沿用现有预览/上传流程。仅弹窗打开时处理图片，文字粘贴不拦截；格式及 12 MB 校验不通过时保留已有有效凭证。非自动读取剪贴板，不请求剪贴板读取权限。
- 业务提交 `8470bcd`，线上 `/opt/pi-manager/releases/20260917154636`，标签 `prod-20260917154636`；服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_154503.tar.gz`，禁用 OSS 上传与旧备份清理。
- 隔离凭证上传/校验/权限测试通过；页面 JS 语法和模拟粘贴范围、预览、格式/大小校验、原凭证保留测试通过。未做交互浏览器验收。

## 最新接续（2026-09-17 15:37）

- 新建/编辑 PI 快速新增产品成功后不再整页刷新，直接将返回的新产品加入当前 PI 末尾，关闭弹窗，保留未保存字段、原有产品和顺序。API 产品数据映射编码、规格、图片、USD 单价，沿用现有币种换算；编辑页新增行应用下游结构锁。
- 业务提交 `f87ad32`，线上 `/opt/pi-manager/releases/20260917153726`，标签 `prod-20260917153726`；服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_153602.tar.gz`，禁用 OSS 上传与旧备份清理。
- 两项相关隔离测试通过；两个页面全部脚本语法及模拟快速新增成功回调验证通过（不刷新、PI 备注保留、返回字段正确带入、按钮恢复）。未做交互浏览器验收。

## 最新接续（2026-09-17 15:21）

- 新建/编辑 PI 产品行序号旁新增上移、下移按钮，原有/新增/复制行均可排序；首尾对应按钮禁用。移动实际 DOM 行并更新 product_order，不重建输入，保留填写内容。沿用 sort_order 保存，预览和导出顺序一致；不改变明细 ID 或下游引用。
- 业务提交 `2c023d7`，线上 `/opt/pi-manager/releases/20260917152151`，标签 `prod-20260917152151`；服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_152100.tar.gz`，禁用 OSS 上传及旧备份清理。
- 两项隔离后台排序/引用保护测试通过；两个页面 JS 语法、模拟 DOM 上下移动/首尾边界/输入保留/提交顺序验证通过。未做交互浏览器验收。

## 最新接续（2026-09-17 15:10）

- 客户新增独立历史美元成交额、截止日期及备注，默认截止日期固定 `2026-09-17`。管理员可从客户详情或编辑页进入历史录入，需确认不含新系统订单；修改留审计并检查客户版本。
- 客户列表及详情显示历史额、系统内额、累计额；列表金额筛选、排序、汇总按累计额。历史金额不进入回款、利润、业绩报表。
- 更正此前说明：实际代码系统内客户成交额按有效回款加手续费累计、每 PI 封顶订单金额，人民币按固定 7 折算；本次保留现有算法，历史字段不会被回款重算覆盖。
- 客户列表增加 Excel 模板、客户编号对照 CSV、上传预览及单独确认导入。按编号或唯一名称匹配，拒绝编号名称冲突、重名、缺少金额、非法金额/日期、公式、重复客户；有错误整批不保存。重导覆盖原历史额，不重复加；预览 30 分钟有效且绑定登录会话/用户，确认检查客户版本并原子保存。
- `assets/customer_history_template.xlsx` 已纳入 Git 和部署白名单。历史数值尚未由用户提供，未编造或导入业务金额；后续用户可填模板导入。
- 业务提交 `807a37b`；线上 `/opt/pi-manager/releases/20260917151018`，标签 `prod-20260917151018`。服务 active，新字段和模板核对成功，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_150859.tar.gz`，禁用 OSS 上传与旧备份清理。
- 本地 61 项业务/安全、5 项图片导出测试通过，末次小调整后两项历史功能测试通过；服务器临时数据库两项测试通过，模板渲染检查通过。未做交互浏览器验收。

## 最新接续（2026-09-17 14:57）

- 供应商新建、编辑和采购页快速新增统一重名校验，不区分英文大小写，忽略首尾空格；提示“该供应商名称已经存在。”并保留表单内容。编辑排除自己，拒绝时不修改数据库；不清理历史重复供应商。
- 业务提交 `8698335`；线上 `/opt/pi-manager/releases/20260917145712`，标签 `prod-20260917145712`。服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_145626.tar.gz`，禁用 OSS 上传与旧备份清理。
- 针对性隔离测试通过：重名新建、重名编辑、保留输入与原记录、原名编辑、API 重名提示；未做交互浏览器验收。

## 最新接续（2026-09-17 13:17）

- 新建/编辑 PI 每行删除按钮左侧新增蓝色复制按钮；下方插入独立明细，复制当前品名、规格、编码、单价、数量和图片，只增加 PI 明细。
- 行标识支持同产品多行；按原 PIItem ID 保存，保留采购/装箱引用；新增 sort_order 保留顺序，历史排序和旧表单兼容。下游结构编辑仍需管理员解锁。
- 提交 `9568905`，线上 `/opt/pi-manager/releases/20260917131752`，标签 `prod-20260917131752`。服务 active、排序字段已核对、公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_131637.tar.gz`，禁用 OSS 上传及旧备份清理。
- 58 项隔离业务/安全、5 项图片导出及两个页面 JS 语法检查通过；未进行交互浏览器验收。

## 最新接续（2026-09-17 13:11）

- 新建和编辑 PI 隐藏单价、数量的数字输入上下箭头，保留数值校验；单价前显示货币符号，随币种切换，行金额原有符号保留。
- 业务提交 `e1ff84c`，部署 release `/opt/pi-manager/releases/20260917131149`，标签 `prod-20260917131149`；服务 active，公网登录 HTTP 200。
- 部署前服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_131055.tar.gz`，禁用 OSS 上传与旧备份清理。
- 两项相关隔离测试通过，未做交互浏览器验收。

## 最新接续（2026-09-17 13:00）

- PI 列表“更多”菜单新增“复制 PI”，复用现有 POST/CSRF 与归属权限规则；复制后进入新单编辑页，日期与编号使用当天，保留单据内容，不复制下游业务记录。
- 业务提交 `07f16cf`，线上 release `/opt/pi-manager/releases/20260917130020`，标签 `prod-20260917130020`；服务 active，公网登录 HTTP 200。
- 部署前仅服务器本地备份 `/var/lib/pi-manager/backups/pi-manager_20260917_125934.tar.gz`，禁用 OSS 上传与旧备份清理。
- 针对性隔离测试通过：列表复制入口、旧日期复制变为今天、新编号、明细覆盖值保留。未做交互浏览器验收。

## 最新接续（2026-09-17 12:55）

- PI 新建、编辑支持单独修改编码（可留空），仅影响当前 PI，产品库不变；恢复按钮支持原品名、规格和编码。
- 新增 `PIItem.code_override`，旧记录回退产品库编码；预览、详情、复制、Excel/PDF 和导出工作台同步。下游记录沿用管理员解锁规则，保留明细 ID。
- 业务提交 `e9d4522`；已部署 `/opt/pi-manager/releases/20260917125537`，标签 `prod-20260917125537`。服务 active、登录健康检查通过，线上字段已核对。
- 部署前本地备份：`/var/lib/pi-manager/backups/pi-manager_20260917_125436.tar.gz`。自动审批拒绝潜在 OSS 上传和旧备份清理后，本次显式禁用 OSS 工具，仅服务器本地备份，未清理旧备份。
- 本地隔离业务/安全 57 项、导出图片 5 项通过；未做交互浏览器验收。需求已完成，以下旧版本号以本节为准。

## 当前基线与接续方式

- 项目目录：`/Users/fantastic/Desktop/jj`；已有实际业务数据的 Flask / SQLAlchemy / SQLite / Jinja2 / Bootstrap 系统。
- GitHub：`https://github.com/fantastic10086-commits/Myweb`，主分支 `main`。
- 最新业务代码提交：`e099ec0`（产品列表同步关键词搜索）。本次交接提交只更新本文，不改变业务功能。
- 最新线上业务版本标签：`prod-20260917124120`，对应 `e099ec0`。以后以实际 Git 分支、标签和服务器 current 为准，不用最大的任意版本号判断。
- 服务器：`root@47.76.221.183`；网站 `https://pimanager.cn`；线上 current 指向 `/opt/pi-manager/releases/20260917124120`（最近部署时已检查）。
- 新对话先读本文，再检查 `git status -sb`、近期提交和有关代码；按用户新需求继续，不重新实现已完成功能。切勿重置已有修改或用旧分支覆盖主分支。
- 用户已授权部署现有服务器。部署前备份，保护业务数据库、上传图片、配置、生成文件；部署授权不等于允许清空业务数据。

## 最近已完成且部署的功能

1. 产品列表和 PI 产品选择共用关键词搜索：大小写不敏感，按空格拆词，所有词都要命中，可跨英文名、中文名、编码、规格匹配。`36KD nozzle` 能匹配 `36KD Gas Nozzle`。完整命中优先；原启停、无图片筛选和手动排序保留。
2. PI 产品名称、规格可单独修改并恢复产品库内容；只影响该 PI，不修改产品库。`PIItem.name_override/spec_override` 保存覆盖值，旧记录回退产品库；预览、复制和导出同步。带下游记录的结构编辑仍受管理员解锁规则约束。
3. 采购多选后批量分配供应商，跨筛选保留选择；只修改供应商，沿用暂存 / 采购完成保存。
4. 报关资料使用用户提供的原 Excel 模板，五个工作表：报关单、发票、装箱单、申报要素、合同。模板在 `assets/customs_declaration_template.xlsx`，导出逻辑在 `customs_export.py`。
5. 报关费用可手填运费、保险费、杂费分配，默认不计入；分配校验不超过 PI 其他费用，折扣另有符号校验。产品申报总额保持产品小计。
6. 按 HS 编码、报关品名和单位整合申报项，报关单 / 发票 / 合同使用整合结果；装箱明细保留。型号仅列少量代表项，过长加“等，详见装箱单”。正式确认保存快照并锁定。
7. 部分报关运输字段改为可选；展开箱子内容使用页面滚动，避免右侧被固定高度裁切。

## 已确认的业务规则（继续开发时必须保留）

- 回款、采购、装箱、报关、发货相对独立；上游回退不能静默删除或重置下游。确需回退时显示影响范围并单独确认。
- 产品有业务引用只能停用，无任何业务引用才允许删除。共享图片必须确认没有其他引用，且数据库提交成功后才能清理。
- 有采购或装箱记录的 PI，普通编辑仅允许非结构字段。产品、数量、币种、客户、金额等结构变化需管理员解锁、原因与影响提示；明细保留原 ID，不删除重建。
- 采购价格明确填写 0 合法；空白才表示缺少价格。完成采购需所有明细完整，否则暂存；已有部分记录的列表显示“部分采购”。
- PI 列表五步流程：回款、采购、装箱、报关、发货；未开始灰色、部分进行蓝色、完成绿色。报关选择需要或无需报关即可绿色；客户旁显示国家。
- 新建 PI 备注必填，放在业务员下方；生成 PI 与 PDF 后保留当前页并预览，不跳列表。PI 导出费用标签只写 Other Charges，不加 Discount。
- 装箱产品跨搜索保留多选，可一起放入目标箱；待装箱筛选包含仍有剩余数量的产品。左右清单与箱子等宽，中间放入操作保留。
- 箱子支持完成后新增并切换、上下调整顺序；卡片字段紧凑排列。精简 100×150 模板保持白底框线、显示业务员，长品名 / 规格省略；支持选择导出的箱子，每箱一页。
- 业务员允许产品复制、编辑、删除或停用，也可创建、编辑、确认报关资料；具体归属 / 权限规则以代码为准。
- 一份报关资料对应一个 PI，原币种沿用，RMB 提示。现有产品报关信息已按用户要求填充，用户未要求逐个核验阻断。

## 关键代码与验证

- `app.py`：权限、页面 / API、启动迁移、PI 明细协调、产品搜索与导出编排。
- `models.py`：业务模型；`customs_export.py`：报关模板和五表；`document_export.py`：PI 模板导出。
- `templates/create_pi.html`、`pi_edit.html`、`procurement.html`、`packing_list_edit.html`、`customs_document.html`：主要相关页面。
- `tests/security_smoke.py` 使用临时目录和隔离测试数据库，禁止改成使用业务库。运行：`venv/bin/python tests/security_smoke.py`。
- 最近两轮搜索与 PI 文本覆盖的针对性本地和服务器测试通过；上一轮完整业务 / 安全 56 项及图片 5 项通过。不能据此声称将来的改动已通过。
- 最新部署检查：服务正常，登录页 / 公开入口正常。最近没有成功完成交互浏览器验收，只做了代码、模板、脚本语法和接口测试。

## 部署约定

- 使用现有 VPS，服务 `pi-manager`，venv `/opt/pi-manager/venv`；Gunicorn `127.0.0.1:8000`。
- 先运行线上 `/opt/pi-manager/current/ops/backup.sh`，再上传独立临时代码目录，运行其中 `ops/update_server.sh`。
- rsync 必须排除 `.git`、`venv`、`instance`、`static/uploads`、`pdf`、`backups`、`settings.json`、日志、业务 CSV、auth 文件和临时目录。
- Excel 模板采用明确白名单，包括 `assets/customs_declaration_template.xlsx`；不要因全局 `*.xlsx` 排除而漏掉它。
- 更新脚本建立新 release、切换 current、重启并检查健康，失败恢复上一 release。成功后核对实际 release 时间并标记对应业务提交。
- GitHub 保存代码、模板与交接记录，不是业务数据库和上传文件的备份。本文不包含登录密码或密钥。

## 当前剩余工作

本轮产品列表搜索已经完成并部署，没有尚待执行的业务修改。本次仅将已完成提交和更新后的交接记录推送 GitHub，等待用户在新对话提供下一项需求。

---

# 历史记录（2026-09-09，以下不是当前版本状态）

# PI Manager 项目交接

整理日期：2026-09-09。项目目录：`/Users/fantastic/Desktop/jj`。

## 1. 本文的依据与工作边界

- 本文根据当前工作区的代码、Git 状态和差异、最近提交、README、DEPLOYMENT、模型、迁移代码、路由、页面、导出模块、测试和运维脚本整理。创建前根目录没有交接文件。
- 当前要求仅检查并创建本文。未修改业务代码，未提交或暂存，未回滚已有修改，未执行部署、恢复或数据迁移。
- 未导入 `app.py`、未启动应用、未运行业务测试，未调用钉钉或 Blob，未连接服务器。不要把静态检查结果当作功能验收或线上健康证明。
- 数据库检查在临时目录内复制主库、WAL、SHM 后以只读连接执行；没有连接原库执行 SQL，也没有读取或摘录客户详情、密码哈希和凭据。副本随后清理。这不是在线事务备份，结果仅代表所检查的本地副本。
- “已有实现”指代码存在；“待验证”指缺少本轮运行证据；“推断风险”不是已确认需求或已复现缺陷。此前对话的具体未完成业务需求无法从当前材料可靠恢复。

## 2. 当前项目状态

项目是已有实际业务数据的外贸形式发票管理系统，技术栈为 Flask、Flask-SQLAlchemy、SQLite、Jinja2、Bootstrap、openpyxl、ReportLab、Pillow。当前 `app.py` 有 6,319 行，业务路由和初始化集中在此文件；不是待搭建的新项目。

当前分支 `main`，HEAD 为 `2b56384`。最新提交时间为 2026-06-22 16:33:07 +0800。当前未提交代码比 HEAD 增加了大量业务、安全、导出和部署实现，不能通过重置到 HEAD 恢复“最新版本”。

现有 `DEPLOYMENT.md` 描述阿里云香港 Ubuntu VPS、Nginx、Gunicorn、systemd 的部署方式。仓库也保留旧 NAS 脚本和 Vercel/Blob 入口。线上实际主机、当前 release、域名、证书和备份状态本轮均未验证；不能仅凭旧 Git 提交推断线上仍运行 Vercel。

### 目录与职责

| 位置 | 职责 |
| --- | --- |
| `app.py` | 配置、启动迁移、权限、业务页面/API、导出编排、备份、钉钉调用 |
| `models.py` | 17 个业务模型、关系、金额/状态属性、部分乐观锁 |
| `document_export.py` | Excel 模板校验、占位符替换、产品行扩展、图片尺寸、LibreOffice 转 PDF |
| `pdf_generator.py` / `excel_generator.py` | 保留的程序化 PI 导出实现；实际入口须沿调用链核对 |
| `packing_list_export.py` / `procurement_export.py` | 装箱单 Excel、供应商采购单 Excel |
| `supplier_statement_pdf.py` | 供应商对账 PDF |
| `templates/` | 39 个页面/片段，主要界面已中文化 |
| `static/` | 本地 Bootstrap 资源、样式、图标；`static/uploads/` 是业务上传数据 |
| `assets/` | 系统默认、QISUO 旧版 Excel 模板及检查产物 |
| `tests/` | 综合安全/业务冒烟测试、导出图片测试 |
| `tools/` | 模板构建工具、缩略图预热工具（预热工具会导入应用，不是只读工具） |
| `ops/` | VPS 安装、更新、迁移、备份、恢复、TLS/OSS 和 systemd/Nginx 配置 |
| `instance/`、`pdf/`、`backups/`、`settings.json` | 本地业务数据、生成文件和配置，不应随代码覆盖线上 |
| `api/index.py`、`vercel.json`、`blob_sync.py` | 保留的 Vercel/Blob 运行路径 |
| `deploy.sh`、`update.sh` | 旧 NAS 上传路径；不是现有 VPS 更新入口 |
| `outputs/`、`output/`、`tmp/`、根目录 CSV/XLSX/图片 | 历史产物和业务资料，未判断为可删除文件 |
| `node_modules` | 指向本机 Codex 依赖目录的符号链接，不是服务器依赖安装结果 |

## 3. 已有功能：继续开发时避免重复实现

| 模块 | 当前实现 | 主要证据 |
| --- | --- | --- |
| 基础资料 | 客户增改查、复制、归属调整；产品导入、搜索分页、选择顺序、增改删、复制；供应商和业务员管理 | `app.py` 对应路由、`templates/` |
| 用户与权限 | 独立登录账号和显示姓名、管理员/业务员权限、客户和 PI 归属限制、启停用户、密码重置、强制改密和会话失效 | `User`、`enforce_password_change`、访问权限帮助函数 |
| PI | 创建、编辑、复制、列表、详情、预览、银行和汇率快照、费用/折扣、价格条款、交货期 | `PI`、`pi_create`、`pi_edit`、`pi_copy` |
| 单据导出 | 默认/自定义 Excel 模板、模板下载与替换、Excel/PDF、导出工作台临时副本、图片等比缩放 | `document_export.py`、`pi_export`、`_generate_default_pi_documents` |
| 收款 | 实际到账账户、流水号去重、提交幂等、凭证图片、手续费、删除确认、审计和恢复 | `Payment`、`pi_toggle_paid`、`payment_delete` |
| 报表与费用 | 回款统计、内部费用及附件、管理员人民币利润表、业务员和日期筛选 | `sales_stats`、`fees_report`、`api_expenses` |
| 采购 | 采购明细、供应商分配、人民币采购单价和供应商运费、完整性检查、确认/取消确认、供应商采购单导出 | `Procurement`、`api_procurement_save`、`api_procurement_confirm` |
| 发货与报关 | 发货日期、物流号、备注、记录人员；报关需求和备注；旧管理员发货状态兼容接口 | `api_pi_shipping_record`、`api_pi_customs_declaration` |
| 装箱单 | 列表、草稿/完成、逐箱数量/重量/尺寸/备注、版本冲突校验、Excel/PDF | `PackingList` / `PackingBox` / `PackingItem`、装箱路由 |
| 数据治理 | 客户/PI/收款软删除和恢复、审计、字段选项、银行账号敏感操作验证 | `AuditLog`、回收站、字段管理路由 |
| 运维 | 环境变量分离、systemd 服务、代码 release 切换、备份及 OSS 上传工具 | `ops/`、`DEPLOYMENT.md` |
| 外部集成 | 钉钉通知/待办/文件帮助函数、产品翻译、历史 Blob 持久化 | `app.py`、`batch_translate.py`、`blob_sync.py` |

以上不承诺历史验收完成，也不证明外部服务当前已配置可用。

## 4. 当前未提交修改

创建本文前：46 个已跟踪文件修改，2 个已跟踪文件删除，18 个未跟踪条目（目录作为一个条目）。已跟踪差异为 48 个文件、7,506 行新增、3,781 行删除；该统计不包含未跟踪文件内容。暂存区为空。

- `app.py`：+3,815/-661；`models.py`：+351/-5。增加权限、审计、软删除、收款校验、费用/利润、模板、装箱单、发货、迁移等。
- 大量页面修改，尤其 `pi_list.html`、`create_pi.html`、`procurement.html`、`live_edit_pi.html`，包含业务交互和中文化。
- `pdf_generator.py`、`excel_generator.py`、`batch_translate.py` 修改；依赖新增/升级 Flask、Flask-WTF、Pillow；启停脚本改为优先 systemd，否则本地 Gunicorn。
- 未跟踪的重要文件：`DEPLOYMENT.md`、三个新导出模块、`ops/`、`tests/`、`tools/`、`assets/` 及新增模板页面。
- 已删除的两个文件为 `CUSTOMER_EXPORT_56677547_1_1781157273.csv` 和 `印尼发货装箱单_Batch2.xlsx`。删除意图未知，不自动恢复、重新导入或清理。
- `.DS_Store` 和四个已跟踪 `.pyc` 也有修改；这些是已有状态，不能把它们当作本次生成的产物。
- `.gitignore` 忽略业务库、上传目录、配置、备份、大部分 Excel、运行目录和环境文件。仅对系统默认模板 Excel 有例外；QISUO 模板仍被忽略（已由 `git check-ignore` 核实）。
- 本次仅新增本文，未执行 `git add` 或 `git commit`。完整检查时状态见附录。

## 5. 数据库、schema 与迁移

本地原库为 `instance/pi_manager.db`，同目录存在非空 `-wal` 和 `-shm`；另有零字节 `pi.db`，不能误认为主库。检查副本 `PRAGMA quick_check` 返回 `ok`，`foreign_key_check` 返回 0 条违规。不能据此推断服务器数据库情况。

| 表 | 本地副本行数 | 用途 |
| --- | ---: | --- |
| customers | 1366 | 客户 |
| products | 2453 | 产品 |
| users | 7 | 用户 |
| salespersons | 10 | 业务员 |
| accounts | 6 | 收款账户 |
| suppliers | 1 | 供应商 |
| pis / pi_items / payments | 各 1 | PI、明细、收款 |
| procurements / expenses / audit_logs | 各 0 | 采购、费用、审计 |
| field_options | 23 | 字段选项 |
| document_templates | 2 | 单据模板 |
| packing_lists / packing_boxes / packing_items | 各 0 | 装箱计划、箱、箱内产品 |

行数是全部记录数，不按软删除过滤；表为空不代表功能未实现。

关系：客户→PI→PI 明细；PI→收款/费用/采购/装箱单；装箱单→箱→装箱行；采购和装箱行均引用 PI 明细。每张 PI 最多一个装箱单，同单箱号有唯一约束。客户、PI、装箱单使用版本字段和 SQLAlchemy 乐观锁。

本地确认存在账号不区分大小写唯一索引、有效流水号全局唯一的部分索引、幂等键唯一的部分索引、装箱相关索引。`create_all()` 不会自动给旧表补齐模型新声明的所有约束/索引；新建库和历史库的结构等价性仍需专门验证。

没有发现独立 Alembic/migrations 目录。迁移集中在 `app.py::_migrate_db()`，并在 `create_app()` 内随启动执行：

1. `blob_sync.init_db()`（有令牌时尝试下载覆盖主库）。
2. 设置 WAL，`db.create_all()`，自动添加缺失字段。
3. 回填登录账号、规范空删除时间、汇率、收款规范化流水号并建唯一索引。
4. 根据收款和采购数量更新历史采购/发货状态；部分情况下清除完成标志。
5. 安装/更新模板元数据、默认业务员/账户/字段；回填费用英文快照；空表时尝试 CSV 种子导入；空用户表时要求初始管理员密码。

因此 `import app`、应用启动、缩略图预热均不能用作只读检查。加列异常有捕获回滚但未明确报错；历史脏数据与唯一索引冲突可能导致启动失败。不要依据代码中的“生产库已检查”注释认定本轮已检查生产。

## 6. 关键业务规则

### 金额、汇率与报表

- `PI.total_amount` 是产品小计；`shipping_cost` 是向客户收取的费用/折扣，允许负值；`grand_total = product_subtotal + other_charges`。不要把小计当应收总额。
- `actual_shipping_cost` 是保留的数据库字段，其当前语义为供应商采购运费（人民币），经 `supplier_freight_cost` 属性访问。
- 内部 `Expense` 影响利润，不改变客户 PI 应收。客户费用英文标签与银行信息存入 PI 快照，字段/账户后续修改不应静默改写历史单据。
- 新 PI 默认读取系统业务汇率，已有 PI 使用本单汇率；回款业绩折算使用固定 `PERFORMANCE_EXCHANGE_RATE = 7.0`，不能统一替换为可变业务汇率。
- `received_amount` 仅累计有效收款的 amount；付清判定累计 amount + fee 与应收总额比较。客户成交额汇总只包含付清 PI，回款统计包含部分收款 PI，筛选日期使用 PI 开单日期。不要凭函数旧注释改变这些口径。
- 利润表仅管理员可看，有收款订单进入报表；采购数量覆盖全部 PI 明细后才显示利润。人民币净收入＝订单收入－收款手续费；利润＝净收入－采购商品成本－供应商运费－其他已录费用；利润率以净收入为分母。此处采购数据完整不等同于必须已点击采购确认。
- 页面对可能重复录入运费有提示，不代表系统自动去重。

### 收款与访问权限

- 收款金额为正，流水号必填并规范化去重，有效流水号在全部 PI 范围唯一；提交幂等键 16–64 字符。
- 选择实际到账账户，币种须匹配 PI（USD/RMB），必须上传有效回款凭证图片，单凭证最大 12 MB。
- 删除收款须输入匹配流水号；客户、PI、收款使用软删除，恢复走回收站并检查冲突。
- 业务员仅访问自己归属的客户/PI，采购及利润/模板/字段等管理入口有管理员限制；产品允许业务员新增，但已有产品管理另有管理员限制。
- 写请求有 CSRF 防护；禁用/改密/权限变更通过 `auth_version` 使旧会话失效。客户/PI 的表单版本检查不能被新界面绕过。

### 采购、发货、报关、装箱

- 有实际收款才能采购；采购保存替换该单采购明细，当前接口同一 PI 明细只能出现一次，不能假设支持一项商品拆给多个供应商。
- 采购确认要求每项数量足够；确认后先取消确认才能改，已发货先撤销发货才能取消采购确认。
- 发货登记要求采购完整并已确认，记录日期、物流号、备注和操作者；所属业务员可登记自己的订单，管理员兼容接口可撤销。
- 回款、采购、装箱、报关和发货记录相对独立；回款变化不会静默清空下游记录。订单进度由采购与发货记录推导，回款状态单独显示。
- 报关需求有未填写、需要、不需要三态，不应改变收款/采购/发货状态。
- 装箱单管理员保存，PI 必须付清；所属业务员可查看/导出。已有历史装箱单即使订单不再付清仍保留可见性，不能继续保存。
- 箱号必填且大小写不敏感去重；单箱同一 PI 明细不能重复；数量是正整数，跨箱合计不能超过 PI 数量；完成时必须全部装足。
- 最大 200 箱、2,000 行，每行数量最大 1,000,000；尺寸为厘米，CBM＝长×宽×高/1,000,000；不能相信客户端传来的体积值。
- 装箱单有独立 version，冲突返回 409；草稿可导出，文件名有 DRAFT 标记。装箱数据独立于客户 PI 单据。

### 导出

- 导出工作台使用内存副本，临时改文案不应回写 PI、客户或产品；银行等受保护字段仍受角色约束。
- 系统默认模板为实际 Excel 源，直接 PI 下载和保存文件已接入统一导出编排；不要新增一套重复的模板系统。
- 自定义 Excel 使用已支持占位符并扩展明细行，图片等比适配。PDF 转换依赖 LibreOffice/soffice（90 秒超时）和字体，不能只凭 Excel 成功判断 PDF 成功。
- 默认模板管理员替换后的上传文件应跨重启保留。QISUO 初始化逻辑会强制该模板 `is_default=False`，与手动设为默认的交互需要验证。

## 7. 当前未完成任务（可推断，尚非已确认业务需求）

目前没有可靠依据列出此前对话约定的具体剩余功能。以下是从代码现状推断出的验证/修复候选，不自动获得修改或部署授权：

| 优先顺序 | 待办/风险 | 证据和下一步 |
| --- | --- | --- |
| 1 | 运行既有隔离测试并记录结果 | 当前有 39 个综合测试、4 个图片测试；本轮只静态检查，不能声称通过 |
| 2 | 验证有下游记录的 PI 编辑 | `pi_edit` 批量删除重建 PIItem，采购/装箱行有外键引用且启用外键；可能发生约束失败。另需验证编辑总额/客户/币种后的收款汇总一致性；只在临时库复现 |
| 3 | 演练旧库迁移、重复启动和记录保留 | 自动迁移会改历史状态并建唯一索引；应对生产一致性备份的隔离副本做前后差异核对 |
| 4 | 修复或核实发布资源范围 | `ops/install_server.sh` 排除所有 XLSX，却未包含默认模板例外；新安装缺少模板且上传目录无副本时会启动失败。更新脚本已有两个模板例外，但 QISUO 源被 Git 忽略 |
| 5 | 验证模板重启及 PDF 版式 | QISUO 默认选择可能被启动重置；测试短/长 PI、宽高图片、分页、默认与 QISUO/自定义模板；图片和分页已有修复，不重复实现 |
| 6 | 只读核对服务器状态 | 当前 release、配置变量名、持久数据路径、LibreOffice/字体、健康状态、备份定时器、OSS 最近成功记录；不输出凭据 |
| 7 | 明确实际需求后再实施 | 与用户确认待办优先级，保留既有修改；当前不提交、不部署 |

没有在应用/页面中发现明确的 TODO/FIXME 待开发清单；“模板占位符”是产品能力，不是未实现占位代码。

## 8. 部署与数据风险

- VPS 文档路径：代码 `/opt/pi-manager/releases/<timestamp>`，`current` 为软链接；虚拟环境 `/opt/pi-manager/venv`；业务数据 `/var/lib/pi-manager`；配置 `/etc/pi-manager/pi-manager.env`；Gunicorn 单 worker、4 threads，监听 `127.0.0.1:8000`。
- `ops/update_server.sh` 排除主业务目录，安装依赖、切换 release、安装服务文件、重启并检查 `/login`；失败自动切回旧代码。它没有在更新前主动调用备份；共享虚拟环境依赖和已执行数据库迁移不会随代码软链接回退。用户禁止回滚时，不能未经讨论直接执行此自动回退流程。
- `/login` 健康检查不能覆盖装箱单、利润、导出、权限和迁移结果。上线验收应另有业务检查。
- `ops/migrate_data.sh` 是覆盖数据的初始化迁移脚本，`ops/restore.sh` 会覆盖主库且对上传/PDF 使用 `--delete`；禁止将其当成常规代码更新步骤。
- `deploy.sh` 是旧 NAS 首次部署脚本且会上传 settings；`update.sh` 使用 `rsync --delete`。不能直接用于当前服务器。
- `ops/backup.sh` 使用 SQLite `.backup` 并检查完整性，打包上传、PDF、settings；OSS 配置存在才上传并核对对象。只在 OSS 上传核对后清理旧本地备份，默认保留 5 份（至少 3）。本轮未验证实际定时执行或恢复演练。
- WAL 数据库不能仅复制 `.db` 作为生产备份。旧 Blob 上传函数目前用 `shutil.copy2` 只复制主库；在 WAL 模式有遗漏最新事务风险。Blob 启动下载会 `os.replace` 现有主库；若 VPS 意外继承 Blob 令牌，会进入该路径。此为代码事实及条件风险，本轮没有验证线上启用情况。
- 测试脚本设置临时业务路径，但没有显式清除继承的 Blob 令牌；运行前需确保外部凭据不被继承并隔离钉钉调用，避免测试触碰真实云数据库或发消息。
- 依赖使用版本范围，没有锁文件；运行环境版本需实测。不要把本机旧 `.pyc` 名称当当前 Python 版本依据。
- 内置模板、源码和业务数据之外存在大文件及本机符号链接，发布前应查看文件清单/dry-run，避免把整目录直接当发布包。

## 9. 检查结果与建议接续步骤

本轮已执行：Git 状态/差异/暂存区/最近提交检查；Python 源码 AST 语法解析（根目录、api、tests、tools，共 14 个文件）通过；11 个 Shell 脚本 `bash -n` 通过；本地临时数据库副本 quick_check 通过、外键违规为 0。

未执行：业务单元/集成测试、浏览器交互、PDF/Excel 视觉验收、线上核对、网络集成验证。语法通过不等于业务测试通过。

测试入口：`tests/security_smoke.py`（39 个，包含权限、汇率、利润、收款、模板、装箱、发货/报关等）及 `tests/test_document_export_images.py`（4 个）。综合测试不是标准 `test_*.py` 文件名，默认 unittest discover 可能漏掉它。PDF 测试存在环境依赖/跳过逻辑，应报告通过、失败和跳过数量。

后续执行应使用隔离配置、临时数据目录、禁用外部凭据/消息调用，并关闭 bytecode 写入；显式运行综合测试，再运行图片测试。不能先直接导入应用“看看能否启动”。

建议先向用户汇报本文和推断风险；在获准继续实现后，优先跑现有隔离测试并复现具体缺陷，确定最小修改，再规划部署。没有证据时不宣称装箱、模板、发货等功能尚未实现，也不擅自扩充产品需求。

## 10. 附录：检查时 Git 状态、提交和路由索引

以下附录由 Git 和 Python AST 静态提取，不加载 Flask 应用。行号对应本次检查时源码。路由装饰器仅描述入口保护；客户/PI 归属等还需看函数体，不能据此替代完整权限审查。

### 创建本文前的 Git 状态

```text
 M .DS_Store
 M .gitignore
 D CUSTOMER_EXPORT_56677547_1_1781157273.csv
 M README.md
 M __pycache__/app.cpython-37.pyc
 M __pycache__/excel_generator.cpython-37.pyc
 M __pycache__/models.cpython-37.pyc
 M __pycache__/pdf_generator.cpython-37.pyc
 M app.py
 M batch_translate.py
 M excel_generator.py
 M models.py
 M pdf_generator.py
 M requirements.txt
 M start.sh
 M stop.sh
 M templates/account_form.html
 M templates/account_list.html
 M templates/backup.html
 M templates/base.html
 M templates/create_pi.html
 M templates/customer_detail.html
 M templates/customer_form.html
 M templates/customers.html
 M templates/fees.html
 M templates/index.html
 M templates/live_edit_pi.html
 M templates/login.html
 M templates/pi_detail.html
 M templates/pi_edit.html
 M templates/pi_list.html
 M templates/pi_preview.html
 M templates/procurement.html
 M templates/procurement_select.html
 M templates/product_form.html
 M templates/product_import.html
 M templates/products.html
 M templates/profile.html
 M templates/sales_stats.html
 M templates/salesperson_form.html
 M templates/salesperson_list.html
 M templates/settings.html
 M templates/supplier_detail.html
 M templates/supplier_form.html
 M templates/supplier_list.html
 M templates/user_form.html
 M templates/user_list.html
 D 印尼发货装箱单_Batch2.xlsx
?? DEPLOYMENT.md
?? assets/
?? document_export.py
?? node_modules
?? ops/
?? outputs/
?? packing_list_export.py
?? procurement_export.py
?? templates/_pi_report_filters.html
?? templates/audit_logs.html
?? templates/document_templates.html
?? templates/field_management.html
?? templates/packing_list_edit.html
?? templates/packing_list_index.html
?? templates/recycle_bin.html
?? tests/
?? tools/
?? 微信图片_20260706155222_109_17.png
```

### 最近 15 次提交

```text
2b56384 | 2026-06-22 16:33:07 +0800 | Read Blob environment at sync time
b7a469f | 2026-06-22 16:29:07 +0800 | Show Blob persistence error details
66ef80f | 2026-06-22 16:24:20 +0800 | Fix Blob store id resolution
a4cbfec | 2026-06-22 16:20:52 +0800 | Warn when Blob persistence fails
93775ef | 2026-06-22 16:19:00 +0800 | Fix Vercel Blob database overwrite
e7037c5 | 2026-06-22 16:11:17 +0800 | Clarify user password status display
3237e6c | 2026-06-22 16:03:51 +0800 | Fix Blob sync after password updates
0171e65 | 2026-06-22 15:57:47 +0800 | Show actual password status: Default vs Custom (changed)
dce3f03 | 2026-06-22 15:54:15 +0800 | Show default password hint on user edit page
03cacc7 | 2026-06-22 14:49:28 +0800 | Add Vercel Blob persistence for SQLite database
3fc38e0 | 2026-06-21 23:51:14 +0800 | Fix customer CSV: replace 姜舒棋 with Shu Kei for salesperson matching
393a832 | 2026-06-21 23:47:29 +0800 | Use direct JS form submission instead of type=submit
ee4fce3 | 2026-06-21 23:45:07 +0800 | Add inline onclick handler to submit button for debugging
5364c7a | 2026-06-21 20:55:42 +0800 | Make debug status always visible with version marker
920a116 | 2026-06-21 20:50:47 +0800 | Add visible submit debug feedback and explicit form action
```

### 全部 Flask 路由

| 方法 | 路径 | 函数与源码位置 | 入口装饰器 |
| --- | --- | --- | --- |
| GET | `/favicon.ico` | `app.py:1482` favicon | 无显式角色装饰器 |
| GET,POST | `/login` | `app.py:1488` login | 无显式角色装饰器 |
| POST | `/login/account-name` | `app.py:1528` login_account_name | 无显式角色装饰器 |
| GET | `/logout` | `app.py:1542` logout | 无显式角色装饰器 |
| GET,POST | `/profile` | `app.py:1549` profile | login_required |
| GET,POST | `/settings` | `app.py:1616` settings_page | login_required |
| GET | `/` | `app.py:1679` index | login_required |
| GET | `/customers` | `app.py:1699` customer_list | login_required |
| GET,POST | `/customers/add` | `app.py:1769` customer_add | login_required |
| GET,POST | `/customers/<int:id>/edit` | `app.py:1801` customer_edit | login_required |
| POST | `/api/customers/add` | `app.py:1846` api_customer_add | login_required |
| POST | `/api/customers/<int:id>/copy` | `app.py:1882` api_customer_copy | login_required |
| GET | `/customers/<int:id>` | `app.py:1909` customer_detail | login_required |
| GET | `/sales-stats` | `app.py:1962` sales_stats | login_required |
| GET | `/fees` | `app.py:2100` fees_report | admin_required |
| GET | `/profit-report` | `app.py:2100` fees_report | admin_required |
| GET,POST | `/api/expenses` | `app.py:2266` api_expenses | login_required |
| DELETE | `/api/expenses/<int:id>` | `app.py:2348` api_expense_delete | admin_required |
| GET | `/expenses/<int:id>/attachment` | `app.py:2371` expense_attachment | login_required |
| POST | `/customers/<int:id>/delete` | `app.py:2394` customer_delete | login_required |
| POST | `/customers/<int:id>/reassign` | `app.py:2417` customer_reassign | login_required |
| GET | `/products` | `app.py:2447` product_list | login_required |
| GET,POST | `/products/import` | `app.py:2494` product_import | admin_required |
| GET,POST | `/products/add` | `app.py:2644` product_add | login_required |
| GET,POST | `/products/<int:id>/edit` | `app.py:2684` product_edit | admin_required |
| POST | `/products/<int:id>/delete` | `app.py:2720` product_delete | admin_required |
| POST | `/products/batch-delete` | `app.py:2734` product_batch_delete | admin_required |
| POST | `/api/products/add` | `app.py:2759` api_product_add | login_required |
| GET | `/api/products/search` | `app.py:2801` api_product_search | login_required |
| POST | `/api/products/<int:id>/update` | `app.py:2862` api_product_update | admin_required |
| POST | `/api/products/<int:id>/copy` | `app.py:2889` api_product_copy | admin_required |
| POST | `/api/products/<int:id>/delete` | `app.py:2915` api_product_delete | admin_required |
| POST | `/api/translate` | `app.py:2929` api_translate | login_required |
| GET | `/uploads/<filename>` | `app.py:2952` uploaded_file | login_required |
| GET | `/uploads/thumb/<filename>` | `app.py:2968` uploaded_product_thumbnail | login_required |
| GET | `/salespersons` | `app.py:2989` salesperson_list | admin_required |
| GET,POST | `/salespersons/add` | `app.py:3006` salesperson_add | admin_required |
| GET,POST | `/salespersons/<int:id>/edit` | `app.py:3031` salesperson_edit | admin_required |
| POST | `/salespersons/<int:id>/delete` | `app.py:3055` salesperson_delete | admin_required |
| GET | `/users` | `app.py:3069` user_list | admin_required |
| GET,POST | `/users/add` | `app.py:3079` user_add | admin_required |
| GET,POST | `/users/<int:id>/edit` | `app.py:3117` user_edit | admin_required |
| POST | `/users/<int:id>/delete` | `app.py:3159` user_delete | admin_required |
| POST | `/users/<int:id>/toggle-active` | `app.py:3175` user_toggle_active | admin_required |
| POST | `/users/<int:id>/reset-password` | `app.py:3193` user_reset_password | admin_required |
| GET | `/accounts` | `app.py:3269` account_list | admin_required |
| GET | `/field-management` | `app.py:3269` account_list | admin_required |
| POST | `/field-options/add` | `app.py:3285` field_option_add | admin_required |
| POST | `/field-options/<int:id>/edit` | `app.py:3323` field_option_edit | admin_required |
| POST | `/field-options/<int:id>/delete` | `app.py:3360` field_option_delete | admin_required |
| GET,POST | `/accounts/add` | `app.py:3373` account_add | admin_required |
| GET,POST | `/accounts/<int:id>/edit` | `app.py:3411` account_edit | admin_required |
| POST | `/accounts/<int:id>/delete` | `app.py:3447` account_delete | admin_required |
| GET | `/audit-logs` | `app.py:3472` audit_logs | admin_required |
| GET | `/recycle-bin` | `app.py:3491` recycle_bin | admin_required |
| POST | `/recycle-bin/customer/<int:id>/restore` | `app.py:3500` restore_customer | admin_required |
| POST | `/recycle-bin/pi/<int:id>/restore` | `app.py:3525` restore_pi | admin_required |
| POST | `/recycle-bin/payment/<int:id>/restore` | `app.py:3547` restore_payment | admin_required |
| GET | `/suppliers` | `app.py:3585` supplier_list | admin_required |
| GET | `/suppliers/<int:id>` | `app.py:3592` supplier_detail | admin_required |
| GET | `/suppliers/<int:id>/statement` | `app.py:3620` supplier_statement | admin_required |
| GET,POST | `/suppliers/add` | `app.py:3647` supplier_add | admin_required |
| GET,POST | `/suppliers/<int:id>/edit` | `app.py:3669` supplier_edit | admin_required |
| POST | `/suppliers/<int:id>/delete` | `app.py:3689` supplier_delete | admin_required |
| GET | `/api/suppliers` | `app.py:3698` api_supplier_list | admin_required |
| GET,POST | `/pi/create` | `app.py:3709` pi_create | login_required |
| GET | `/pi/list` | `app.py:3886` pi_list | login_required |
| GET | `/packing-lists` | `app.py:4150` packing_list_index | login_required |
| GET | `/packing-list/<int:pi_id>` | `app.py:4191` packing_list_detail | login_required |
| POST | `/api/packing-list/<int:pi_id>` | `app.py:4210` packing_list_save | admin_required |
| GET | `/packing-list/<int:pi_id>/export.xlsx` | `app.py:4348` packing_list_export_excel | login_required |
| GET | `/packing-list/<int:pi_id>/export.pdf` | `app.py:4354` packing_list_export_pdf | login_required |
| GET | `/pi/<int:id>` | `app.py:4360` pi_detail | login_required |
| GET | `/pi/<int:id>/preview` | `app.py:4375` pi_preview | login_required |
| GET | `/pi/<int:id>/download` | `app.py:4386` pi_download | login_required |
| GET | `/pi/<int:id>/excel` | `app.py:4430` pi_excel_download | login_required |
| POST | `/pi/<int:id>/toggle-paid` | `app.py:4451` pi_toggle_paid | login_required |
| POST | `/pi/<int:id>/payment/<int:pid>/delete` | `app.py:4622` payment_delete | login_required |
| GET | `/api/pi/<int:id>/payments` | `app.py:4653` api_pi_payments | login_required |
| GET | `/payments/<int:id>/attachment` | `app.py:4693` payment_attachment | login_required |
| GET,POST | `/api/pi/<int:id>/customs-declaration` | `app.py:4716` api_pi_customs_declaration | login_required |
| POST | `/pi/<int:id>/delete` | `app.py:4785` pi_delete | login_required |
| POST | `/pi/<int:id>/copy` | `app.py:4803` pi_copy | login_required |
| GET,POST | `/pi/<int:id>/edit` | `app.py:4884` pi_edit | login_required |
| GET | `/document-templates` | `app.py:5385` document_template_list | admin_required |
| POST | `/document-templates/add` | `app.py:5397` document_template_add | admin_required |
| POST | `/document-templates/<int:id>/edit` | `app.py:5444` document_template_edit | admin_required |
| POST | `/document-templates/<int:id>/toggle` | `app.py:5498` document_template_toggle | admin_required |
| POST | `/document-templates/<int:id>/default` | `app.py:5519` document_template_default | admin_required |
| POST | `/document-templates/<int:id>/delete` | `app.py:5539` document_template_delete | admin_required |
| GET | `/document-templates/<int:id>/source` | `app.py:5571` document_template_source | admin_required |
| GET | `/document-templates/example` | `app.py:5581` document_template_example | admin_required |
| GET,POST | `/pi/<int:id>/export` | `app.py:5593` pi_export | login_required |
| GET | `/pi/<int:id>/live-edit` | `app.py:5663` pi_live_edit | login_required |
| GET | `/procurement` | `app.py:5698` procurement_select | admin_required |
| GET | `/procurement/<int:pi_id>` | `app.py:5730` procurement_page | admin_required |
| POST | `/procurement/<int:pi_id>/supplier-orders/export` | `app.py:5822` procurement_supplier_orders_export | admin_required |
| POST | `/api/procurement/save` | `app.py:5896` api_procurement_save | admin_required |
| POST | `/api/procurement/<int:pi_id>/confirm` | `app.py:5992` api_procurement_confirm | admin_required |
| GET,POST | `/api/pi/<int:pi_id>/shipping-record` | `app.py:6053` api_pi_shipping_record | login_required |
| POST | `/api/pi/<int:pi_id>/shipping-complete` | `app.py:6113` api_pi_shipping_complete | admin_required |
| GET | `/api/procurement/<int:pi_id>` | `app.py:6156` api_procurement_get | admin_required |
| GET | `/backup` | `app.py:6175` backup_page | admin_required |
| POST | `/backup/create` | `app.py:6199` backup_create | admin_required |
| GET | `/backup/download/<filename>` | `app.py:6261` backup_download | admin_required |
| POST | `/backup/delete/<filename>` | `app.py:6273` backup_delete | admin_required |

共 106 个路由声明；GET 路由的 Flask 自动 HEAD/OPTIONS 未另列。
