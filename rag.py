

from pathlib import Path
from datetime import date
import re

import numpy as np
from sentence_transformers import SentenceTransformer



KNOWLEDGE_BASE_DIR = (
    Path(__file__).parent / "knowledge-base"
)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

DEFAULT_TOP_K = 8

# Semantic similarity threshold.
MIN_RELEVANCE_SCORE = 0.28

# Minimum score for a result to participate in
# strong conflict detection.
MIN_CONFLICT_SCORE = 0.30



print("Loading embedding model...")

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)



def parse_front_matter(content: str):
   
    

    if not content.startswith("---"):
        return {}, content.strip()

    match = re.search(
        r"^---\s*\n(.*?)\n---\s*\n",
        content,
        re.DOTALL
    )

    if not match:
        return {}, content.strip()

    metadata_text = match.group(1)
    document_text = content[match.end():].strip()

    metadata = {}

    for line in metadata_text.splitlines():

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        key = key.strip()
        value = value.strip()

        metadata[key] = value

    return metadata, document_text



def load_documents():
    

    if not KNOWLEDGE_BASE_DIR.exists():

        raise FileNotFoundError(
            f"Knowledge base directory not found: "
            f"{KNOWLEDGE_BASE_DIR}"
        )

    documents = []

    for file_path in sorted(
        KNOWLEDGE_BASE_DIR.glob("*.md")
    ):

        content = file_path.read_text(
            encoding="utf-8"
        )

        metadata, text = parse_front_matter(
            content
        )

        metadata = metadata.copy()

        # Always preserve filename.
        metadata["source"] = file_path.name

        documents.append(
            {
                "text": text,
                "metadata": metadata
            }
        )

    return documents



def chunk_document(document):
    
    text = document["text"]

    # Split immediately before Markdown headings.
    sections = re.split(
        r"\n(?=#{1,6}\s+)",
        text
    )

    chunks = []

    for section in sections:

        section = section.strip()

        if not section:
            continue

        lines = section.splitlines()

        heading = ""
        content_lines = lines

        # Extract heading.
        if lines and re.match(
            r"^#{1,6}\s+",
            lines[0]
        ):

            heading = re.sub(
                r"^#{1,6}\s+",
                "",
                lines[0]
            ).strip()

            content_lines = lines[1:]

        content = "\n".join(
            content_lines
        ).strip()

        if not content:
            continue

        metadata = {
            **document["metadata"],
            "heading": heading
        }

        # Text used by semantic retrieval.
        search_text = " ".join(
            [
                metadata.get("title", ""),
                heading,
                content
            ]
        ).strip()

        chunk = {
            "text": content,
            "search_text": search_text,
            "metadata": metadata
        }

        chunks.append(chunk)

    return chunks


def create_chunks(documents):
   

    all_chunks = []

    for document in documents:

        all_chunks.extend(
            chunk_document(document)
        )

    return all_chunks



def create_embeddings(chunks):
    

    if not chunks:
        return np.empty((0, 0))

    texts = [
        chunk["search_text"]
        for chunk in chunks
    ]

    embeddings = embedding_model.encode(
        texts,
        normalize_embeddings=True
    )

    return np.asarray(
        embeddings,
        dtype=np.float32
    )



def _status(metadata):
    return (
        metadata.get("status", "")
        .strip()
        .lower()
    )


def _authority(metadata):
    return (
        metadata.get(
            "policy_authority",
            ""
        )
        .strip()
        .lower()
    )


def _is_active(metadata):
    return _status(metadata) == "active"


def _is_superseded(metadata):
    return _status(metadata) in {
        "superseded",
        "legacy",
        "inactive",
        "deprecated"
    }


def _is_official(metadata):
    return _authority(metadata) == "official"


def _is_internal(metadata):
    

    audience = (
        metadata.get("audience", "")
        .strip()
        .lower()
    )

    source = (
        metadata.get("source", "")
        .strip()
        .lower()
    )

    title = (
        metadata.get("title", "")
        .strip()
        .lower()
    )

    return (
        audience == "internal"
        or "internal" in source
        or "internal" in title
        or _authority(metadata) in {
            "none",
            "internal",
            "draft"
        }
    )


