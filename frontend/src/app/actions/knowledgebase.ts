"use server";

import { backendFetch } from "@/lib/backend-fetch";
import type { KnowledgeBaseDocument } from "@/lib/types";

interface DocumentApiOut {
  id: string;
  source_type: string;
  original_filename: string | null;
  doc_name: string;
  machine_type: string | null;
  status: string;
  rejection_reason: string | null;
  uploaded_at: string;
  processed_at: string | null;
  chunk_count: number;
}

function fromApi(d: DocumentApiOut): KnowledgeBaseDocument {
  return {
    id: d.id,
    originalFilename: d.original_filename,
    docName: d.doc_name,
    status: d.status,
    chunkCount: d.chunk_count,
    uploadedAt: d.uploaded_at,
  };
}

export async function listKnowledgeBaseDocumentsAction(
  machineId: string,
): Promise<KnowledgeBaseDocument[]> {
  const resp = await backendFetch(
    `/knowledgebase/documents?machine_id=${encodeURIComponent(machineId)}`,
    { cache: "no-store" },
  );
  if (!resp.ok) {
    throw new Error(`Failed to load knowledge base documents (${resp.status})`);
  }
  const data = (await resp.json()) as DocumentApiOut[];
  return data.map(fromApi);
}
