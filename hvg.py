#!/usr/bin/env python3
"""
Samantha Hybrid-Vector-Graph Memory System
Lightweight implementation: numpy only (no heavy deps)

Core components:
- Episode store: JSON files with vector + entity + content
- Vector index: TF-IDF + numpy cosine similarity
- Graph index: pure python adjacency dict
- Hybrid retrieval: α·cosine + β·BM25 + γ·graph_rank
"""

import json, os, re
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Configuration ────────────────────────────────────────────
WORKSPACE = Path.home() / ".openclaw" / "workspace" / "samantha-hvg"
EPISODE_DIR = WORKSPACE / "episodes"
EPISODE_DIR.mkdir(parents=True, exist_ok=True)

class VectorIndex:
    """TF-IDF based vector index using pure numpy."""
    
    def __init__(self, episodes: list[dict]):
        self.episodes = episodes
        self.term_to_idx: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.episode_vectors: list[dict] = []
        self._build()
    
    def _tokenize(self, text: str) -> list[str]:
        """
        Chinese-aware tokenization: character unigrams + bigrams + ASCII words.
        
        Strategy:
        - English/ASCII words: split by underscore/camelCase, filter short (<3)
        - Chinese: unigrams + bigrams (captures multi-char term patterns)
        - Mixed: each character treated independently
        
        Bigrams are critical for Chinese: they capture semantic units like
        '心跳' (heartbeat) even without word segmentation.
        """
        import re
        tokens: list[str] = []
        for chunk in re.split(r'([\w]+)', text.lower()):
            if not chunk or re.match(r'\s', chunk):
                continue
            # Use ASCII-only \w to avoid matching Chinese chars
            if re.match(r'[a-zA-Z0-9_]', chunk):
                # ASCII word: split by underscore, filter short
                for t in chunk.split('_'):
                    if len(t) > 2:
                        tokens.append(t)
            else:
                # Non-ASCII (Chinese/punctuation): iterate each char, build unigrams + bigrams
                prev_char = None
                for i, ch in enumerate(chunk):
                    if re.match(r'\s', ch):
                        prev_char = None
                        continue
                    # Unigram
                    tokens.append(ch)
                    # Bigram with previous char (captures Chinese term patterns)
                    if prev_char is not None:
                        bigram = prev_char + ch
                        tokens.append(bigram)
                    prev_char = ch
        return tokens
    
    def _build(self):
        """Build inverted index + IDF from episodes."""
        import math
        
        doc_count = len(self.episodes)
        if doc_count == 0:
            return
        
        # Count term frequencies across all docs
        df: dict[str, int] = {}
        for ep in self.episodes:
            words = set(self._tokenize(ep.get('content', '')))
            for w in words:
                df[w] = df.get(w, 0) + 1
        
        # Build term index
        self.term_to_idx = {t: i for i, t in enumerate(sorted(df.keys()))}
        
        # Compute IDF
        for term, doc_freq in df.items():
            self.idf[term] = math.log((doc_count + 1) / (doc_freq + 1)) + 1
        
        # Build episode TF-IDF vectors
        for ep in self.episodes:
            words = self._tokenize(ep.get('content', ''))
            tf = {}
            for w in words:
                tf[w] = tf.get(w, 0) + 1
            
            vocab_size = len(self.term_to_idx)
            vec = [0.0] * vocab_size
            for term, freq in tf.items():
                if term in self.term_to_idx:
                    idx = self.term_to_idx[term]
                    tf_val = freq / max(len(words), 1)
                    vec[idx] = tf_val * self.idf.get(term, 1.0)
            
            norm = math.sqrt(sum(v * v for v in vec))
            self.episode_vectors.append(vec if norm == 0 else [v / norm for v in vec])
    
    def cosine_score(self, query: str) -> list[tuple[str, float]]:
        """Return (episode_id, score) sorted by cosine similarity."""
        import math
        
        words = self._tokenize(query)
        tf = {}
        for w in words:
            tf[w] = tf.get(w, 0) + 1
        
        vocab_size = len(self.term_to_idx)
        qvec = [0.0] * vocab_size
        for term, freq in tf.items():
            if term in self.term_to_idx:
                idx = self.term_to_idx[term]
                tf_val = freq / max(len(words), 1)
                qvec[idx] = tf_val * self.idf.get(term, 1.0)
        
        qnorm = math.sqrt(sum(v * v for v in qvec))
        if qnorm == 0:
            return []
        qvec = [v / qnorm for v in qvec]
        
        scores = []
        for i, evec in enumerate(self.episode_vectors):
            dot = sum(q * v for q, v in zip(qvec, evec))
            scores.append((self.episodes[i]['episode_id'], dot))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def bm25_score(self, query: str, k1=1.5, b=0.75) -> list[tuple[str, float]]:
        """Return (episode_id, score) sorted by BM25."""
        import math
        
        words = self._tokenize(query)
        doc_count = len(self.episodes)
        avg_dl = sum(len(self._tokenize(ep.get('content', ''))) for ep in self.episodes) / max(doc_count, 1)
        
        scores = []
        for ep in self.episodes:
            doc_words = self._tokenize(ep.get('content', ''))
            dl = len(doc_words)
            
            tf_map = {}
            for w in doc_words:
                tf_map[w] = tf_map.get(w, 0) + 1
            
            score = 0.0
            for term in words:
                if term in tf_map:
                    tf = tf_map[term]
                    idf = self.idf.get(term, 0)
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
                    score += idf * numerator / denominator
            
            scores.append((ep['episode_id'], score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores


class GraphIndex:
    """Pure python entity graph."""
    
    def __init__(self, episodes: list[dict]):
        self.adj: dict[str, set[str]] = {}
        self.entity_episodes: dict[str, list[str]] = {}
        for ep in episodes:
            for entity in ep.get('entities', []):
                if entity not in self.adj:
                    self.adj[entity] = set()
                for other in ep.get('entities', []):
                    if other != entity:
                        self.adj[entity].add(other)
                
                if entity not in self.entity_episodes:
                    self.entity_episodes[entity] = []
                self.entity_episodes[entity].append(ep['episode_id'])
    
    def get_connected_entities(self, entity: str, depth: int = 1) -> set[str]:
        """BFS to find entities connected within depth hops."""
        if entity not in self.adj:
            return set()
        visited = {entity}
        frontier = {entity}
        for _ in range(depth):
            next_frontier = set()
            for e in frontier:
                for neighbor in self.adj.get(e, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
        return visited - {entity}
    
    def get_episodes_with_entity(self, entity: str) -> list[str]:
        return self.entity_episodes.get(entity, [])
    
    def get_entity_neighbors(self, entity: str) -> list[str]:
        return list(self.adj.get(entity, set()))


class EpisodeStore:
    """JSON-based episode storage."""
    
    def __init__(self, directory: Path = EPISODE_DIR):
        self.directory = directory
    
    def save(self, episode: dict) -> str:
        ep_id = episode['episode_id']
        filepath = self.directory / f"{ep_id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(episode, f, ensure_ascii=False, indent=2)
        return ep_id
    
    def load_all(self) -> list[dict]:
        episodes = []
        for filepath in sorted(self.directory.glob("*.json")):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    episodes.append(json.load(f))
            except Exception:
                continue
        return episodes
    
    def load(self, episode_id: str) -> Optional[dict]:
        filepath = self.directory / f"{episode_id}.json"
        if not filepath.exists():
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)


class HVGMemory:
    """Main Hybrid-Vector-Graph Memory system."""
    
    def __init__(self, alpha=0.4, beta=0.4, gamma=0.2):
        self.store = EpisodeStore()
        self.alpha = alpha  # vector weight
        self.beta = beta    # BM25 weight
        self.gamma = gamma   # graph weight
        self.episodes: list[dict] = []
        self.vector_index: Optional[VectorIndex] = None
        self.graph_index: Optional[GraphIndex] = None
        self._reindex()
    
    def _reindex(self):
        """Rebuild all indices from stored episodes."""
        self.episodes = self.store.load_all()
        self.vector_index = VectorIndex(self.episodes)
        self.graph_index = GraphIndex(self.episodes)
    
    @staticmethod
    def extract_entities(content: str) -> list[str]:
        """
        Auto-extract entities from content using simple patterns.

        Extracts:
        - Quoted terms: 「X」, 【X】, "X", 'X'
        - English CamelCase words (e.g. BotLearn, TF-IDF)
        - Capitalized single words (length >= 3)
        - Chinese bracket-enclosed terms

        Returns deduplicated list of entities, filtered to terms appearing 2+ times
        or enclosed in special markers.
        """
        import re
        entities: list[str] = []

        # 1. Quoted/enclosed terms: 「X」, 【X】, 【】, "X", 'X'
        for pat in [r'[「【]([^」】]+)[」】]', r'【([^】]+)】', r'"([^"]+)"', r"'([^']+)'"]:
            entities.extend(re.findall(pat, content))

        # 2. English CamelCase: BotLearn, HybridVec, TF-IDF, GitHub
        entities.extend(re.findall(r'[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+', content))
        # Single capitalized words (>= 3 chars), avoid common English words
        english_stop = {'The', 'And', 'For', 'With', 'From', 'This', 'That', 'When', 'Then'}
        single_cap = re.findall(r'(?<![a-zA-Z])[A-Z][a-z]{2,}(?![a-zA-Z])', content)
        entities.extend(w for w in single_cap if w not in english_stop)

        # 3. Count occurrences to filter noise
        entity_counts: dict[str, int] = {}
        for ent in entities:
            entity_counts[ent] = entity_counts.get(ent, 0) + 1

        # Keep: appears 2+ times OR was explicitly quoted/bracketed
        seen: set[str] = set()
        result: list[str] = []
        quote_chars = [('「', '」'), ('【', '】'), ('"', '"'), ("'", "'")]
        for ent in entities:
            if ent in seen:
                continue
            # Check if entity appears in any quoted form
            is_quoted = any(qc[0] + ent + qc[1] in content for qc in quote_chars)
            if is_quoted or entity_counts.get(ent, 0) >= 2:
                result.append(ent)
                seen.add(ent)

        return result

    def add_episode(
        self,
        content: str,
        trigger: str,
        entities: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Add a new episode. Returns episode_id."""
        import uuid
        # Auto-extract entities if not provided
        auto_entities = self.extract_entities(content) if not entities else entities
        ep_id = f"ep-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        episode = {
            'episode_id': ep_id,
            'timestamp': datetime.now().isoformat(),
            'trigger': trigger,
            'content': content,
            'entities': auto_entities,
            'tags': tags or [],
            'metadata': metadata or {},
        }
        self.store.save(episode)
        self._reindex()
        return ep_id
    
    def search(
        self,
        query: str,
        entities_filter: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Hybrid search: combine cosine + BM25 + graph proximity.
        Auto-extracts entities from query for graph boosting if none provided.
        Returns top_k episodes with normalized scores in [0, 1].
        """
        # Auto-extract query entities if not given
        query_entities = entities_filter
        if not query_entities:
            query_entities = self.extract_entities(query)

        cosine_scores = {
            eid: score for eid, score in self.vector_index.cosine_score(query)
        }
        bm25_scores = {
            eid: score for eid, score in self.vector_index.bm25_score(query)
        }

        graph_scores: dict[str, float] = {}
        if query_entities and self.graph_index:
            # Boost: episodes containing query entities OR connected to them
            for ent in query_entities:
                for ep_id in self.graph_index.get_episodes_with_entity(ent):
                    graph_scores[ep_id] = graph_scores.get(ep_id, 0) + 2.0  # direct match = 2x
                for neighbor in self.graph_index.get_entity_neighbors(ent):
                    if neighbor != ent:
                        for ep_id in self.graph_index.get_episodes_with_entity(neighbor):
                            graph_scores[ep_id] = graph_scores.get(ep_id, 0) + 0.5  # neighbor = 0.5x

        # Normalize all scores to [0, 1] using min-max
        all_ids = set(cosine_scores) | set(bm25_scores) | set(graph_scores)

        def minmax_norm(scores_dict: dict) -> dict:
            """Min-max normalize scores to [0, 1]. Zero/non-matching values clamp to 0."""
            vals = [v for v in scores_dict.values() if v > 0]
            if not vals:
                return {k: 0.0 for k in scores_dict}
            mn, mx = min(vals), max(vals)
            if mx == mn:
                return {k: (1.0 if v > 0 else 0.0) for k, v in scores_dict.items()}
            result = {}
            for k, v in scores_dict.items():
                if v <= 0:
                    result[k] = 0.0
                else:
                    # Clamp to [0, 1] range
                    result[k] = max(0.0, min(1.0, (v - mn) / (mx - mn)))
            return result

        c_norm = minmax_norm(cosine_scores)
        b_norm = minmax_norm(bm25_scores)
        g_norm = minmax_norm(graph_scores) if graph_scores else {}

        # Character-level Jaccard fallback for episodes with zero vector/BM25 scores
        q_chars = set(query) - {' ', '　'}

        def char_jaccard(ep_content: str) -> float:
            if not q_chars:
                return 0.0
            ep_chars = set(ep_content) - {' ', '　', '\n', '\t'}
            overlap = len(q_chars & ep_chars)
            union = len(q_chars | ep_chars)
            return overlap / union if union > 0 else 0.0

        results: list[tuple[dict, float]] = []
        for ep_id in all_ids:
            c_s = c_norm.get(ep_id, 0.0)
            b_s = b_norm.get(ep_id, 0.0)
            g_s = g_norm.get(ep_id, 0.0)
            combined = self.alpha * c_s + self.beta * b_s + self.gamma * g_s

            # Fallback: if all indexed scores are 0, use character-level Jaccard
            if combined == 0.0 and q_chars:
                ep = self.store.load(ep_id)
                if ep:
                    char_sim = char_jaccard(ep.get('content', ''))
                    if char_sim > 0.05:
                        combined = char_sim * 0.5  # fallback weight capped at 0.5

            ep = self.store.load(ep_id)
            if ep:
                results.append((ep, combined))

        results.sort(key=lambda x: x[1], reverse=True)
        return [{**ep, 'hvg_score': round(score, 4)} for ep, score in results[:top_k]]
    
    def query_by_entity(self, entity: str, depth: int = 1, top_k: int = 5) -> list[dict]:
        """Graph-walk query: find entities connected to given entity."""
        neighbors = self.graph_index.get_connected_entities(entity, depth)
        all_eps = set()
        for e in [entity] + list(neighbors):
            all_eps.update(self.graph_index.get_episodes_with_entity(e))
        
        episodes = []
        for ep_id in all_eps:
            ep = self.store.load(ep_id)
            if ep:
                ep['hvg_score'] = 1.0 if entity in ep.get('entities', []) else 0.5
                episodes.append(ep)
        
        episodes.sort(key=lambda x: x['hvg_score'], reverse=True)
        return episodes[:top_k]
    
    def stats(self) -> dict:
        """Return system statistics."""
        entity_set = set()
        for ep in self.episodes:
            entity_set.update(ep.get('entities', []))
        return {
            'total_episodes': len(self.episodes),
            'total_entities': len(entity_set),
            'index_alpha': self.alpha,
            'index_beta': self.beta,
            'index_gamma': self.gamma,
        }