def _effective_date(metadata):
    

    value = metadata.get(
        "effective_date"
    )

    if not value:
        return None

    try:

        return date.fromisoformat(
            value.strip()
        )

    except ValueError:

        return None



def retrieve(
    query,
    chunks,
    embeddings,
    top_k=DEFAULT_TOP_K
):
    

    if not query or not query.strip():
        return []

    if not chunks:
        return []

    if embeddings.size == 0:
        return []

    query = query.strip()

    query_embedding = embedding_model.encode(
        [query],
        normalize_embeddings=True
    )[0]

    scores = np.dot(
        embeddings,
        query_embedding
    )

    top_k = min(
        top_k,
        len(chunks)
    )

    top_indices = np.argsort(
        scores
    )[::-1][:top_k]

    results = []

    for index in top_indices:

        chunk = chunks[index]

        results.append(
            {
                "text": chunk["text"],
                "search_text": chunk["search_text"],
                "metadata": chunk["metadata"].copy(),
                "original_score": float(
                    scores[index]
                ),
                "score": float(
                    scores[index]
                )
            }
        )

    return results



def rerank_results(results):
    

    today = date.today()

    for result in results:

        metadata = result["metadata"]

        bonus = 0.0


        if _is_active(metadata):

            bonus += 0.18


        if _is_official(metadata):

            bonus += 0.15


        audience = (
            metadata.get(
                "audience",
                ""
            )
            .strip()
            .lower()
        )

        if audience == "customer":

            bonus += 0.04


        if _is_superseded(metadata):

            bonus -= 0.30


        if _is_internal(metadata):

            bonus -= 0.25


        effective_date = _effective_date(
            metadata
        )

        if effective_date:

            if effective_date > today:

                # Future policies should not be treated
                # as current authority.
                bonus -= 0.20

            else:

                days_old = (
                    today - effective_date
                ).days

                # Small bounded recency bonus.
                recency_bonus = min(
                    0.05,
                    max(
                        0.0,
                        0.05
                        - days_old / 3650
                    )
                )

                bonus += recency_bonus

        result["metadata_bonus"] = bonus

        result["score"] = (
            result["original_score"]
            + bonus
        )

    results.sort(
        key=lambda result: result["score"],
        reverse=True
    )

    return results



def filter_relevant_results(
    results,
    min_score=MIN_RELEVANCE_SCORE
):
    
    return [
        result
        for result in results
        if result["original_score"]
        >= min_score
    ]



