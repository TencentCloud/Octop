import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { EmbeddingModelPool } from "./EmbeddingModelPool";

it("lists enabled embeddings from a mixed provider on the embedding tab", () => {
  const models = [
    { id: "BAAI/bge-large-zh-v1.5", embedding: true },
    { id: "BAAI/bge-m3" },
    { id: "BAAI/bge-reranker-v2-m3" },
    { id: "Pro/BAAI/bge-m3", enabled: false },
    { id: "chat-model" },
  ].map((model) => ({ name: model.id, enabled: true, ...model }));

  render(
    <MemoryRouter>
      <EmbeddingModelPool
        providers={[
          {
            id: 1,
            name: "SiliconFlow (China)",
            kind: "openai",
            enabled: true,
            base_url: "https://example.test/v1",
            api_key: "test",
            note: null,
            purpose: "chat",
            models,
          },
        ]}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText("BAAI/bge-large-zh-v1.5")).toBeInTheDocument();
  expect(screen.getByText("BAAI/bge-m3")).toBeInTheDocument();
  expect(screen.queryByText("BAAI/bge-reranker-v2-m3")).toBeNull();
  expect(screen.queryByText("Pro/BAAI/bge-m3")).toBeNull();
  expect(screen.queryByText("chat-model")).toBeNull();
});
