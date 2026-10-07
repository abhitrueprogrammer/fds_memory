import json
from pathlib import Path

conditions = ["A", "B", "C", "D"]
all_data = {}
for c in conditions:
    sum_path = Path(f"results/condition_{c}/summary.json")
    if sum_path.exists():
        all_data[c] = json.loads(sum_path.read_text())

print("Loaded conditions:", list(all_data.keys()))
for c, tasks in all_data.items():
    print(f"\n=== Condition {c} ===")
    total_cost = sum(t["cost"] for t in tasks)
    total_latency = sum(t["latency_seconds"] for t in tasks)
    resolved_count = sum(1 for t in tasks if t["resolved"])
    print(f"Total resolved: {resolved_count}/{len(tasks)} ({resolved_count/len(tasks)*100:.1f}%)")
    print(f"Total cost: ${total_cost:.4f}, Total latency: {total_latency:.1f}s")
    for t in tasks:
        print(f"  Pos {t['position']}: {t['instance_id']} | resolved={t['resolved']} | cost=${t['cost']:.4f} | latency={t['latency_seconds']}s | calls={t['api_calls']} | exit={t['exit_status']}")
