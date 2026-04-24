# CataForge — Claude Code 项目指令

## Git 工作流

`main` 和 `dev` 均为**受保护分支**，禁止直接 push。所有变更必须通过 PR 合入。

**发版流程**：
1. 在功能/修复分支上完成变更并 commit
2. `git push -u origin <branch>` 推送分支
3. `gh pr create` 开 PR，等待 CI 通过后合入
4. 合入后在 `main` 上打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`

**常见错误**：不要在本地 `main` 上 commit 后直接 `git push`——受保护分支会拒绝。
若已提交到本地 `main`，用以下方式补救：

```bash
git branch <new-branch>        # 在当前 commit 创建新分支
git reset --hard origin/main   # 将 main 还原到远端状态
git push -u origin <new-branch>
```
