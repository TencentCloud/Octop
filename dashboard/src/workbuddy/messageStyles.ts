import cssModules from "./generated/cssModules.json";

// Keep hashed classes coupled to the source CSS Modules extraction.
export const sourceUserBubbleClass =
  cssModules[
    "../packages/cb-chat-ui/src/components/message-timeline/user-bubble.module.scss"
  ].userMessageBubble;
