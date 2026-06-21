#!/usr/bin/env python3
"""
FinTwin — Test RAG Retrieval
----------------------------
Rebuilds the vector index from knowledge_base/ documents, runs sample semantic queries,
and outputs the results for manual verification.
"""

from rag_engine import build_rag_index, search_product_policy

def print_search_results(query: str, results: list[dict]):
    print("=" * 80)
    print(f"QUERY: '{query}'")
    print("=" * 80)
    
    for i, res in enumerate(results, 1):
        print(f"Match #{i} [Score: {res['similarity_score']:.4f}]")
        print(f"Product: {res['product_name']} | Section: {res['section_name']}")
        print(f"Source:  {res['source_file']}")
        print("-" * 40)
        print(res['text'])
        print("=" * 80)
    print("\n")

def main():
    # 1. Force index rebuild
    build_rag_index()
    print("\n" + "#" * 80)
    print("RUNNING SEMANTIC SEARCH RETRIEVAL TESTS")
    print("#" * 80 + "\n")
    
    test_queries = [
        "personal loan eligibility for a 22 year old",
        "fixed deposit interest rates and minimum tenure",
        "investment options for long term wealth building"
    ]
    
    for query in test_queries:
        results = search_product_policy(query, top_k=3)
        print_search_results(query, results)

if __name__ == "__main__":
    main()
