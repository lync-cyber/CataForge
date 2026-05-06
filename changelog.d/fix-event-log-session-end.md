### Added

- **`event-log` schema 接收 `session_end` 事件** —— `event` enum 与 `cataforge.core.event_log.VALID_EVENTS` 同步追加 `session_end`，与既有 `session_start` 对称。下游 Stop hook / orchestrator 协议手写的 session 收尾事件不再被 `cataforge doctor` 标为 schema FAIL。
