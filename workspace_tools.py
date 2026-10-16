"""Session-only comparison and voluntary usability evidence."""
from datetime import datetime, timezone


def filter_history(history, query='', mode='all'):
    """Search session records locally without modifying order or invoking a model."""
    term = query.strip().casefold()
    return [(index, result) for index, result in enumerate(history)
            if (mode == 'all' or result['mode'] == mode)
            and (not term or term in result['problem'].casefold()
                 or term in str(result.get('final_answer', '')).casefold())]


def paired_history(history):
    """Match exact trimmed questions and model IDs; keep the newest of each mode."""
    groups = {}
    for result in history:
        key = (result['problem'].strip(), result['model'])
        group = groups.setdefault(key, {})
        group.setdefault(result['mode'], result)
    return [(question, model, modes) for (question, model), modes in groups.items()
            if 'single' in modes and 'multi' in modes]


def feedback_record(task, completed, ease, clarity, comment):
    """No names, problem text, credentials, or automatic research accuracy claims."""
    if task not in {'Solve a question', 'Compare both approaches', 'Export a solution'}:
        raise ValueError('Unknown feedback task')
    if not 1 <= ease <= 5 or not 1 <= clarity <= 5:
        raise ValueError('Ratings must be between 1 and 5')
    return {'recorded_at': datetime.now(timezone.utc).isoformat(), 'task': task,
            'completed': bool(completed), 'ease_1_to_5': ease,
            'clarity_1_to_5': clarity, 'comment': comment.strip()[:1000],
            'source': 'voluntary self-report', 'release': 'beta-2026-09-27'}
