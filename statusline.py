#!/usr/bin/env python3
import json
import os
import re
import sys
import subprocess
import time

sys.stdout.reconfigure(encoding='utf-8')

def g(d, *keys, default=''):
    obj = d
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k)
        if obj is None:
            return default
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    return str(obj)

def comma(val):
    if not val:
        return ''
    try:
        return f'{int(float(val)):,}'
    except Exception:
        return val

def fmt_duration(ms):
    if not ms:
        return ''
    try:
        secs = int(ms) // 1000
    except Exception:
        return ''
    days = secs // 86400
    hrs  = (secs % 86400) // 3600
    mins = (secs % 3600) // 60
    if days > 0:
        return f'{days}d {hrs}h {mins}m'
    elif hrs > 0:
        return f'{hrs}h {mins}m'
    return f'{mins}m'

def fmt_reset(secs_left):
    if secs_left <= 0:
        return 'resetting'
    mins_left = secs_left // 60
    hrs  = mins_left // 60
    days = hrs // 24
    hrs_rem  = hrs % 24
    mins_rem = mins_left % 60
    if days > 0:
        return f'{days}d {hrs_rem}h'
    elif hrs > 0:
        return f'{hrs}h {mins_rem}m'
    return f'{mins_left}m'

GRAY    = '\033[38;5;245m'
YELLOW  = '\033[33m'
CYAN    = '\033[38;5;51m'
PURPLE  = '\033[38;5;134m'
DKGREEN = '\033[38;5;28m'
BRED    = '\033[91m'
WHITE   = '\033[97m'
GREEN   = '\033[32m'
ORANGE  = '\033[38;5;208m'
WARN_GREEN  = '\033[38;5;77m'
WARN_LIME   = '\033[38;5;148m'
WARN_YELLOW = '\033[38;5;220m'
WARN_ORANGE = '\033[38;5;208m'
WARN_RED    = '\033[38;5;196m'
EFFORT_LOW    = '\033[38;5;250m'
EFFORT_MEDIUM = '\033[38;5;35m'
EFFORT_HIGH   = '\033[38;5;208m'
EFFORT_XHIGH  = '\033[38;5;202m'
EFFORT_MAX    = '\033[38;5;196m'
SESSION_NAME_COLOR = '\033[38;5;213m'
RESET   = '\033[0m'

LABEL_WIDTH = 6

def label(text):
    return f'{GRAY}{text:<{LABEL_WIDTH}}{RESET}'

ANSI_RE = re.compile(r'\033\[[0-9;]*m')

def visible_len(s):
    return len(ANSI_RE.sub('', s))

def pad(s, width):
    if not s:
        return ' ' * width
    return s + ' ' * max(1, width - visible_len(s))

def collapse_path(path, max_width):
    """Collapse a long path to fit max_width, keeping the trailing
    (most relevant/deepest) segments and prefixing with an ellipsis."""
    if max_width <= 0 or len(path) <= max_width:
        return path
    sep = '\\' if '\\' in path else '/'
    parts = [p for p in path.split(sep) if p != '']
    if not parts:
        return path[-max_width:]
    prefix = '...' + sep
    result = parts[-1]
    for part in reversed(parts[:-1]):
        candidate = part + sep + result
        if len(prefix) + len(candidate) > max_width:
            break
        result = candidate
    collapsed = prefix + result
    if len(collapsed) > max_width:
        keep = max(0, max_width - len(prefix))
        collapsed = prefix + result[-keep:] if keep else result[-max_width:]
    return collapsed

try:
    columns = int(os.environ.get('COLUMNS', '100'))
except Exception:
    columns = 100
