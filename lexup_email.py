"""Builds the HTML + plain-text body of one LexUp drop."""
from html import escape

ACID = "#c8ff00"
BLACK = "#0a0a0a"
MUTED = "#6b6b5e"


def make_subject(words):
    names = [w["word"].title() for w in words]
    if len(names) <= 2:
        return "LexUp: " + " & ".join(names)
    return f"LexUp: {names[0]}, {names[1]} + {len(names) - 2} more"


def _word_cards(words):
    out = []
    for w in words:
        out.append(
            f'<tr><td style="padding:0 0 14px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
            f'style="border-left:4px solid {ACID};background:#f7f7f2;"><tr>'
            f'<td style="padding:14px 16px;">'
            f'<div style="font-family:Georgia,serif;font-size:22px;font-weight:bold;color:{BLACK};">'
            f'{escape(w["word"].upper())}'
            f' <span style="font-family:Arial,sans-serif;font-size:12px;font-weight:normal;color:{MUTED};">'
            f'{escape(w.get("part_of_speech", ""))}</span></div>'
            f'<div style="font-family:Arial,sans-serif;font-size:15px;line-height:22px;color:#222;margin-top:6px;">'
            f'{escape(w["definition"])}</div>'
            f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:21px;color:{MUTED};'
            f'font-style:italic;margin-top:6px;">&ldquo;{escape(w.get("example", ""))}&rdquo;</div>'
            f'</td></tr></table></td></tr>'
        )
    return "".join(out)


def _grid_html(cw):
    starts = {}
    for e in cw["entries"]:
        starts[(e["row"], e["col"])] = e["num"]
    rows = []
    for r, row in enumerate(cw["grid"]):
        cells = []
        for c, ch in enumerate(row):
            if ch:
                num = starts.get((r, c), "")
                cells.append(
                    f'<td width="32" height="32" valign="top" style="width:32px;height:32px;'
                    f'border:1px solid {BLACK};background:#ffffff;font-family:Arial,sans-serif;'
                    f'font-size:10px;line-height:10px;color:{BLACK};padding:1px 0 0 2px;">'
                    f'{num if num else "&nbsp;"}</td>'
                )
            else:
                cells.append('<td width="32" height="32" style="width:32px;height:32px;"></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table cellpadding="0" cellspacing="0" role="presentation" '
        'style="border-collapse:collapse;margin:0 auto;">' + "".join(rows) + "</table>"
    )


def _clues_html(cw, clues):
    parts = []
    for label, d in (("Across", "A"), ("Down", "D")):
        items = [e for e in cw["entries"] if e["dir"] == d]
        if not items:
            continue
        lis = "".join(
            f'<div style="margin:0 0 4px 0;"><b>{e["num"]}.</b> {escape(clues[e["word"]])}</div>'
            for e in items
        )
        parts.append(
            f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:20px;color:#222;'
            f'margin-top:14px;"><div style="font-size:12px;letter-spacing:1px;text-transform:uppercase;'
            f'color:{MUTED};margin-bottom:6px;">{label}</div>{lis}</div>'
        )
    return "".join(parts)


def render_email(words, cw, vocab_area=None, reply_to=None):
    """words: [{"word","part_of_speech","definition","example","clue"}]
    cw: result of build_crossword (may have no entries -> section skipped)."""
    clues = {w["word"].upper(): w["clue"] for w in words}
    has_cw = len(cw["entries"]) >= 3

    topic = ""
    if vocab_area and vocab_area.lower() != "not specified":
        topic = f" for <b>{escape(vocab_area)}</b>"

    cw_block = ""
    if has_cw:
        cw_block = (
            f'<tr><td style="padding:10px 0 0 0;">'
            f'<div style="font-family:Arial,sans-serif;font-size:12px;letter-spacing:2px;'
            f'text-transform:uppercase;color:{MUTED};margin-bottom:6px;">Lock it in</div>'
            f'<div style="font-family:Georgia,serif;font-size:20px;font-weight:bold;color:{BLACK};'
            f'margin-bottom:14px;">Today&rsquo;s crossword</div>'
            f'{_grid_html(cw)}{_clues_html(cw, clues)}</td></tr>'
        )

    cancel = (
        "To cancel or change your delivery days, just reply to this email."
        if reply_to
        else "To cancel or change your delivery days, reply to this email."
    )

    html = (
        f'<!doctype html><html><body style="margin:0;padding:0;background:#ecece6;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:#ecece6;">'
        f'<tr><td align="center" style="padding:24px 12px;">'
        f'<table width="600" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="max-width:600px;width:100%;background:#ffffff;">'
        f'<tr><td style="background:{BLACK};padding:18px 24px;font-family:Arial,sans-serif;'
        f'font-size:22px;font-weight:bold;letter-spacing:4px;color:{ACID};">LEXUP</td></tr>'
        f'<tr><td style="padding:24px;"><table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f'<tr><td style="font-family:Arial,sans-serif;font-size:16px;line-height:24px;color:#222;'
        f'padding-bottom:18px;">Here are your {len(words)} words{topic}. '
        f'Read them, then see how many you can use.</td></tr>'
        f'{_word_cards(words)}{cw_block}'
        f'</table></td></tr>'
        f'<tr><td style="padding:16px 24px 24px 24px;font-family:Arial,sans-serif;font-size:12px;'
        f'line-height:18px;color:{MUTED};border-top:1px solid #e5e5dc;">'
        f'You&rsquo;re getting this because you subscribed to LexUp. {cancel}</td></tr>'
        f'</table></td></tr></table></body></html>'
    )

    lines = [f"LEXUP - your {len(words)} words", ""]
    for w in words:
        lines += [
            f'{w["word"].upper()} ({w.get("part_of_speech", "")})',
            f'  {w["definition"]}',
            f'  "{w.get("example", "")}"',
            "",
        ]
    if has_cw:
        lines.append("CROSSWORD CLUES (open the HTML version to see the grid)")
        for label, d in (("Across", "A"), ("Down", "D")):
            for e in (x for x in cw["entries"] if x["dir"] == d):
                lines.append(f'  {e["num"]} {label}: {clues[e["word"]]}')
        lines.append("")
    lines.append(cancel)
    return html, "\n".join(lines)
