#!/usr/bin/env python3
"""
Update ROADMAP.md when a user story is completed.

Usage:
    python scripts/update_roadmap.py --complete US-001
    python scripts/update_roadmap.py --complete US-001 --date 2025-11-10
    python scripts/update_roadmap.py --in-progress US-003
    python scripts/update_roadmap.py --not-started US-004

This script:
1. Finds the user story in ROADMAP.md
2. Updates the status emoji (🔴 → 🟡 → ✅)
3. Adds completion date if marking as done
4. Updates the progress summary table
5. Optionally creates a git commit
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


def find_roadmap_path() -> Path:
    """Find ROADMAP.md relative to script location."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    roadmap_path = repo_root / "ROADMAP.md"

    if not roadmap_path.exists():
        print(f"❌ Error: ROADMAP.md not found at {roadmap_path}")
        sys.exit(1)

    return roadmap_path


def update_user_story_status(content: str, story_id: str, status: str, date: str = None) -> str:
    """
    Update the status of a user story in the roadmap.

    Args:
        content: Full roadmap content
        story_id: User story ID (e.g., "US-001")
        status: "done", "in_progress", or "not_started"
        date: Completion date (YYYY-MM-DD) if status is "done"

    Returns:
        Updated roadmap content
    """
    status_emoji = {
        "done": "✅ **DONE**",
        "in_progress": "🟡 **IN PROGRESS**",
        "not_started": "🔴 **NOT STARTED**",
    }

    if status not in status_emoji:
        print(f"❌ Error: Invalid status '{status}'. Must be: done, in_progress, not_started")
        sys.exit(1)

    # Find the user story section
    # Pattern: **Status**: (emoji) **STATUS**
    pattern = r"(\*\*Status\*\*:\s+)[🔴🟡✅]\s+\*\*[A-Z\s]+\*\*(\s+\([^)]+\))?"

    # Find the user story by ID (e.g., "US-001")
    story_pattern = rf"\*\*User Story\*\*:\s+\[{story_id}\]"

    lines = content.split("\n")
    updated_lines = []
    story_found = False
    status_updated = False

    for i, line in enumerate(lines):
        # Check if this line contains the user story reference
        if re.search(story_pattern, line):
            story_found = True
            # Look backwards for the status line (should be 1-2 lines above)
            for j in range(max(0, i - 5), i):
                if "**Status**:" in lines[j]:
                    # Update this status line
                    new_status = status_emoji[status]
                    if status == "done" and date:
                        new_status += f" ({date})"

                    updated_lines[j] = re.sub(pattern, rf"\1{new_status}", lines[j])
                    status_updated = True
                    break

        updated_lines.append(line)

    if not story_found:
        print(f"❌ Error: User story {story_id} not found in ROADMAP.md")
        sys.exit(1)

    if not status_updated:
        print(
            f"⚠️  Warning: Status line not found for {story_id}. "
            "Story exists but couldn't update status."
        )
        return content

    return "\n".join(updated_lines)


