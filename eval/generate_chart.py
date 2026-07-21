
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Load telemetry
with open('logs/metric_telemetry.json', 'r') as f:
    telemetry = json.load(f)

# Filter valid runs
valid_runs = []
for t in telemetry:
    if t.get('success_rate') and t.get('success_rate') != "0/0":
        p, n = map(int, t['success_rate'].split('/'))
        dt = datetime.fromisoformat(t['timestamp'])
        valid_runs.append({
            'timestamp': dt,
            'tier': t['tier'],
            'rate': (p / n) * 100,
            'passed': p,
            'total': n
        })

# Sort by timestamp
valid_runs.sort(key=lambda x: x['timestamp'])

# Create dark theme plot
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
fig.patch.set_facecolor('#0B0F19')
ax.set_facecolor('#111827')

# Color palette for tiers
colors = {
    'tier_1': '#3B82F6',
    'tier_3': '#60A5FA',
    'tier_4': '#34D399',
    'tier_5': '#F59E0B',
    'tier_6': '#EC4899',
    'tier_overnight': '#8B5CF6'
}

# Group data by tier
tier_data = {}
for r in valid_runs:
    tier = r['tier']
    if tier not in tier_data:
        tier_data[tier] = {'x': [], 'y': []}
    tier_data[tier]['x'].append(r['timestamp'])
    tier_data[tier]['y'].append(r['rate'])

# Plot line and scatter for each tier
for tier, data in tier_data.items():
    label_name = tier.replace('_', ' ').title()
    c = colors.get(tier, '#9CA3AF')
    ax.plot(data['x'], data['y'], label=label_name, color=c, linewidth=2.2, alpha=0.85, marker='o', markersize=5)

# Formatting
ax.set_title('Mighty Mouse v9.1 — Autonomous Optimization Loop Progress', fontsize=16, fontweight='bold', pad=15, color='#F9FAFB')
ax.set_xlabel('Timeline (Cycles & Escalation)', fontsize=12, labelpad=10, color='#9CA3AF')
ax.set_ylabel('Pass Rate (%)', fontsize=12, labelpad=10, color='#9CA3AF')
ax.set_ylim(-5, 105)
ax.yaxis.set_major_formatter('{x:.0f}%')

# Annotations for key Tier 6 milestone breakthroughs
t6_runs = [r for r in valid_runs if r['tier'] == 'tier_6']
if t6_runs:
    # Annotate base Tier 6 score
    ax.annotate('Base Tier 6: 20%', xy=(t6_runs[0]['timestamp'], t6_runs[0]['rate']),
                xytext=(t6_runs[0]['timestamp'], t6_runs[0]['rate'] - 12),
                arrowprops=dict(facecolor='#EC4899', shrink=0.08, width=1, headwidth=6),
                fontsize=9, color='#EC4899', fontweight='bold')
    
    # Find max Tier 6 score
    max_t6 = max(t6_runs, key=lambda x: x['rate'])
    ax.annotate(f'Peak Tier 6: {max_t6["rate"]:.0f}%', xy=(max_t6['timestamp'], max_t6['rate']),
                xytext=(max_t6['timestamp'], max_t6['rate'] + 8),
                arrowprops=dict(facecolor='#10B981', shrink=0.08, width=1, headwidth=6),
                fontsize=9, color='#10B981', fontweight='bold')

ax.grid(True, linestyle='--', alpha=0.15, color='#6B7280')
ax.legend(loc='lower right', framealpha=0.8, facecolor='#1F2937', edgecolor='#374151', fontsize=10)

plt.tight_layout()

# Save to workspace and artifacts dir
output_path = 'eval/results/mighty_mouse_experiment_progress.png'
plt.savefig(output_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
print(f"Chart saved to {output_path}")
