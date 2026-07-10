# 外部真值优先 (external-truth-first)

适用：产物契约依赖**第三方外部系统消费**的项目——产出的 HTML / 文件 / API 载荷最终被外部平台粘贴过滤、导入解析、渲染变换。无外部消费方的自包含项目（产物即终点）整套机制自然 no-op，不产生任何额外负担。

核心原则：内部一致性门禁（文档↔代码↔测试互证）无法度量外部正确性；最高风险的外部假设必须在规模化开发前先经真实系统验证，未校准的替身不得把「未知」转换成「绿灯」。

## external_oracles 声明（arch §1.5）

- 格式：`| EO-NNN | 外部系统 | 对产物的变换行为 | 验证方式 |`；无外部消费方显式写 N/A，使「不填」成为显式决定
- 声明非空即激活下方全部机制；模板占位行（含 `{` 未填值）不算声明

## walking-skeleton 强制卡（dev-planning）

- arch external_oracles 非空时，Sprint 1 必须含一张 `walking_skeleton: true` 任务卡：渲染最小产物 → 经真实通道送入外部系统 → 比对消费后状态
- 该卡是后续规模化 Sprint 任务的 blocking dependency——先退火外部假设，再放量开发
- 其 AC 真值锚定**最终消费边界**（消费后状态），浏览器渲染正确只是中间层（COMMON-RULES §保真类 AC）
- 外部系统开发期不可达 → 按 COMMON-RULES §verdict_blocking_semantics 走 `conditional_release` + 非空 `blocking_conditions`，不默认放行
- doc-review dev-plan Layer 1 机检：external_oracles 非空而 dev-plan 无 `walking_skeleton: true` 卡 → FAIL
- 可选检查点 `post_skeleton`（COMMON-RULES §MANUAL_REVIEW_CHECKPOINTS 可选值）：tracer 验证通过后由用户确认再进入规模化

## 模拟器保真度契约（门禁证据资格）

- 替身外部系统的模拟器/mock 须以机器可读元数据声明保真度：`fidelity: calibrated | partial | placeholder`，附校准证据——与真实系统输出的 fixture 对照集、校准日期、已知盲区清单
- `placeholder` / 未声明保真度者的结论**不得**在 code-review / sprint-review / AC 勾选中作为通过证据；对应结论按未验证处理
- 校准证据过期（外部系统行为已变）降级为 `partial`
- 模拟对象为项目自有系统（非外部黑盒）时不适用——保真度与代码同源，属常规测试覆盖
- 盲区回灌：真实系统走查发现的每处模拟器盲区，回灌为该模拟器的回归 fixture（真实行为语料库），保证保真度单调收敛
- 收敛不变量（可选）：校准后把「模拟器对自家产物零差异」固化为 CI 性质，新产物/新规则破坏即门禁红
