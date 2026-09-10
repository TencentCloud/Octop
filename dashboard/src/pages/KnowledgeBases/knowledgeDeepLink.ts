import { knowledgeCitationDirectory } from "../../utils/knowledgeCitationDisplay";

export type KnowledgeDeepLinkDocument = {
  id: string;
  path?: string;
  filename: string;
  is_dir?: boolean;
};

export function resolveKnowledgeDeepLink(params: {
  kb: string | null;
  doc: string | null;
  bases: { id: string }[];
  documents: KnowledgeDeepLinkDocument[];
}): {
  kbId: string;
  document: KnowledgeDeepLinkDocument;
  folder: string;
} | null {
  const kbId = (params.kb || "").trim();
  const docId = (params.doc || "").trim();
  if (!kbId || !docId) return null;
  if (!params.bases.some((base) => base.id === kbId)) return null;
  const document = params.documents.find(
    (row) => row.id === docId && !row.is_dir,
  );
  if (!document) return null;
  const folder = knowledgeCitationDirectory(document.path || document.filename);
  return { kbId, document, folder };
}
