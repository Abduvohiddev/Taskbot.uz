"""
Chart generator - premium matplotlib charts (individual, sent as media group)
"""
import io
import logging
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle

from config import settings

logger = logging.getLogger(__name__)

# ── Color palette ──────────────────────────────────────────────────────────────
COLORS = {
    "new":        "#2979FF",
    "in_progress":"#FF6D00",
    "review":     "#AA00FF",
    "done":       "#00C853",
    "overdue":    "#FF1744",
    "cancelled":  "#78909C",
}
STATUS_LABELS = {
    "new": "Yangi", "in_progress": "Jarayonda", "review": "Ko'rilmoqda",
    "done": "Bajarildi", "overdue": "Kechikdi", "cancelled": "Bekor",
}
PRIORITY_LABELS  = {"low": "Past", "medium": "O'rta", "high": "Yuqori", "urgent": "Shoshilinch"}
PRIORITY_COLORS  = {"low": "#4CAF50", "medium": "#FF9800", "high": "#F44336", "urgent": "#9C27B0"}
RANK_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32"] + ["#2979FF"] * 20

BG       = "#F4F6FA"
PANEL    = "#FFFFFF"
T_DARK   = "#1A1A2E"
T_MED    = "#555577"
T_LIGHT  = "#9999BB"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _setup():
    plt.rcParams.update({
        'font.family': 'DejaVu Sans',
        'figure.facecolor': BG,
        'axes.facecolor': PANEL,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.edgecolor': '#DDDDEE',
        'axes.grid': True,
        'grid.color': '#EEEEEE',
        'grid.linewidth': 0.8,
        'xtick.color': T_MED,
        'ytick.color': T_MED,
    })


