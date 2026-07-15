### Fixed

- **file_lock 双并发竞态** —— ① 空载荷窗口误回收：锁文件在 `O_EXCL` 创建与持有者载荷写入之间为空，竞争者将其误判为 corrupt 而立即删除夺锁，导致双持有者同时进入临界区（CI 曾实际复现进程内互斥断言失败）；corrupt/空载荷改按锁文件 mtime 判新鲜度，仅 TTL 过期才可回收。② 夺锁 TOCTOU：基于旧 holder 快照判 stale 后直接 unlink，可能删掉的是期间已被新持有者重建的锁；unlink 前重读 holder 与快照比对，不一致即退避重试。
