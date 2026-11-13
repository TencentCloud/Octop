import McpAccess from "../../Agent/Memory/McpAccess";

/**
 * 终端接入（设置 → 终端接入）。
 *
 * token 是用户级的：一人一份，绑定专家只是它的一个字段。放在设置里而不是某个
 * 专家的记忆面板里，避免「这是某个专家的配置」的误解，也避免每个专家页重复入口。
 */
export default function TokensPage() {
  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflow: "auto",
        padding: "10px 16px",
      }}
    >
      <McpAccess />
    </div>
  );
}
