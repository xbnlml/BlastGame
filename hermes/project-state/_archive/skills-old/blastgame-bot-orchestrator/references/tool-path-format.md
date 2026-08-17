# 工具路径格式说明

## search_files 路径格式

`search_files` 底层用**原生 Windows ripgrep**，不支持 MSYS2 路径格式。

```bash
# ❌ 错误 — ripgrep 不认 MSYS2 路径
search_files(pattern="something", path="/d/download/Hermes")

# ✅ 正确 — 必须用 Windows 风格
search_files(pattern="something", path="D:/download/BlastGame/hermes")
```

**判断方法：** 如果 `search_files` 报 `IO error for operation on /d/...`，就是路径格式问题。

## terminal 路径格式

`terminal` 工具同时支持两种格式：
- MSYS2: `/d/download/Hermes/`  
- Windows: ``

推荐用 `/d/` 格式在 terminal 中操作（更短）.

## Python open() 路径格式

在 `python3 -c` 内联代码或脚本中，`open()` **不接受** MSYS2 路径：
- ❌ `open("/d/download/Hermes/file.json")` — 报错
- ✅ `open("file.json")` — 正确

## 通用规则

| 工具 | MSYS2 (/d/) | Windows (D:/) |
|------|------------|---------------|
| terminal | ✅ | ✅ |
| search_files | ❌ | ✅ |
| read_file | ✅ | ✅ |
| write_file | ✅ | ✅ |
| python open() | ❌ | ✅ |
| patch | ✅ | ✅ |