def _save(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=settings.CHART_DPI,
                bbox_inches='tight', facecolor=BG, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Chart 1: Status donut ──────────────────────────────────────────────────────

def generate_status_donut_chart(stats: dict, title: str = "Vazifalar holati") -> bytes:
    """Premium donut chart with completion % in center"""
    _setup()
    fig, ax = plt.subplots(figsize=(8, 7), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(BG)

    data = {k: stats.get(k, 0) for k in ("done", "in_progress", "review", "new", "overdue")}
    valid = {k: v for k, v in data.items() if v > 0}
    total = sum(valid.values())

    if not total:
        ax.text(0.5, 0.5, "Ma'lumot yo'q", ha='center', va='center',
                fontsize=16, color=T_LIGHT, transform=ax.transAxes)
        ax.axis('off')
        fig.suptitle(title, fontsize=14, fontweight='bold', color=T_DARK, y=0.97)
        return _save(fig)

    labels = [STATUS_LABELS.get(k, k) for k in valid]
    sizes  = list(valid.values())
    colors = [COLORS.get(k, "#9E9E9E") for k in valid]
    explode= [0.06 if k == "overdue" else 0.02 for k in valid]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, colors=colors, autopct='%1.0f%%',
        explode=explode, startangle=90,
        textprops={'fontsize': 11},
        wedgeprops={'edgecolor': 'white', 'linewidth': 3, 'width': 0.42},
        pctdistance=0.80,
    )
    for at in autotexts:
        at.set_fontweight('bold'); at.set_color('white'); at.set_fontsize(10)

    # Center hole
    ax.add_artist(plt.Circle((0, 0), 0.55, fc='white', linewidth=0, zorder=10))

    rate = stats.get('completion_rate', 0)
    ax.text(0,  0.12, f"{rate}%",   ha='center', va='center', fontsize=28,
            fontweight='bold', color=COLORS["done"], zorder=11)
    ax.text(0, -0.13, "bajarilish", ha='center', va='center', fontsize=10,
            color=T_LIGHT, zorder=11)
    ax.text(0, -0.36, f"Jami: {total}", ha='center', va='center', fontsize=11,
            color=T_MED, fontweight='bold', zorder=11)

    # Legend below chart
    patches = [mpatches.Patch(color=COLORS.get(k, '#9E9E9E'),
                               label=f"{STATUS_LABELS.get(k,k)}: {v}")
               for k, v in valid.items()]
    ax.legend(handles=patches, loc='lower center', bbox_to_anchor=(0.5, -0.10),
              ncol=3, fontsize=10, framealpha=0.95, edgecolor='#DDDDEE')

    ax.axis('equal')
    fig.suptitle(title, fontsize=14, fontweight='bold', color=T_DARK, y=0.98)
    plt.tight_layout(pad=1.5)
    return _save(fig)


# ── Chart 2: Weekly bar ────────────────────────────────────────────────────────

def generate_weekly_chart(weekly_data: List[dict], title: str = "So'nggi 7 kun") -> bytes:
    """Premium grouped bar chart: created vs done"""
    _setup()
    fig, ax = plt.subplots(figsize=(10, 6), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    days    = [d["day"] for d in weekly_data]
    created = [d["created"] for d in weekly_data]
    done    = [d["done"] for d in weekly_data]

    x, w = range(len(days)), 0.38

    b1 = ax.bar([i - w/2 for i in x], created, w, label="Yaratildi",
                color=COLORS["new"],  alpha=0.88, edgecolor='white', linewidth=1.5, zorder=3)
    b2 = ax.bar([i + w/2 for i in x], done, w, label="Bajarildi",
                color=COLORS["done"], alpha=0.88, edgecolor='white', linewidth=1.5, zorder=3)

    for bar in list(b1) + list(b2):
        h = bar.get_height()
        if h > 0:
            color = COLORS["new"] if bar in b1 else COLORS["done"]
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.08,
                    str(int(h)), ha='center', va='bottom',
                    fontsize=9, color=color, fontweight='bold')

    ax.set_xticks(list(x))
    ax.set_xticklabels(days, fontsize=11)
    ax.set_ylabel("Vazifalar soni", fontsize=11, color=T_MED)
    ax.legend(fontsize=10, framealpha=0.95, edgecolor='#DDDDEE')
    max_v = max(max(created + [0]), max(done + [0]))
    ax.set_ylim(0, max_v * 1.35 + 1)
    ax.grid(axis='y', alpha=0.4)
    ax.grid(axis='x', visible=False)

    fig.suptitle(title, fontsize=14, fontweight='bold', color=T_DARK, y=0.98)
    plt.tight_layout(pad=2.0)
    return _save(fig)


# ── Chart 3: Priority distribution ────────────────────────────────────────────

def generate_priority_chart(priority_data: dict, title: str = "Muhimlik taqsimoti") -> bytes:
    """Horizontal bar chart by priority"""
    _setup()
    fig, ax = plt.subplots(figsize=(9, 5), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    order = ["urgent", "high", "medium", "low"]
    labels, values, colors = [], [], []
    for k in order:
        v = priority_data.get(k, 0)
        if v > 0:
            labels.append(PRIORITY_LABELS.get(k, k))
            values.append(v)
            colors.append(PRIORITY_COLORS.get(k, "#888"))

    if not values:
        ax.text(0.5, 0.5, "Ma'lumot yo'q", ha='center', va='center',
                fontsize=14, color=T_LIGHT, transform=ax.transAxes)
        ax.axis('off')
        fig.suptitle(title, fontsize=14, fontweight='bold', color=T_DARK, y=0.97)
        return _save(fig)

    y = range(len(labels))
    bars = ax.barh(list(y), values, color=colors, alpha=0.90,
                   edgecolor='white', linewidth=2, height=0.58, zorder=3)

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height()/2,
                str(val), ha='left', va='center',
                fontsize=13, fontweight='bold', color=T_DARK)

    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=12, fontweight='bold')
    ax.set_xlabel("Vazifalar soni", fontsize=11, color=T_MED)
    ax.set_xlim(0, max(values) * 1.30 + 1)
    ax.invert_yaxis()
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.grid(axis='x', alpha=0.35)
    ax.grid(axis='y', visible=False)

    fig.suptitle(title, fontsize=14, fontweight='bold', color=T_DARK, y=0.98)
    plt.tight_layout(pad=2.0)
    return _save(fig)


