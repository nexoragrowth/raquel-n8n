"""Diff two v6 AUDIT snapshots, node by node."""
import json
import sys
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
audits = sorted((REPO / "workflows" / "current").glob("v6_AUDIT_*.json"))
if len(audits) < 2:
    sys.exit("Need at least 2 v6_AUDIT_*.json snapshots")
OLD, NEW = audits[-2], audits[-1]
print(f"OLD: {OLD.name}")
print(f"NEW: {NEW.name}\n")

old = json.loads(OLD.read_text(encoding="utf-8"))
new = json.loads(NEW.read_text(encoding="utf-8"))

def hash_node(n):
    p = json.dumps(n.get("parameters", {}), sort_keys=True, ensure_ascii=False)
    c = json.dumps(n.get("credentials", {}), sort_keys=True, ensure_ascii=False)
    return hashlib.sha1((p + "||" + c).encode("utf-8")).hexdigest()

old_by_name = {n["name"]: n for n in old.get("nodes", [])}
new_by_name = {n["name"]: n for n in new.get("nodes", [])}

added = sorted(set(new_by_name) - set(old_by_name))
removed = sorted(set(old_by_name) - set(new_by_name))
common = sorted(set(old_by_name) & set(new_by_name))

changed = []
for name in common:
    if hash_node(old_by_name[name]) != hash_node(new_by_name[name]):
        changed.append(name)

print(f"Added: {len(added)}")
for n in added:
    print(f"  + {n}  [{new_by_name[n].get('type')}]")
print(f"\nRemoved: {len(removed)}")
for n in removed:
    print(f"  - {n}  [{old_by_name[n].get('type')}]")
print(f"\nChanged: {len(changed)}")
for n in changed:
    print(f"  ~ {n}  [{new_by_name[n].get('type')}]")

# Connections diff
old_conn = json.dumps(old.get("connections", {}), sort_keys=True)
new_conn = json.dumps(new.get("connections", {}), sort_keys=True)
print(f"\nConnections changed: {old_conn != new_conn}")

# Dump changed nodes' params to a file for review
out = REPO / "tests" / f"audit_diff_{OLD.stem.split('_')[-2]}_{OLD.stem.split('_')[-1]}_vs_{NEW.stem.split('_')[-2]}_{NEW.stem.split('_')[-1]}.md"
lines = [f"# Diff {OLD.name} -> {NEW.name}\n"]
lines.append(f"## Added: {len(added)}")
for n in added:
    lines.append(f"\n### + {n}  [{new_by_name[n].get('type')}]")
    lines.append("```json")
    lines.append(json.dumps(new_by_name[n].get("parameters", {}), ensure_ascii=False, indent=2))
    lines.append("```\n")
lines.append(f"\n## Removed: {len(removed)}")
for n in removed:
    lines.append(f"\n### - {n}  [{old_by_name[n].get('type')}]")
    lines.append("```json")
    lines.append(json.dumps(old_by_name[n].get("parameters", {}), ensure_ascii=False, indent=2))
    lines.append("```\n")
lines.append(f"\n## Changed: {len(changed)}")
for n in changed:
    lines.append(f"\n### ~ {n}  [{new_by_name[n].get('type')}]")
    lines.append("\n**OLD parameters:**")
    lines.append("```json")
    lines.append(json.dumps(old_by_name[n].get("parameters", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("\n**NEW parameters:**")
    lines.append("```json")
    lines.append(json.dumps(new_by_name[n].get("parameters", {}), ensure_ascii=False, indent=2))
    lines.append("```\n")

out.write_text("\n".join(lines), encoding="utf-8")
print(f"\nFull diff -> {out.relative_to(REPO)}")