def update_progress_summary(content: str) -> str:
    """
    Recalculate and update the progress summary table.

    Counts:
    - Total items per phase (NOW/NEXT/LATER)
    - Completed items (✅ **DONE**)
    - In progress items (🟡 **IN PROGRESS**)
    - Not started items (🔴 **NOT STARTED**)
    """
    # Count status by phase
    phases = {"NOW": {}, "NEXT": {}, "LATER": {}}
    current_phase = None

    lines = content.split("\n")
    for line in lines:
        # Detect phase headers
        if line.startswith("## NOW"):
            current_phase = "NOW"
        elif line.startswith("## NEXT"):
            current_phase = "NEXT"
        elif line.startswith("## LATER"):
            current_phase = "LATER"
        elif line.startswith("## Overall Progress Summary") or line.startswith("## Completed Work"):
            current_phase = None  # Stop counting

        # Count status lines within phase
        if current_phase and "**Status**:" in line:
            if "✅" in line and "**DONE**" in line:
                phases[current_phase]["done"] = phases[current_phase].get("done", 0) + 1
            elif "🟡" in line and "**IN PROGRESS**" in line:
                phases[current_phase]["in_progress"] = (
                    phases[current_phase].get("in_progress", 0) + 1
                )
            elif "🔴" in line and "**NOT STARTED**" in line:
                phases[current_phase]["not_started"] = (
                    phases[current_phase].get("not_started", 0) + 1
                )

    # Calculate totals and percentages
    summary_lines = []
    summary_lines.append(
        "| Phase | Total Items | Completed | In Progress | Not Started | % Complete |"
    )
    summary_lines.append(
        "|-------|-------------|-----------|-------------|-------------|------------|"
    )

    total_all = 0
    completed_all = 0
    in_progress_all = 0
    not_started_all = 0

    for phase in ["NOW", "NEXT", "LATER"]:
        done = phases[phase].get("done", 0)
        in_prog = phases[phase].get("in_progress", 0)
        not_started = phases[phase].get("not_started", 0)
        total = done + in_prog + not_started

        pct = (done / total * 100) if total > 0 else 0

        summary_lines.append(
            f"| **{phase}** | {total} | {done} | {in_prog} | {not_started} | {pct:.0f}% |"
        )

        total_all += total
        completed_all += done
        in_progress_all += in_prog
        not_started_all += not_started

    pct_all = (completed_all / total_all * 100) if total_all > 0 else 0
    summary_lines.append(
        f"| **TOTAL** | **{total_all}** | **{completed_all}** | "
        f"**{in_progress_all}** | **{not_started_all}** | **{pct_all:.0f}%** |"
    )

    # Replace the progress summary table
    table_pattern = r"## Overall Progress Summary\n\n\| Phase.*?\n\| \*\*TOTAL\*\*.*?\|"
    new_table = "## Overall Progress Summary\n\n" + "\n".join(summary_lines)

    return re.sub(table_pattern, new_table, content, flags=re.DOTALL)


def main():
    parser = argparse.ArgumentParser(
        description="Update ROADMAP.md when completing a user story",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Mark US-001 as complete
  python scripts/update_roadmap.py --complete US-001

  # Mark US-003 as in progress
  python scripts/update_roadmap.py --in-progress US-003

  # Mark US-004 as not started (revert)
  python scripts/update_roadmap.py --not-started US-004

  # Mark complete with custom date
  python scripts/update_roadmap.py --complete US-002 --date 2025-11-09

  # Mark complete and create git commit
  python scripts/update_roadmap.py --complete US-001 --commit
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--complete", metavar="US-XXX", help="Mark user story as completed")
    group.add_argument("--in-progress", metavar="US-XXX", help="Mark user story as in progress")
    group.add_argument("--not-started", metavar="US-XXX", help="Mark user story as not started")

    parser.add_argument("--date", metavar="YYYY-MM-DD", help="Completion date (default: today)")
    parser.add_argument("--commit", action="store_true", help="Create git commit after update")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    args = parser.parse_args()

    # Determine status and story ID
    if args.complete:
        status = "done"
        story_id = args.complete
        date = args.date or datetime.now().strftime("%Y-%m-%d")
    elif args.in_progress:
        status = "in_progress"
        story_id = args.in_progress
        date = None
    else:  # args.not_started
        status = "not_started"
        story_id = args.not_started
        date = None

    # Find and read roadmap
    roadmap_path = find_roadmap_path()
    content = roadmap_path.read_text()

    print(f"📋 Updating {story_id} → {status.replace('_', ' ').upper()}")

    # Update user story status
    updated_content = update_user_story_status(content, story_id, status, date)

    # Update progress summary
    updated_content = update_progress_summary(updated_content)

    # Show diff or write
    if args.dry_run:
        print("\n--- Dry run: Changes would be ---")
        print(updated_content)
    else:
        roadmap_path.write_text(updated_content)
        print("✅ Updated ROADMAP.md")

        # Optional: create git commit
        if args.commit:
            import subprocess

            commit_msg = f"docs: Mark {story_id} as {status.replace('_', ' ')}"
            subprocess.run(["git", "add", str(roadmap_path)], check=True)
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            print(f"✅ Created git commit: {commit_msg}")


if __name__ == "__main__":
    main()
