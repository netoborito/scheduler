# Quick Git Commit Fix

If your commit is stalled in an editor:

## Option 1: Complete the commit
1. Save the COMMIT_EDITMSG file (Ctrl+S)
2. Close the file
3. The commit should complete automatically

## Option 2: Abort and retry
Run these commands in your terminal:

```bash
# Abort the current commit
git commit --abort

# Commit with a message directly (no editor)
git commit -m "Initial commit"
```

## Option 3: If stuck in Vim
- Press `Esc` (to enter command mode)
- Type `:wq` and press Enter (save and quit)
- Or type `:q!` and press Enter (quit without saving, then use Option 2)
