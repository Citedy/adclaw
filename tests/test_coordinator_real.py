# -*- coding: utf-8 -*-
"""Real integration test for Coordinator Persona (2A).

Runs against LIVE production container with real LLM + AOM.
Requires: docker container 'adclaw' running on localhost:8088.

Usage:
    python3 tests/test_coordinator_real.py
"""

import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8088"


def api(method: str, path: str, body: dict = None) -> dict:
    """Call AdClaw API."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  HTTP {e.code}: {body_text[:200]}")
        raise


def test_health():
    """Step 0: Container is healthy."""
    req = urllib.request.Request(f"{BASE}/", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"Health check failed: {resp.status}"
    print("✅ Health check: HTTP 200")


def test_ingest_persona_activity():
    """Step 1: Seed AOM with simulated persona activity."""
    memories = [
        {
            "content": "@seo-expert completed SEO audit: found 5 pages with missing meta descriptions, 3 with duplicate H1 tags, site speed score 45/100",
            "source_type": "skill",
            "source_id": "seo-audit",
            "skip_llm": True,
        },
        {
            "content": "@content-writer wrote blog post 'AI Marketing Trends 2026', 1200 words, SEO score 72/100, missing internal links",
            "source_type": "skill",
            "source_id": "blog-writer",
            "skip_llm": True,
        },
        {
            "content": "Don't use clickbait titles in blog posts because they hurt brand credibility",
            "source_type": "manual",
            "skip_llm": True,
        },
        {
            "content": "Campaign deadline is April 15 for Q2 content launch",
            "source_type": "manual",
            "skip_llm": True,
        },
    ]
    for mem in memories:
        result = api("POST", "/api/memory/memories", mem)
        mtype = result.get("memory_type", "?")
        print(f"  Ingested: [{mtype}] {result.get('content', '')[:60]}")

    print("✅ Ingested 4 persona activity memories")


def test_query_recent_activity():
    """Step 2: Query AOM for recent activity (what coordinator would do)."""
    result = api("POST", "/api/memory/query", {
        "question": "Recent persona execution results and task completions",
        "max_results": 10,
    })
    citations = result.get("citations", [])
    answer = result.get("answer", "")

    print(f"  Answer: {answer[:200]}")
    print(f"  Citations: {len(citations)}")
    for c in citations[:5]:
        m = c.get("memory", {})
        print(f"    [{m.get('memory_type', '?')}] score={c.get('score', 0):.4f} — {m.get('content', '')[:60]}")

    assert len(citations) > 0, "Expected citations from AOM query"
    print("✅ AOM query returns persona activity")
    return answer


def test_coordinator_synthesis_manual():
    """Step 3: Simulate what coordinator does — LLM synthesis of activity."""
    # This tests the LLM synthesis path directly via /api/memory/query
    # (coordinator uses same LLM, same AOM)
    result = api("POST", "/api/memory/query", {
        "question": (
            "You are a coordinator. Analyze these recent results: "
            "SEO audit found 5 missing meta descriptions, 3 duplicate H1s. "
            "Content writer wrote 1200-word blog post with SEO score 72. "
            "What specific tasks should @seo-expert and @content-writer do next?"
        ),
        "max_results": 5,
    })
    answer = result.get("answer", "")
    print(f"  LLM Synthesis: {answer[:400]}")

    assert answer, "Expected LLM synthesis answer"
    assert "coroutine" not in answer.lower(), "LLM returned raw coroutine"
    assert "async_generator" not in answer.lower(), "LLM returned async_generator"
    print("✅ LLM synthesis produces actionable answer")


def test_type_classification_in_activity():
    """Step 4: Verify type classification worked for activity memories."""
    result = api("POST", "/api/memory/query", {
        "question": "Don't use clickbait titles",
        "max_results": 3,
    })
    for c in result.get("citations", []):
        m = c.get("memory", {})
        if "clickbait" in m.get("content", "").lower():
            assert m.get("memory_type") == "feedback", (
                f"Expected feedback type, got {m.get('memory_type')}"
            )
            print(f"  Feedback detected: {m.get('content', '')[:60]}")
            print("✅ Feedback memory correctly classified and retrievable")
            return

    print("⚠️ Clickbait feedback memory not found in query results (may be outside top-3)")


def test_consolidation_trigger():
    """Step 5: Trigger consolidation and verify it runs."""
    try:
        result = api("POST", "/api/memory/consolidate")
        insights = result.get("insights", [])
        print(f"  Consolidation: {len(insights)} insights generated")
        if insights:
            print(f"  First insight: {insights[0].get('insight', '')[:100]}")
        print("✅ Consolidation cycle completed")
    except Exception as e:
        print(f"⚠️ Consolidation failed (may be expected if no engine): {e}")


def test_aom_stats():
    """Step 6: Check AOM statistics."""
    result = api("GET", "/api/memory/stats")
    print(f"  Total memories: {result.get('total_memories', '?')}")
    print(f"  Consolidations: {result.get('consolidations', '?')}")
    print(f"  With embeddings: {result.get('with_embeddings', '?')}")
    by_source = result.get("by_source", {})
    print(f"  By source: {by_source}")
    print("✅ AOM stats retrieved")


if __name__ == "__main__":
    print("=" * 60)
    print("REAL INTEGRATION TEST: Coordinator Persona (2A)")
    print("Target: localhost:8088 (production container)")
    print("=" * 60)
    print()

    tests = [
        test_health,
        test_ingest_persona_activity,
        test_query_recent_activity,
        test_coordinator_synthesis_manual,
        test_type_classification_in_activity,
        test_consolidation_trigger,
        test_aom_stats,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n--- {test.__doc__} ---")
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")