# ── Chart 4: Dark summary card ─────────────────────────────────────────────────

def generate_summary_card(stats: dict, user_name: str = "",
                          rank_info: Optional[dict] = None) -> bytes:
    """Dark-theme performance card with score, metrics, progress bar"""
    DARK_BG    = "#0F0E17"
    DARK_PANEL = "#1A1A2E"
    ACCENT     = "#FFD700"
    DONE_C     = "#00E676"
    PROG_C     = "#FFAB40"
    OVER_C     = "#FF5252"
    INFO_C     = "#40C4FF"
    DIM        = "#7070A0"

    fig = plt.figure(figsize=(8, 5.2), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(DARK_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(DARK_BG)
    ax.axis('off')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    total      = stats.get('total', 0)
    done       = stats.get('done', 0)
    overdue    = stats.get('overdue', 0)
    in_progress= stats.get('in_progress', 0)
    new        = stats.get('new', 0)
    rate       = stats.get('completion_rate', 0)
    score      = max(0, done * 10 - overdue * 8 + in_progress * 2)

    # Panel background
    panel = Rectangle((0.02, 0.02), 0.96, 0.96,
                       transform=ax.transAxes, color=DARK_PANEL, zorder=1,
                       linewidth=1.5, edgecolor='#2A2A4A')
    ax.add_patch(panel)

    # Header line
    ax.text(0.5, 0.93, "PERFORMANCE CARD",
            ha='center', va='top', fontsize=12, color=DIM, fontweight='bold',
            transform=ax.transAxes, zorder=2)

    # Rank badge (top right)
    if rank_info:
        rank_str = f"#{rank_info['rank']} / {rank_info['total_members']}"
        ax.text(0.95, 0.93, rank_str, ha='right', va='top',
                fontsize=10, color=ACCENT, fontweight='bold',
                transform=ax.transAxes, zorder=2)

    # Name
    if user_name:
        ax.text(0.5, 0.80, user_name, ha='center', va='top',
                fontsize=16, color='#CCD6F6', fontweight='bold',
                transform=ax.transAxes, zorder=2)

    # Big score (★ U+2605 renders in DejaVu Sans)
    ax.text(0.5, 0.60, f"\u2605  {score}", ha='center', va='center',
            fontsize=36, color=ACCENT, fontweight='bold',
            transform=ax.transAxes, zorder=2)
    ax.text(0.5, 0.45, "REYTING BALI", ha='center', va='center',
            fontsize=9, color=DIM, transform=ax.transAxes, zorder=2)

    # Divider
    divider = Rectangle((0.06, 0.405), 0.88, 0.008,
                         transform=ax.transAxes, color='#1F3460', zorder=2)
    ax.add_patch(divider)

    # 4 metric columns
    metrics = [
        (str(done),        "Bajarildi", DONE_C),
        (str(in_progress), "Jarayonda", PROG_C),
        (str(overdue),     "Kechikdi",  OVER_C),
        (f"{rate}%",       "Faollik",   INFO_C),
    ]
    for i, (val, label, color) in enumerate(metrics):
        xc = 0.10 + i * 0.225
        ax.text(xc, 0.31, val, ha='center', va='center',
                fontsize=17, color=color, fontweight='bold',
                transform=ax.transAxes, zorder=2)
        ax.text(xc, 0.18, label, ha='center', va='center',
                fontsize=8, color=DIM, transform=ax.transAxes, zorder=2)

    # Progress bar (bg + fill)
    bx, bw, by, bh = 0.06, 0.88, 0.085, 0.038
    ax.add_patch(Rectangle((bx, by), bw, bh, transform=ax.transAxes,
                            color='#1F3460', zorder=2))
    if total > 0:
        fill = bw * min(done / total, 1.0)
        ax.add_patch(Rectangle((bx, by), fill, bh, transform=ax.transAxes,
                                color=DONE_C, zorder=3))

    ax.text(0.5, 0.03, f"Jami: {total} ta vazifa", ha='center', va='bottom',
            fontsize=9, color=DIM, transform=ax.transAxes, zorder=2)

    fig.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=settings.CHART_DPI,
                bbox_inches='tight', facecolor=DARK_BG, edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Chart: Team leaderboard (horizontal bars) ──────────────────────────────────

def generate_leaderboard_chart(member_stats: List[dict]) -> bytes:
    """Horizontal bar chart ranked by score (no emojis — rank circles + text labels)"""
    _setup()
    members = sorted(member_stats, key=lambda x: x.get("score", 0), reverse=True)[:10]
    n = len(members)
    if n == 0:
        fig, ax = plt.subplots(figsize=(11, 5), dpi=settings.CHART_DPI)
        fig.patch.set_facecolor(BG); ax.set_facecolor(PANEL)
        ax.text(0.5, 0.5, "A'zolar yo'q", ha='center', va='center',
                fontsize=16, color=T_LIGHT, transform=ax.transAxes)
        ax.axis('off')
        fig.suptitle("Jamoa reytingi", fontsize=16, fontweight='bold', color=T_DARK, y=0.96)
        return _save(fig)

    fig, ax = plt.subplots(figsize=(12, max(5, n * 0.85 + 1.5)), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    names  = [m["user_name"][:22] for m in members]
    scores = [max(0, m.get("score", 0)) for m in members]
    bar_colors = RANK_COLORS[:n]

    max_s = max(scores) if any(s > 0 for s in scores) else 1

    # Reference track bars
    ax.barh(range(n), [max_s] * n, color='#F2F4FA',
            edgecolor='none', height=0.70, zorder=1)
    # Score bars
    bars = ax.barh(range(n), scores, color=bar_colors, alpha=0.92,
                   edgecolor='white', linewidth=1.5, height=0.70, zorder=2)

    for i, (bar, m) in enumerate(zip(bars, members)):
        # Rank badge: colored circle with number
        ax.text(-max_s * 0.045, bar.get_y() + bar.get_height()/2,
                str(i + 1), ha='center', va='center',
                fontsize=12, fontweight='bold', color='white', zorder=4,
                bbox=dict(boxstyle='circle,pad=0.45',
                          facecolor=bar_colors[i], edgecolor='white', linewidth=2))
        # Stats line (plain text, no emojis)
        parts = [
            f"{int(m.get('score', 0))} bal",
            f"{m.get('done', 0)} bajarildi",
            f"{m.get('overdue', 0)} kech",
            f"{m.get('completion_rate', 0)}%",
        ]
        ax.text(bar.get_width() + max_s * 0.03, bar.get_y() + bar.get_height()/2,
                "    ".join(parts), ha='left', va='center',
                fontsize=10, color=T_MED, zorder=3)

    ax.set_yticks(range(n))
    ax.set_yticklabels(names, fontsize=11, fontweight='bold', color=T_DARK)
    ax.set_xlabel("Reyting bali", fontsize=11, color=T_MED)
    ax.set_xlim(-max_s * 0.15, max_s * 2.00)
    ax.invert_yaxis()
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.grid(axis='x', alpha=0.3)
    ax.grid(axis='y', visible=False)

    fig.suptitle("Jamoa reytingi", fontsize=16, fontweight='bold',
                 color=T_DARK, y=1.00)
    plt.tight_layout(pad=2.0)
    return _save(fig)


# ── Chart: Team comparison stacked bars ───────────────────────────────────────

def generate_team_comparison_chart(member_stats: List[dict]) -> bytes:
    """Stacked horizontal bars: done / in_progress / new / overdue per member"""
    _setup()
    members = sorted(member_stats, key=lambda x: x.get("total", 0), reverse=True)[:10]
    n = len(members)
    if n == 0:
        fig, ax = plt.subplots(figsize=(11, 5), dpi=settings.CHART_DPI)
        fig.patch.set_facecolor(BG); ax.set_facecolor(PANEL)
        ax.text(0.5, 0.5, "A'zolar yo'q", ha='center', va='center',
                fontsize=16, color=T_LIGHT, transform=ax.transAxes)
        ax.axis('off')
        fig.suptitle("A'zolar taqqoslash", fontsize=14, fontweight='bold', color=T_DARK, y=0.96)
        return _save(fig)

    fig, ax = plt.subplots(figsize=(12, max(5, n * 0.9 + 2.2)), dpi=settings.CHART_DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    names   = [m["user_name"][:22] for m in members]
    done    = [m.get("done", 0)        for m in members]
    in_prog = [m.get("in_progress", 0) for m in members]
    new     = [m.get("new", 0)         for m in members]
    overdue = [m.get("overdue", 0)     for m in members]
    totals  = [d + p + n + o for d, p, n, o in zip(done, in_prog, new, overdue)]

    y = range(n)
    kw = dict(edgecolor='white', linewidth=1.5, height=0.65, zorder=3)

    ax.barh(list(y), done,    label="Bajarildi",  color=COLORS["done"], alpha=0.92, **kw)
    ax.barh(list(y), in_prog, left=done,
            label="Jarayonda", color=COLORS["in_progress"], alpha=0.92, **kw)
    left2 = [a+b for a, b in zip(done, in_prog)]
    ax.barh(list(y), new, left=left2,
            label="Yangi",     color=COLORS["new"], alpha=0.92, **kw)
    left3 = [a+b for a, b in zip(left2, new)]
    ax.barh(list(y), overdue, left=left3,
            label="Kechikdi",  color=COLORS["overdue"], alpha=0.92, **kw)

    # Numbers inside segments (only if segment wide enough)
    max_total = max(totals) if totals else 1
    min_w = max_total * 0.06
    for i in range(n):
        segs = [(done[i], 0, COLORS["done"]),
                (in_prog[i], done[i], COLORS["in_progress"]),
                (new[i], done[i] + in_prog[i], COLORS["new"]),
                (overdue[i], done[i] + in_prog[i] + new[i], COLORS["overdue"])]
        for val, left, _c in segs:
            if val >= min_w:
                ax.text(left + val/2, i, str(val),
                        ha='center', va='center',
                        fontsize=10, color='white', fontweight='bold', zorder=5)
        # Total on right
        ax.text(totals[i] + max_total * 0.02, i, f"jami: {totals[i]}",
                ha='left', va='center',
                fontsize=9, color=T_MED, zorder=4)

    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=11, fontweight='bold', color=T_DARK)
    ax.set_xlabel("Vazifalar soni", fontsize=11, color=T_MED)
    ax.set_xlim(0, max_total * 1.25 + 1)
    ax.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, -0.08),
              ncol=4, framealpha=0.95, edgecolor='#DDDDEE')
    ax.invert_yaxis()
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.grid(axis='x', alpha=0.3)
    ax.grid(axis='y', visible=False)

    fig.suptitle("A'zolar taqqoslash", fontsize=16, fontweight='bold',
                 color=T_DARK, y=1.00)
    plt.tight_layout(pad=2.5)
    return _save(fig)


# ── Legacy wrappers (used by group stats) ─────────────────────────────────────

def generate_personal_stats_chart(stats: Dict, weekly_data: List[Dict]) -> bytes:
    return generate_status_donut_chart(stats, "Shaxsiy ko'rsatkichlar")


def generate_weekly_dynamics_chart(weekly_data: List[Dict]) -> bytes:
    return generate_weekly_chart(weekly_data, "Haftalik dinamika")


def generate_overdue_chart(member_stats: List[Dict], status_counts: Dict) -> bytes:
    if member_stats:
        return generate_leaderboard_chart(member_stats)
    return generate_status_donut_chart(status_counts, "Guruh holati")


def generate_group_report_chart(member_stats, weekly_data, completion_report) -> bytes:
    return generate_team_comparison_chart(member_stats)
