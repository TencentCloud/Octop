# 集群节点发现

范围按这个顺序定，不要写进 `MEMORY.md`：

1. 用户点名的实例 ID 或名称。
2. 用户给出的标签。`tccli cvm DescribeInstances --region <r> --Filters '[{"Name":"tag:<键>","Values":["<值>"]}]'`。
3. 都没有时，用当前地域的 `RUNNING` 实例，并先告诉用户台数。超过 200 台先说明耗时，再问要不要抽样。

跨地域分开查。轻量应用服务器用 `tccli lighthouse DescribeInstances`，TAT 单独下发，不和 `ins-` 混在同一次 `RunCommand` 里。

凭据先看 `tccli-oauth-helper.py --status`。`DescribeInstances` 里混进已销毁实例会导致整批失败，按 `MEMORY.md` 的已知坑做二分。
