"""

from __future__ import annotations

AI-powered code summarizer using Google's Gemini API.
Generates concise, context-aware summaries of code files.
"""

import hashlib
import json
import os
import time
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError(
        "GOOGLE_API_KEY environment variable not set\n"
        f"Checked .env file at: {env_path}\n"
        "Add GOOGLE_API_KEY to your .env file"
    )

genai.configure(api_key=GOOGLE_API_KEY)

# Use Gemini 2.5 Flash (fastest, most cost-effective)
model = genai.GenerativeModel("models/gemini-2.5-flash")
print("✅ Initialized model: gemini-2.5-flash")


def compute_file_hash(content: str) -> str:
    """Compute SHA-256 hash of file content for change detection"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def has_file_changed(file_path: str, old_data: dict, content: str) -> bool:
    """
    Check if file has changed significantly.

    Returns:
        True if file should be re-analyzed, False if summary can be reused
    """
    # No previous summary = needs analysis
    if "ai_summary" not in old_data:
        return True

    # No previous hash = needs analysis
    if "content_hash" not in old_data:
        return True

    # Compute current hash
    current_hash = compute_file_hash(content)
    old_hash = old_data.get("content_hash")

    # File content changed = needs re-analysis
    if current_hash != old_hash:
        return True

    # Check if file path changed (file was moved)
    if old_data.get("path") != file_path:
        return True

    # File unchanged, can reuse summary
    return False


def generate_summary(file_path: str, code_content: str, context: dict = None) -> str:
    """
    Generate AI summary for a code file with relationship context.

    Args:
        file_path: Path to the file
        code_content: The actual code content
        context: Dict with 'imports' and 'imported_by' lists

    Returns:
        AI-generated summary with relationship info
    """

    # Build context section
    context_info = ""
    if context:
        imports = context.get("imports", [])
        imported_by = context.get("imported_by", [])

        if imports or imported_by:
            context_info = "\n\nFILE RELATIONSHIPS:\n"
            if imports:
                context_info += f"- This file imports: {', '.join(imports[:5])}\n"
            if imported_by:
                context_info += f"- This file is imported by: {', '.join(imported_by[:5])}\n"

    prompt = """Analyze this code file and provide:

1. A one-sentence summary of what this file does (20-30 words)
2. A 2-3 sentence explanation of how this file relates to other parts of the codebase (focus on dependencies and usage patterns)

FILE: {file_path}

CODE:
```
{code_content[:3000]}  # First 3000 chars to stay within limits
```
{context_info}

Format your response as:
SUMMARY: [one sentence]
RELATIONSHIPS: [2-3 sentences about how this file connects to others]

Be specific about:
- What components it depends on
- What components depend on it
- Its role in the overall system (e.g., "entry point", "utility", "core logic", "API layer")
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"   ⚠️ API Error: {e}")
        return f"AI summary unavailable: {str(e)}"


def enhance_analysis_with_ai(analysis_file: str, output_file: str):
    """
    Read existing analysis and add AI summaries with relationship context.
    Uses incremental analysis - only re-generates summaries for changed files.

    Args:
        analysis_file: Path to codebase_analysis.json
        output_file: Path to save enhanced analysis
    """

    # Load existing analysis
    with open(analysis_file) as f:
        data = json.load(f)

    # Load previous summaries if they exist
    previous_summaries = {}
    if os.path.exists(output_file):
        try:
            with open(output_file) as f:
                previous_data = json.load(f)
                previous_summaries = previous_data.get("files", {})
                print(f"📚 Loaded {len(previous_summaries)} previous summaries")
        except Exception as e:
            print(f"⚠️  Could not load previous summaries: {e}")

    # Build dependency context for each file
    def build_context(file_path: str, all_files: dict) -> dict:
        """Build import/imported-by context for a file"""
        context = {"imports": [], "imported_by": []}

        # Find what this file imports
        file_data = all_files.get(file_path, {})
        imports = file_data.get("internal_imports", [])
        context["imports"] = imports

        # Find what imports this file
        for other_path, other_data in all_files.items():
            if other_path == file_path:
                continue

            other_imports = other_data.get("internal_imports", [])
            if file_path in other_imports:
                context["imported_by"].append(other_path)

        return context

    # Process all files
    all_files = data.get("files", {})

    print("🤖 Generating AI summaries with relationship context...")
    print(f"📊 Processing {len(all_files)} files\n")

    stats = {"total": len(all_files), "reused": 0, "generated": 0, "failed": 0}

    for file_path, file_data in all_files.items():
        print(f"⏳ Analyzing: {file_path}")

        # Get file content
        try:
            project_root = Path(__file__).parent.parent.parent
            full_path = project_root / file_path

            with open(full_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"   ❌ Error reading file: {e}\n")
            file_data["ai_summary"] = "File not accessible"
            stats["failed"] += 1
            continue

        # Compute content hash
        content_hash = compute_file_hash(content)
        file_data["content_hash"] = content_hash

        # Check if we can reuse previous summary
        old_data = previous_summaries.get(file_path, {})

        if not has_file_changed(file_path, old_data, content):
            # Reuse previous summary
            file_data["ai_summary"] = old_data.get("ai_summary")
            print("   ♻️  Reused existing summary (unchanged)\n")
            stats["reused"] += 1
            continue

        # File changed or no previous summary - generate new one
        print("   🔄 File changed, generating new summary...")

        # Build relationship context
        context = build_context(file_path, all_files)

        # Generate AI summary
        summary = generate_summary(file_path, content, context)
        file_data["ai_summary"] = summary

        print("   ✓ Generated new summary\n")
        stats["generated"] += 1

        # Rate limit protection
        time.sleep(1)

    # Save enhanced analysis
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Enhanced analysis saved to: {output_file}")
    print("\n📊 Summary Statistics:")
    print(f"   Total files:      {stats['total']}")
    print(f"   Reused summaries: {stats['reused']} (♻️  unchanged)")
    print(f"   New summaries:    {stats['generated']} (🔄 generated)")
    print(f"   Failed:           {stats['failed']} (❌ errors)")

    if stats["generated"] > 0:
        print(f"\n💰 API Usage: ~{stats['generated']} requests to Gemini")


def main():
    """Entry point"""
    analysis_file = Path(__file__).parent.parent / "codebase_analysis.json"
    output_file = Path(__file__).parent.parent / "codebase_analysis_with_summaries.json"

    enhance_analysis_with_ai(str(analysis_file), str(output_file))


if __name__ == "__main__":
    main()