def normalize_text(text):
    

    text = text.lower()

    text = text.replace(
        "–",
        "-"
    )

    text = text.replace(
        "—",
        "-"
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def chunk_topics(chunk):
    

    text = normalize_text(
        chunk.get(
            "search_text",
            chunk.get("text", "")
        )
    )

    metadata = chunk.get(
        "metadata",
        {}
    )

    title = normalize_text(
        metadata.get(
            "title",
            ""
        )
    )

    heading = normalize_text(
        metadata.get(
            "heading",
            ""
        )
    )

    combined = (
        f"{title} {heading} {text}"
    )

    topics = set()


    if any(
        word in combined
        for word in [
            "return",
            "returns",
            "return window",
            "refund"
        ]
    ):

        topics.add("returns")


    if any(
        word in combined
        for word in [
            "shipping",
            "ship",
            "delivery",
            "canada",
            "international"
        ]
    ):

        topics.add("shipping")


    if "warranty" in combined:

        topics.add("warranty")


    if any(
        word in combined
        for word in [
            "product care",
            "cleaning",
            "dishwasher",
            "hand-washed",
            "hand washed"
        ]
    ):

        topics.add("product_care")


    if "breeze tumbler" in combined:

        topics.add("breeze_tumbler")


    if any(
        phrase in combined
        for phrase in [
            "damaged item",
            "wrong item",
            "broken zipper"
        ]
    ):

        topics.add("damaged_items")


    if any(
        word in combined
        for word in [
            "cancel",
            "cancellation"
        ]
    ):

        topics.add("cancellation")


    if any(
        word in combined
        for word in [
            "trailplus",
            "membership"
        ]
    ):

        topics.add("membership")

    return topics



def _contains_any(text, phrases):
    

    return any(
        phrase in text
        for phrase in phrases
    )


def _has_returns_window_conflict(text_a, text_b):
    

    a = normalize_text(text_a)
    b = normalize_text(text_b)

    days_a = set(
        re.findall(
            r"\b(\d+)\s*(?:calendar\s*)?days?\b",
            a
        )
    )

    days_b = set(
        re.findall(
            r"\b(\d+)\s*(?:calendar\s*)?days?\b",
            b
        )
    )

    # Only treat it as a conflict if both chunks
    # explicitly discuss returns and contain different
    # return-window values.
    if (
        "return" in a
        and "return" in b
        and days_a
        and days_b
        and days_a != days_b
    ):

        return True

    return False


def _has_dishwasher_conflict(text_a, text_b):
     
    a = normalize_text(text_a)
    b = normalize_text(text_b)

    def says_body_handwash(text):
        return (
            (
                "body" in text
                and "hand-wash" in text
            )
            or
            (
                "body" in text
                and "hand wash" in text
            )
        )

    def says_all_dishwasher_safe(text):
        return (
            "all components are dishwasher safe" in text
            or
            "all components dishwasher safe" in text
            or
            "all components are dishwasher-safe" in text
        )

    return (
        (
            says_body_handwash(a)
            and says_all_dishwasher_safe(b)
        )
        or
        (
            says_body_handwash(b)
            and says_all_dishwasher_safe(a)
        )
    )

def _has_shipping_conflict(text_a, text_b):
    
    a = normalize_text(text_a)
    b = normalize_text(text_b)

    countries = [
        "canada",
        "germany",
        "united kingdom",
        "uk",
        "australia",
        "japan"
    ]

    for country in countries:

        if country not in a or country not in b:
            continue

        supported_a = _contains_any(
            a,
            [
                f"{country} is supported",
                f"ship to {country}",
                f"shipping to {country} is available"
            ]
        )

        unsupported_a = _contains_any(
            a,
            [
                f"{country} is not supported",
                f"shipping to {country} is not available",
                f"do not ship to {country}"
            ]
        )

        supported_b = _contains_any(
            b,
            [
                f"{country} is supported",
                f"ship to {country}",
                f"shipping to {country} is available"
            ]
        )

        unsupported_b = _contains_any(
            b,
            [
                f"{country} is not supported",
                f"shipping to {country} is not available",
                f"do not ship to {country}"
            ]
        )

        if (
            supported_a
            and unsupported_b
        ) or (
            supported_b
            and unsupported_a
        ):

            return True

    return False


def chunks_conflict(chunk_a, chunk_b):
    

    metadata_a = chunk_a["metadata"]
    metadata_b = chunk_b["metadata"]

    topics_a = chunk_topics(chunk_a)
    topics_b = chunk_topics(chunk_b)

    shared_topics = (
        topics_a & topics_b
    )

    if not shared_topics:
        return False

    text_a = chunk_a.get(
        "text",
        ""
    )

    text_b = chunk_b.get(
        "text",
        ""
    )


    if (
        "breeze_tumbler" in shared_topics
        or "product_care" in shared_topics
    ):

        if _has_dishwasher_conflict(
            text_a,
            text_b
        ):

            return True


    if "returns" in shared_topics:

        if _has_returns_window_conflict(
            text_a,
            text_b
        ):

            return True


    if "shipping" in shared_topics:

        if _has_shipping_conflict(
            text_a,
            text_b
        ):

            return True

    return False



def detect_conflicts(results):
    

    candidates = []

    for result in results:

        metadata = result["metadata"]

        if result["original_score"] < MIN_CONFLICT_SCORE:
            continue

        if not _is_active(metadata):
            continue

        if not _is_official(metadata):
            continue

        if _is_internal(metadata):
            continue

        candidates.append(result)

    conflicts = []

    # Compare pairs.
    for i in range(
        len(candidates)
    ):

        for j in range(
            i + 1,
            len(candidates)
        ):

            first = candidates[i]
            second = candidates[j]

            if chunks_conflict(
                first,
                second
            ):

                topic_set = (
                    chunk_topics(first)
                    & chunk_topics(second)
                )

                topic = (
                    sorted(topic_set)[0]
                    if topic_set
                    else "policy"
                )

                conflicts.append(
                    {
                        "topic": topic,
                        "results": [
                            first,
                            second
                        ]
                    }
                )

    return conflicts



def build_citation(result):
    

    metadata = result["metadata"]

    source = metadata.get(
        "source",
        "unknown source"
    )

    heading = metadata.get(
        "heading",
        ""
    )

    if heading:

        return (
            f"{source} — {heading}"
        )

    return source


def build_citations(results):
   

    citations = []

    seen = set()

    for result in results:

        citation = build_citation(
            result
        )

        if citation not in seen:

            citations.append(
                citation
            )

            seen.add(citation)

    return citations



def format_evidence(results):
    

    blocks = []

    for i, result in enumerate(
        results,
        start=1
    ):

        metadata = result["metadata"]

        source = metadata.get(
            "source",
            "unknown"
        )

        heading = metadata.get(
            "heading",
            ""
        )

        status = metadata.get(
            "status",
            ""
        )

        authority = metadata.get(
            "policy_authority",
            ""
        )

        block = (
            f"[EVIDENCE {i}]\n"
            f"Source: {source}\n"
            f"Heading: {heading}\n"
            f"Status: {status}\n"
            f"Authority: {authority}\n"
            f"Similarity: "
            f"{result['original_score']:.4f}\n"
            f"Content:\n"
            f"{result['text']}\n"
            f"[/EVIDENCE {i}]"
        )

        blocks.append(block)

    return "\n\n".join(
        blocks
    )



def format_conflicts(conflicts):
    

    if not conflicts:
        return ""

    blocks = []

    for conflict in conflicts:

        topic = conflict.get(
            "topic",
            "policy"
        )

        blocks.append(
            f"CONFLICT TOPIC: {topic}"
        )

        for result in conflict["results"]:

            blocks.append(
                (
                    f"Source: "
                    f"{build_citation(result)}\n"
                    f"Content: "
                    f"{result['text']}"
                )
            )

    return "\n\n".join(
        blocks
    )



def search_knowledge_base(
    query,
    chunks,
    embeddings,
    top_k=DEFAULT_TOP_K,
    min_score=MIN_RELEVANCE_SCORE
):
    


    if not query or not query.strip():

        return {
            "found": False,
            "abstain": True,
            "reason": "empty_query",
            "results": [],
            "citations": [],
            "evidence": "",
            "conflicts": [],
            "conflict_summary": ""
        }


    results = retrieve(
        query=query,
        chunks=chunks,
        embeddings=embeddings,
        top_k=top_k
    )

    if not results:

        return {
            "found": False,
            "abstain": True,
            "reason": "no_results",
            "results": [],
            "citations": [],
            "evidence": "",
            "conflicts": [],
            "conflict_summary": ""
        }


    results = rerank_results(
        results
    )


    relevant_results = filter_relevant_results(
        results,
        min_score=min_score
    )

    if not relevant_results:

        return {
            "found": False,
            "abstain": True,
            "reason": "insufficient_evidence",
            "results": [],
            "citations": [],
            "evidence": "",
            "conflicts": [],
            "conflict_summary": ""
        }


    conflicts = detect_conflicts(
        relevant_results
    )


    citations = build_citations(
        relevant_results
    )


    evidence = format_evidence(
        relevant_results
    )


    conflict_summary = format_conflicts(
        conflicts
    )

    return {
        "found": True,
        "abstain": False,
        "reason": None,
        "results": relevant_results,
        "citations": citations,
        "evidence": evidence,
        "conflicts": conflicts,
        "conflict_summary": conflict_summary
    }



def build_rag_index():
    

    documents = load_documents()

    chunks = create_chunks(
        documents
    )

    embeddings = create_embeddings(
        chunks
    )

    return chunks, embeddings



def print_search_result(
    query,
    response
):
   
    print("\n" + "=" * 70)
    print("QUERY")
    print("=" * 70)

    print(query)

    if response["abstain"]:

        print("\nABSTAIN")
        print(
            "Reason:",
            response["reason"]
        )

        return

    print(
        f"\nRelevant results: "
        f"{len(response['results'])}"
    )

    for i, result in enumerate(
        response["results"],
        start=1
    ):

        metadata = result["metadata"]

        print(
            "\n" + "-" * 70
        )

        print(
            f"Result {i}"
        )

        print(
            "Original similarity:",
            f"{result['original_score']:.4f}"
        )

        print(
            "Metadata bonus:",
            f"{result['metadata_bonus']:.4f}"
        )

        print(
            "Final ranking score:",
            f"{result['score']:.4f}"
        )

        print(
            "Source:",
            metadata.get("source")
        )

        print(
            "Heading:",
            metadata.get("heading")
        )

        print(
            "Title:",
            metadata.get("title")
        )

        print(
            "Status:",
            metadata.get("status")
        )

        print(
            "Authority:",
            metadata.get(
                "policy_authority"
            )
        )

        print(
            "\nText:"
        )

        print(
            result["text"]
        )


    print(
        "\n" + "=" * 70
    )

    print(
        "CONFLICT CHECK"
    )

    print(
        "=" * 70
    )

    if response["conflicts"]:

        print(
            "GENUINE ACTIVE-SOURCE CONFLICT DETECTED"
        )

        for conflict in response[
            "conflicts"
        ]:

            print(
                f"\nTopic: "
                f"{conflict['topic']}"
            )

            for result in conflict[
                "results"
            ]:

                print(
                    f"- {build_citation(result)}"
                )

                print(
                    f"  {result['text']}"
                )

    else:

        print(
            "No genuine active-source conflicts detected."
        )


    print(
        "\n" + "=" * 70
    )

    print(
        "CITATIONS"
    )

    print(
        "=" * 70
    )

    for citation in response[
        "citations"
    ]:

        print(
            f"- {citation}"
        )



if __name__ == "__main__":

    print("=" * 70)
    print("ASTER & ROW RAG KNOWLEDGE BASE")
    print("=" * 70)


    documents = load_documents()

    print(
        f"Documents loaded: "
        f"{len(documents)}"
    )


    chunks = create_chunks(
        documents
    )

    print(
        f"Chunks created: "
        f"{len(chunks)}"
    )


    missing_search_text = [
        i
        for i, chunk in enumerate(chunks)
        if "search_text" not in chunk
    ]

    if missing_search_text:

        raise RuntimeError(
            "Some chunks are missing search_text: "
            f"{missing_search_text}"
        )

    print(
        "search_text validation: PASSED"
    )


    print(
        "\nCreating embeddings..."
    )

    embeddings = create_embeddings(
        chunks
    )

    print(
        f"Embedding shape: "
        f"{embeddings.shape}"
    )


    response = search_knowledge_base(
        query=(
            "How long do I have to return "
            "an unused backpack?"
        ),
        chunks=chunks,
        embeddings=embeddings
    )

    print_search_result(
        "How long do I have to return an unused backpack?",
        response
    )


    response = search_knowledge_base(
        query=(
            "My TrailPlus membership was active "
            "when I ordered. What is my return window?"
        ),
        chunks=chunks,
        embeddings=embeddings
    )

    print_search_result(
        (
            "My TrailPlus membership was active "
            "when I ordered. What is my return window?"
        ),
        response
    )


    response = search_knowledge_base(
        query=(
            "Can I put the entire Breeze Tumbler "
            "in the dishwasher?"
        ),
        chunks=chunks,
        embeddings=embeddings
    )

    print_search_result(
        (
            "Can I put the entire Breeze Tumbler "
            "in the dishwasher?"
        ),
        response
    )


    response = search_knowledge_base(
        query=(
            "Do you ship internationally? "
            "What about Canada?"
        ),
        chunks=chunks,
        embeddings=embeddings
    )

    print_search_result(
        (
            "Do you ship internationally? "
            "What about Canada?"
        ),
        response
    )


    response = search_knowledge_base(
        query=(
            "Do all Aster and Row products "
            "have a lifetime warranty?"
        ),
        chunks=chunks,
        embeddings=embeddings
    )

    print_search_result(
        (
            "Do all Aster and Row products "
            "have a lifetime warranty?"
        ),
        response
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "RAG DEVELOPMENT TESTS COMPLETE"
    )

    print(
        "=" * 70
    )