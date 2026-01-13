#!/usr/bin/env python3
"""
Test script to validate Mermaid diagram syntax
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SYSTEM_DIAGRAM = PROJECT_ROOT / "code-graph" / "visuals" / "SYSTEM_DIAGRAM.md"


def extract_mermaid_code(markdown_file):
    """Extract mermaid code block from markdown"""
    content = markdown_file.read_text()
    pattern = r"```mermaid\n(.*?)\n```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def test_no_duplicate_node_ids(mermaid_code):
    """Test that all node IDs are unique"""
    # Find all node definitions: NODE_ID[label]
    node_pattern = r"(\w+)\["
    node_ids = re.findall(node_pattern, mermaid_code)

    # Exclude reserved keywords
    reserved = {"graph", "subgraph", "end", "class", "classDef"}
    node_ids = [nid for nid in node_ids if nid not in reserved]

    duplicates = [nid for nid in set(node_ids) if node_ids.count(nid) > 1]

    if duplicates:
        print(f"❌ FAIL: Duplicate node IDs found: {duplicates}")
        return False

    print(f"✅ PASS: No duplicate node IDs ({len(set(node_ids))} unique nodes)")
    return True


def test_consistent_indentation(mermaid_code):
    """Test that nodes in subgraphs have consistent and correct indentation (8 or 12 spaces for nested)"""
    lines = mermaid_code.split("\n")

    subgraph_stack = []  # Track nested subgraphs
    node_indents = []
    issues = []

    for i, line in enumerate(lines, 1):
        if "subgraph" in line and not line.strip().startswith("%%"):
            # Entering a subgraph
            indent = len(line) - len(line.lstrip())
            subgraph_stack.append({"name": line.strip(), "indent": indent, "nodes": []})
        elif line.strip() == "end" and subgraph_stack:
            # Exiting a subgraph - check node indents
            current_subgraph = subgraph_stack.pop()
            if current_subgraph["nodes"]:
                unique_indents = set(current_subgraph["nodes"])
                if len(unique_indents) > 1:
                    issues.append(
                        f"Line {i}: {current_subgraph['name']} has inconsistent indents: {unique_indents}"
                    )
                # Allow 8 or 12 spaces (for nested subgraphs)
                elif not any(indent in [8, 12] for indent in unique_indents):
                    issues.append(
                        f"Line {i}: {current_subgraph['name']} nodes should have 8 or 12 spaces, found: {unique_indents}"
                    )
        elif subgraph_stack and "[" in line and "subgraph" not in line:
            # This is a node definition inside a subgraph
            indent = len(line) - len(line.lstrip())
            subgraph_stack[-1]["nodes"].append(indent)

    if issues:
        print("❌ FAIL: Incorrect indentation:")
        for issue in issues:
            print(f"  {issue}")
        return False

    print("✅ PASS: All subgraph nodes have correct indentation (8 or 12 spaces for nested)")
    return True


def test_valid_connections(mermaid_code):
    """Test that all connections reference defined nodes"""
    # Find all node definitions
    node_pattern = r"(\w+)\["
    defined_nodes = set(re.findall(node_pattern, mermaid_code))

    # Find all node references in connections
    connection_pattern = r"(\w+)\s*(?:-->|<-->|---|\.->)"
    referenced_nodes = set(re.findall(connection_pattern, mermaid_code))

    # Nodes referenced but not defined
    undefined = referenced_nodes - defined_nodes

    if undefined:
        print(f"❌ FAIL: Connections reference undefined nodes: {undefined}")
        return False

    print("✅ PASS: All connections reference defined nodes")
    return True


def test_no_empty_labels(mermaid_code):
    """Test that no nodes have empty labels"""
    # Find nodes with empty or very short labels
    empty_pattern = r"\w+\[\s*<br/>\s*\]"
    if re.search(empty_pattern, mermaid_code):
        print("❌ FAIL: Found nodes with empty labels")
        return False

    print("✅ PASS: No empty node labels")
    return True


def main():
    print("🧪 Testing Mermaid Diagram Syntax\n")

    if not SYSTEM_DIAGRAM.exists():
        print(f"❌ ERROR: {SYSTEM_DIAGRAM} not found")
        sys.exit(1)

    mermaid_code = extract_mermaid_code(SYSTEM_DIAGRAM)
    if not mermaid_code:
        print(f"❌ ERROR: No mermaid code block found in {SYSTEM_DIAGRAM}")
        sys.exit(1)

    print(f"📄 Testing: {SYSTEM_DIAGRAM.name}\n")

    tests = [
        test_no_duplicate_node_ids,
        test_consistent_indentation,
        test_valid_connections,
        test_no_empty_labels,
    ]

    results = [test(mermaid_code) for test in tests]

    print(f"\n{'=' * 60}")
    if all(results):
        print(f"✅ All tests passed ({len(results)}/{len(results)})")
        sys.exit(0)
    else:
        failed = len([r for r in results if not r])
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
