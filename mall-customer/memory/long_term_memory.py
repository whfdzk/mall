"""
长期记忆 — 基于向量数据库的持久化记忆
存储用户画像、历史工单、知识库文档等需要持久化的信息。
支持语义相似度检索，用于RAG知识检索Agent。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None


# 常见 Embedding 模型的输出维度（用于自动确定 FAISS 索引维度）
_EMBEDDING_DIMS: dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "BAAI/bge-large-zh-v1.5": 1024,
    "BAAI/bge-large-zh": 1024,
    "BAAI/bge-m3": 1024,
}


class LongTermMemory:
    """
    长期记忆：基于FAISS的向量检索。

    特点：
    - 向量化存储，支持语义相似度检索
    - 持久化到磁盘，跨会话保持
    - 支持增量更新和批量导入
    - 生产环境可切换为Milvus/Pinecone

    文档分块策略：
    - 固定长度分块 (512 tokens) + 重叠窗口 (128 tokens)
    - 按段落自然分割优先
    """

    def __init__(
        self,
        index_path: str = "./vector_store/faiss_index",
        embedding_dim: int | None = None,
    ):
        self.index_path = Path(index_path)
        self.embedding_dim = self._resolve_embedding_dim(embedding_dim)
        self._documents: list[dict[str, Any]] = []
        self._index = None
        self._openai_embeddings = None
        self._embedding_failed = False
        self._init_embeddings()
        self._init_index()

    @staticmethod
    def _resolve_embedding_dim(embedding_dim: int | None) -> int:
        """确定向量维度：显式参数 > EMBEDDING_DIM 环境变量 > 已知模型映射 > 默认 1536"""
        if embedding_dim is not None:
            return embedding_dim
        env_dim = os.getenv("EMBEDDING_DIM", "").strip()
        if env_dim.isdigit():
            return int(env_dim)
        model_name = os.getenv("EMBEDDING_MODEL_NAME", "")
        return _EMBEDDING_DIMS.get(model_name, 1536)

    def _init_index(self):
        """初始化FAISS索引"""
        if faiss is None:
            self._index = None
            return

        metadata_path = self.index_path.with_suffix(".meta.json")
        if self.index_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
                if self._index.d != self.embedding_dim:
                    print(
                        f"[LongTermMemory] 索引维度 {self._index.d} 与当前向量维度 "
                        f"{self.embedding_dim} 不一致，重建索引"
                    )
                    self._index = faiss.IndexFlatIP(self.embedding_dim)
                    self._documents = []
                elif metadata_path.exists():
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        self._documents = json.load(f)
            except Exception:
                self._index = faiss.IndexFlatIP(self.embedding_dim)
        else:
            self._index = faiss.IndexFlatIP(self.embedding_dim)

    def _init_embeddings(self):
        """初始化向量化模型：优先 EMBEDDING_* 专属配置，否则回退 OPENAI_*。

        对话模型与向量模型常由不同厂商提供（如讯飞对话 + 硅基流动向量），
        因此向量模型使用独立的 EMBEDDING_API_KEY / EMBEDDING_BASE_URL，
        未配置时回退到 OPENAI_API_KEY / OPENAI_BASE_URL（单厂商场景）。
        """
        api_key = (os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            self._openai_embeddings = None
            return

        try:
            from langchain_openai import OpenAIEmbeddings

            self._openai_embeddings = OpenAIEmbeddings(
                model=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-ada-002"),
                openai_api_key=api_key,
                openai_api_base=(os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL")) or None,
                # 关闭长度安全检查：否则 langchain 会用 tiktoken 把文本转成 token ID 整数发送，
                # 硅基流动等第三方兼容端点只接受原始字符串，会导致 400 参数错误。
                check_embedding_ctx_length=False,
            )
        except Exception as exc:  # 配置错误时降级为本地哈希向量
            print(f"[LongTermMemory] 初始化 OpenAI Embedding 失败，降级为本地哈希向量: {exc}")
            self._openai_embeddings = None

    def _hash_embedding(self, text: str) -> np.ndarray:
        """本地确定性特征哈希向量（无 Key 降级方案）。

        对英文/数字按词、对中文按字 + 二元组切分，哈希到固定维度后
        做 sublinear TF + L2 归一化。相比旧的随机向量，共享字词会产生
        真实的余弦相似度，语义检索可用且确定、可复现。
        """
        text = text.lower()
        features: list[str] = re.findall(r"[a-z0-9]+", text)

        cjk = re.findall(r"[\u4e00-\u9fff]", text)
        features.extend(cjk)
        features.extend(a + b for a, b in zip(cjk, cjk[1:]))

        vec = np.zeros(self.embedding_dim, dtype=np.float32)
        for feat in features:
            bucket = int(hashlib.sha256(feat.encode()).hexdigest()[:8], 16) % self.embedding_dim
            vec[bucket] += 1.0

        vec = np.log1p(vec)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.astype(np.float32)

    def _embed(self, text: str) -> np.ndarray:
        """返回文本的向量表示：优先真实 Embedding，否则哈希特征向量。

        远程 Embedding 一旦调用失败（如讯飞 MaaS 不提供 OpenAI 兼容的
        embedding 端点），就记住失败状态，后续直接走本地哈希，避免每次
        检索都重复发起注定失败的远程请求。
        """
        if self._openai_embeddings is not None and not self._embedding_failed:
            try:
                return np.asarray(self._openai_embeddings.embed_query(text), dtype=np.float32)
            except Exception as exc:
                print(f"[LongTermMemory] OpenAI Embedding 调用失败，回退哈希向量: {exc}")
                self._embedding_failed = True
        return self._hash_embedding(text)

    def add_document(self, content: str, source: str = "", metadata: dict | None = None) -> str:
        """添加文档到向量库（幂等：相同内容不会重复入库）"""
        doc_id = hashlib.md5(content.encode()).hexdigest()[:12]
        if any(d["id"] == doc_id for d in self._documents):
            return doc_id

        doc = {
            "id": doc_id,
            "content": content,
            "source": source,
            "metadata": metadata or {},
        }
        self._documents.append(doc)

        if self._index is not None:
            embedding = self._embed(content)
            self._index.add(embedding.reshape(1, -1))

        return doc_id

    def add_documents_batch(self, documents: list[dict]) -> list[str]:
        """批量添加文档"""
        doc_ids = []
        for doc in documents:
            doc_id = self.add_document(
                content=doc.get("content", ""),
                source=doc.get("source", ""),
                metadata=doc.get("metadata", {}),
            )
            doc_ids.append(doc_id)
        return doc_ids

    def remove_by_source(self, source: str, keep_ids: set[str] | None = None) -> int:
        """按来源移除文档，返回移除数量。

        Args:
            source: 要清理的文档来源（如 "mall-server/products"）。
            keep_ids: 可选，保留的文档 id 集合；不在该集合内的同来源文档视为过期（如已下架商品）。

        FAISS 的 IndexFlatIP 不支持逐条删除，移除后从剩余文档重建索引。
        """
        remaining: list[dict[str, Any]] = []
        removed = 0
        for doc in self._documents:
            if doc.get("source") == source and (keep_ids is None or doc["id"] not in keep_ids):
                removed += 1
            else:
                remaining.append(doc)

        if removed == 0:
            return 0

        self._documents = remaining
        self._rebuild_index()
        return removed

    def _rebuild_index(self) -> None:
        """从当前文档列表重建 FAISS 索引（保持索引顺序与 _documents 一致）。"""
        if faiss is None:
            self._index = None
            return
        self._index = faiss.IndexFlatIP(self.embedding_dim)
        for doc in self._documents:
            embedding = self._embed(doc["content"])
            self._index.add(embedding.reshape(1, -1))

    def is_empty(self) -> bool:
        """知识库是否为空（用于启动时判断是否需要播种默认文档）"""
        return not self._documents

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义相似度检索"""
        if self._index is None or not self._documents:
            return self._fallback_search(query, top_k)

        query_vec = self._embed(query).reshape(1, -1)
        scores, indices = self._index.search(query_vec, min(top_k, len(self._documents)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._documents):
                continue
            doc = self._documents[idx].copy()
            doc["score"] = float(score)
            results.append(doc)

        return results

    def _fallback_search(self, query: str, top_k: int) -> list[dict]:
        """当FAISS不可用时的关键词回退搜索"""
        scored = []
        query_terms = set(query.lower().split())

        for doc in self._documents:
            content_lower = doc["content"].lower()
            score = sum(1 for term in query_terms if term in content_lower)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def save(self):
        """持久化索引到磁盘"""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        if self._index is not None:
            faiss.write_index(self._index, str(self.index_path))

        metadata_path = self.index_path.with_suffix(".meta.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self._documents, f, ensure_ascii=False, indent=2)

    def load_knowledge_base(self, kb_dir: str) -> int:
        """从目录批量加载知识库文档"""
        kb_path = Path(kb_dir)
        if not kb_path.exists():
            return 0

        count = 0
        for file_path in kb_path.glob("**/*.txt"):
            content = file_path.read_text(encoding="utf-8")
            chunks = self._chunk_text(content)
            for chunk in chunks:
                self.add_document(
                    content=chunk,
                    source=str(file_path.name),
                    metadata={"file": str(file_path)},
                )
                count += 1

        return count

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 128) -> list[str]:
        """
        文本分块：固定长度 + 重叠窗口。
        优先按段落分割，段落过长则按句子分割。
        """
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    current_chunk = overlap_text + para + "\n\n"
                else:
                    sentences = para.replace("。", "。\n").replace(".", ".\n").split("\n")
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        if len(current_chunk) + len(sentence) <= chunk_size:
                            current_chunk += sentence
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:chunk_size]]