COL_WIDTH = max(10, (columns - LABEL_WIDTH) // 3)

def row(label_text, cells):
    out = label(label_text)
    for i, cell in enumerate(cells):
        if i < len(cells) - 1:
            out += pad(cell, COL_WIDTH)
        else:
            out += cell
    return out

def warn_color(pct):
    """Shared 5-step escalating-alert gradient, keyed off a 0-100+ pct-like
    value. Used for both the context-window bar and (via a burn-rate
    projection) the rate-limit lines."""
    if pct >= 81:
        return WARN_RED
    if pct >= 66:
        return WARN_ORANGE
    if pct >= 56:
        return WARN_YELLOW
    if pct >= 40:
        return WARN_LIME
    return WARN_GREEN

def limit_warn_color(projected_pct):
    """Thresholds for a *projected end-of-window* rate-limit value. Unlike
    warn_color (tiered for a live 0-100 usage level, e.g. the context-window
    bar), the only real danger here is exhausting the quota before reset —
    i.e. approaching/exceeding 100% — so caution starts much higher than 56."""
    if projected_pct >= 100:
        return WARN_RED
    if projected_pct >= 90:
        return WARN_ORANGE
    if projected_pct >= 75:
        return WARN_YELLOW
    if projected_pct >= 50:
        return WARN_LIME
    return WARN_GREEN

MIN_ELAPSED_FRAC = 0.02

def limit_color(pct, secs_left, window_secs):
    """Burn-rate-aware color for a rate-limit window: projects current usage
    forward to reset time so a high % with lots of time left reads as more
    urgent than the same % right before it resets anyway.

    elapsed_frac is floored (not cut off) at MIN_ELAPSED_FRAC so a fast burn
    in the opening minutes of a window still projects and escalates color,
    instead of hiding behind raw pct until 5% of the window has passed. The
    floor only exists to keep pct/elapsed_frac from dividing by ~0."""
    if secs_left is None or secs_left <= 0:
        return WARN_GREEN
    elapsed_frac = max(MIN_ELAPSED_FRAC, min(1.0, (window_secs - secs_left) / window_secs))
    projected = pct / elapsed_frac
    return limit_warn_color(projected)

try:
    d = json.load(sys.stdin)
except Exception:
    d = {}

model       = g(d, 'model', 'display_name') or 'Unknown'
used        = g(d, 'context_window', 'used_percentage')
in_tok      = comma(g(d, 'context_window', 'current_usage', 'input_tokens'))
out_tok     = comma(g(d, 'context_window', 'current_usage', 'output_tokens'))
tot_in      = comma(g(d, 'context_window', 'total_input_tokens'))
tot_out     = comma(g(d, 'context_window', 'total_output_tokens'))
exceeds     = g(d, 'context_window', 'exceeds_200k_tokens')
five_pct    = g(d, 'rate_limits', 'five_hour', 'used_percentage')
five_reset  = g(d, 'rate_limits', 'five_hour', 'resets_at')
seven_pct   = g(d, 'rate_limits', 'seven_day', 'used_percentage')
seven_reset = g(d, 'rate_limits', 'seven_day', 'resets_at')
dur_ms      = g(d, 'cost', 'total_duration_ms')
api_ms      = g(d, 'cost', 'total_api_duration_ms')
cost_usd    = g(d, 'cost', 'total_cost_usd')
lines_add   = g(d, 'cost', 'total_lines_added')
lines_rem   = g(d, 'cost', 'total_lines_removed')
cwd         = g(d, 'workspace', 'current_dir') or g(d, 'cwd') or 'unknown'
effort      = g(d, 'effort', 'level')
session_name = g(d, 'session_name')
ctx_size    = g(d, 'context_window', 'context_window_size')
worktree_name = g(d, 'worktree', 'name')

EFFORT_COLORS = {
    'low':    EFFORT_LOW,
    'medium': EFFORT_MEDIUM,
    'high':   EFFORT_HIGH,
    'xhigh':  EFFORT_XHIGH,
    'max':    EFFORT_MAX,
}

# --- Line "info": session name | cwd (+worktree) | git branch ---
branch = ''
dirty = False
try:
    r = subprocess.run(
        ['git', '-C', cwd, '--no-optional-locks', 'status', '--porcelain=v1', '--branch'],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        out_lines = r.stdout.splitlines()
        dirty = len(out_lines) > 1
        if out_lines and out_lines[0].startswith('## '):
            head = out_lines[0][3:]
            if head.startswith('HEAD (no branch)'):
                rev = subprocess.run(
                    ['git', '-C', cwd, 'rev-parse', '--short', 'HEAD'],
                    capture_output=True, text=True
                )
                branch = rev.stdout.strip()
            else:
                branch = head.split('...')[0].split(' ')[0]
except Exception:
    pass

branch_cell = ''
if branch:
    color = YELLOW if dirty else GREEN
    star  = '*' if dirty else ''
    branch_cell = f'{color}{branch}{star}{RESET}'

session_cell = f'{SESSION_NAME_COLOR}[{session_name}]{RESET}' if session_name else f'{GRAY}[unnamed]{RESET}'

# Neither the session nor branch cell needs a rigid 1/3-of-line column:
# session is unpadded down to its own width, and branch is the last cell
# (already unpadded). Whatever room they don't use goes to the path instead
# of leaving a wide gap or collapsing prematurely.
GAP = 2
branch_slack = max(0, COL_WIDTH - visible_len(branch_cell) - 1) if branch_cell else COL_WIDTH
session_width = visible_len(session_cell) + GAP
session_slack = max(0, COL_WIDTH - session_width)
wt_suffix = f' (wt: {worktree_name})' if worktree_name else ''
dir_max_width = max(10, COL_WIDTH + branch_slack + session_slack - len(wt_suffix))

dir_cell = f'{CYAN}{collapse_path(cwd, dir_max_width)}{RESET}'
if worktree_name:
    dir_cell += f' {GRAY}(wt: {worktree_name}){RESET}'

dir_width = visible_len(dir_cell) + GAP
print(label('info') + pad(session_cell, session_width) + pad(dir_cell, dir_width) + branch_cell)

# --- Line "model": model + effort | context bar | tokens ---
model_cell = f'{WHITE}{model}{RESET}'
if effort:
    effort_color = EFFORT_COLORS.get(effort, ORANGE)
    model_cell += f' {effort_color}{effort}{RESET}'

BAR_WIDTH = 20

bar_cell = ''
if used:
    try:
        filled = max(0, min(BAR_WIDTH, round(float(used) * BAR_WIDTH / 100)))
        bar    = '█' * filled + '░' * (BAR_WIDTH - filled)
        pct    = round(float(used))
        bar_color = warn_color(pct)
        bar_cell = f'{bar_color}{bar} {pct}%{RESET}'
        try:
            if ctx_size and int(float(ctx_size)) > 200000:
                bar_cell += f'{GRAY} 1M{RESET}'
        except Exception:
            pass
    except Exception:
        pass

tok_cell = ''
if in_tok and out_tok:
    tok_cell = f'{YELLOW}↑{in_tok} ↓{out_tok}{RESET}'
    if tot_in and tot_out:
        tok_cell += f'  {GRAY}(↑{tot_in} ↓{tot_out}){RESET}'
if exceeds == 'true':
    tok_cell += f'  {BRED}⚠ >200k{RESET}'

print(row('model', [model_cell, bar_cell, tok_cell]))

# --- Line "limit": 5h | 7d ---
FIVE_HOUR_SECS = 5 * 3600
SEVEN_DAY_SECS = 7 * 24 * 3600

if five_pct:
    try:
        now  = int(time.time())
        pct5 = round(float(five_pct))
        secs_left5 = int(five_reset) - now if five_reset else None
        five_color = limit_color(pct5, secs_left5, FIVE_HOUR_SECS)
        if five_reset:
            five_cell = f'{five_color}5h {pct5}% (resets in {fmt_reset(secs_left5)}){RESET}'
        else:
            five_cell = f'{five_color}5h {pct5}%{RESET}'

        seven_cell = ''
        if seven_pct:
            pct7 = round(float(seven_pct))
            secs_left7 = int(seven_reset) - now if seven_reset else None
            seven_color = limit_color(pct7, secs_left7, SEVEN_DAY_SECS)
            if seven_reset:
                seven_cell = f'{seven_color}7d {pct7}% (resets in {fmt_reset(secs_left7)}){RESET}'
            else:
                seven_cell = f'{seven_color}7d {pct7}%{RESET}'

        print(row('limit', [five_cell, seven_cell]))
    except Exception:
        pass

# --- Line "sess": elapsed time | cost | lines changed ---
if dur_ms:
    try:
        wall = fmt_duration(int(dur_ms))
        api  = fmt_duration(int(api_ms)) if api_ms else ''
        elapsed_cell = f'{PURPLE}{wall} (wall) {api} (api){RESET}' if api else f'{PURPLE}{wall} (wall){RESET}'

        cost_cell = f'{DKGREEN}${float(cost_usd):.4f}{RESET}' if cost_usd else ''

        lines_cell = ''
        if lines_add or lines_rem:
            added   = lines_add or '0'
            removed = lines_rem or '0'
            lines_cell = f'{GREEN}+{added}{RESET} {BRED}-{removed}{RESET}'

        print(row('sess', [elapsed_cell, cost_cell, lines_cell]))
    except Exception:
        pass
