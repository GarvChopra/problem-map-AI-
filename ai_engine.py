"""
AreaPulse Civic AI — the intelligence layer.

This module contains:
  • Spam / moderation classifier (rule-based + heuristic confidence)
  • Severity & category auto-suggestion (copilot mode)
  • Trend / cluster detection over historical issue data
  • Insight generation (e.g. "garbage complaints up 40% in last 24h")
  • Map intelligence (heat zones, hot spots)
  • A natural-language "ask AI" handler that decides which structured
    response to return — table, map_markers, insight_card, copilot, etc.

If you want to plug in a real LLM (OpenAI / Anthropic / Gemini), see
the `llm_chat()` function at the bottom — it falls back to a deterministic
local responder if no API key is configured.
"""
import re, time, math, os
from collections import Counter, defaultdict

# ── 1. SPAM / MODERATION ─────────────────────────────────
GIBBERISH_PATTERN = re.compile(r'^[a-z]{1,3}([a-z])\1{3,}', re.I)   # aaaa, sssss
ALL_CAPS_PATTERN  = re.compile(r'^[A-Z\s!?.]{15,}$')
URL_PATTERN       = re.compile(r'https?://|www\.|\.com|\.in', re.I)
REPEATED_CHAR_PATTERN = re.compile(r'(.)\1{4,}')

PROFANITY_LITE = {'fuck','shit','bitch','asshole','bastard','dick'}
SPAM_KEYWORDS  = {'click here','buy now','free money','viagra','casino',
                  'lottery','winner','crypto','bitcoin','investment opportunity'}
PRANK_KEYWORDS = {'test','testing','asdf','asdfgh','qwerty','abcd','xyz',
                  'lorem ipsum','sample','dummy','123','hello world'}

def detect_spam(description, user=None, recent_count=0):
    """
    Analyses a report's text and recent submission velocity.

    Args:
        description: the report text
        user: name of submitter (for repeat-offender weighting)
        recent_count: number of reports this user has filed in last 5 min

    Returns:
        dict with:
            isSpam     bool
            confidence 0–100
            reason     human-readable
            action     'allow' | 'review' | 'auto_block'
            flags      list of triggered rules
    """
    if not description:
        return _spam_result(True, 95, "Empty description", ['empty'])

    text = description.strip().lower()
    flags = []
    score = 0

    # Length check
    if len(text) < 10:
        score += 35; flags.append('too_short')
    elif len(text) < 20:
        score += 10; flags.append('short')

    # Word count
    words = text.split()
    if len(words) < 3:
        score += 25; flags.append('few_words')

    # Gibberish detection
    if GIBBERISH_PATTERN.search(text) or REPEATED_CHAR_PATTERN.search(text):
        score += 40; flags.append('gibberish')

    # Random-looking letter blob (no spaces, all consonants)
    if len(words) == 1 and len(text) > 6 and not any(c in 'aeiou' for c in text):
        score += 30; flags.append('keyboard_mashing')

    # Prank / test keywords
    if any(p in text for p in PRANK_KEYWORDS):
        score += 35; flags.append('prank_keyword')

    # Spam keywords
    if any(s in text for s in SPAM_KEYWORDS):
        score += 60; flags.append('spam_keyword')

    # URLs / promotional
    if URL_PATTERN.search(description):
        score += 25; flags.append('url_present')

    # All-caps shouting
    if ALL_CAPS_PATTERN.match(description):
        score += 15; flags.append('all_caps')

    # Profanity (mild penalty — could be venting, not spam)
    if any(p in text for p in PROFANITY_LITE):
        score += 8; flags.append('profanity')

    # Repeat-offender weighting
    if recent_count >= 5:
        score += 30; flags.append('rapid_fire')
    elif recent_count >= 3:
        score += 15; flags.append('frequent_submitter')

    # No civic vocabulary at all? Likely off-topic
    civic_words = {'road','water','garbage','light','street','park','drain',
                   'trash','noise','traffic','signal','tree','sewage','pipe',
                   'pothole','electric','power','dustbin','overflow','leak',
                   'broken','damage','complaint','issue','problem','area',
                   'block','sector','colony','market','smell','dump','wire'}
    if not any(w in text for w in civic_words) and len(words) < 8:
        score += 20; flags.append('no_civic_context')

    score = min(100, score)

    # Decide
    if score < 40:
        action = 'allow';      is_spam = False
    elif score < 75:
        action = 'review';     is_spam = False   # not auto-blocked, just queued
    else:
        action = 'auto_block'; is_spam = True

    reason = _build_reason(flags) or "Looks legitimate"
    return _spam_result(is_spam, score, reason, flags, action)


def _build_reason(flags):
    msgs = {
        'empty': 'No description provided',
        'too_short': 'Description too short (under 10 chars)',
        'short': 'Description is brief',
        'few_words': 'Less than 3 words',
        'gibberish': 'Text appears to be gibberish',
        'keyboard_mashing': 'Looks like random keyboard input',
        'prank_keyword': 'Contains test / prank keywords',
        'spam_keyword': 'Contains promotional / spam phrases',
        'url_present': 'Contains URLs (often promotional)',
        'all_caps': 'Entirely uppercase — possible shouting',
        'profanity': 'Contains profanity',
        'rapid_fire': 'User submitting reports very rapidly',
        'frequent_submitter': 'User has submitted multiple reports recently',
        'no_civic_context': 'No civic-issue vocabulary detected',
    }
    return ' | '.join(msgs[f] for f in flags if f in msgs)


def _spam_result(is_spam, confidence, reason, flags, action=None):
    if action is None:
        action = 'auto_block' if is_spam else ('review' if confidence >= 40 else 'allow')
    return {
        'type':       'moderation',
        'isSpam':     is_spam,
        'confidence': confidence,
        'reason':     reason,
        'action':     action,
        'flags':      flags,
    }


# ── 2. COPILOT — auto-suggest category, severity, improved description ─
SEVERITY_KEYWORDS = {
    'high':   ['accident','dangerous','injured','hurt','urgent','emergency',
               'overflow','flooding','sparking','fire','burst','collapse',
               'blocking','child','school','hospital','death','fatal'],
    'medium': ['daily','frequent','large','big','many','complaint','weeks',
               'months','blocked','damaged','broken'],
    'low':    ['small','minor','sometimes','occasional','slight'],
}

def suggest_severity(description):
    text = description.lower()
    for level in ('high','medium','low'):
        if any(kw in text for kw in SEVERITY_KEYWORDS[level]):
            return level
    return 'medium'


def copilot_analyze(description, area=None):
    """Runs auto-tagging, severity, and offers a polished description."""
    from classifier import auto_tag

    tag = auto_tag(description) if description else 'other'
    severity = suggest_severity(description) if description else 'medium'

    # Build a short improved version (capitalize, trim, remove repeated chars)
    improved = description.strip()
    improved = REPEATED_CHAR_PATTERN.sub(r'\1\1', improved)  # collapse aaaaa → aa
    if improved and improved[0].islower():
        improved = improved[0].upper() + improved[1:]
    if improved and not improved.endswith(('.', '!', '?')):
        improved += '.'

    # Suggestion message
    tag_label = tag.replace('_', ' ').title()
    msg = f"This looks like a '{tag_label}' issue with **{severity}** urgency."
    if area:
        msg += f" Reporting in {area}."

    return {
        'type':         'copilot',
        'message':      msg,
        'suggested_tag':      tag,
        'suggested_severity': severity,
        'improved_description': improved,
    }


# ── 3. TRENDS / CLUSTERS over issue data ─────────────────────
def analyze_trends(issues, hours=24):
    """Return % change in reports vs. previous equal window."""
    now = time.time()
    cutoff_recent = now - hours * 3600
    cutoff_prev   = now - hours * 3600 * 2

    recent = [i for i in issues if i.get('timestamp', 0) >= cutoff_recent]
    prev   = [i for i in issues if cutoff_prev <= i.get('timestamp', 0) < cutoff_recent]

    by_tag_recent = Counter(i.get('tag','other') for i in recent)
    by_tag_prev   = Counter(i.get('tag','other') for i in prev)

    trends = []
    for tag, recent_n in by_tag_recent.most_common():
        prev_n = by_tag_prev.get(tag, 0)
        if prev_n == 0:
            change_pct = 100 if recent_n > 0 else 0
        else:
            change_pct = round(((recent_n - prev_n) / prev_n) * 100)
        trends.append({
            'tag': tag, 'recent': recent_n, 'previous': prev_n,
            'change_pct': change_pct,
        })

    return {
        'type':      'trends',
        'window_hours': hours,
        'total_recent': len(recent),
        'total_prev':   len(prev),
        'by_tag':       trends,
    }


def hottest_areas(issues, top_n=5):
    """Return top N areas with the most open + high-severity issues."""
    score = defaultdict(float)
    counts = defaultdict(int)
    for i in issues:
        if i.get('status') == 'resolved':
            continue
        area = i.get('area') or 'Unknown'
        sev = i.get('severity', 'medium')
        weight = {'high': 3, 'medium': 2, 'low': 1}.get(sev, 1)
        score[area] += weight + 0.1 * (i.get('upvotes') or 0)
        counts[area] += 1

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {'area': a, 'priority_score': round(s, 1), 'issue_count': counts[a]}
        for a, s in ranked
    ]


def generate_insights(issues):
    """Always-useful insight cards. Tuned to fire on small datasets too."""
    insights = []
    if not issues:
        return [{
            'type':'insight_card','priority':'medium','icon':'ℹ️',
            'message':"No reports in the system yet. Submit one to get started!"
        }]

    total = len(issues)
    open_n = sum(1 for i in issues if i.get('status') != 'resolved')
    resolved = sum(1 for i in issues if i.get('status') == 'resolved')
    high_sev = sum(1 for i in issues if i.get('severity') == 'high' and i.get('status') != 'resolved')

    # 1. High-severity alert
    if high_sev > 0:
        insights.append({
            'type':'insight_card','priority':'high','icon':'🚨',
            'message': f"**{high_sev}** high-severity issue{'s' if high_sev != 1 else ''} "
                       f"need urgent attention across Delhi"
        })

    # 2. Top category
    by_tag = Counter(i.get('tag','other') for i in issues if i.get('status') != 'resolved')
    if by_tag:
        top_tag, top_n = by_tag.most_common(1)[0]
        insights.append({
            'type':'insight_card','priority':'medium','icon':'🏷️',
            'message': f"**{top_tag.title()}** is the most-reported category right now "
                       f"({top_n} open report{'s' if top_n != 1 else ''})"
        })

    # 3. Hottest area (lowered threshold)
    hot = hottest_areas(issues, top_n=2)
    for h in hot:
        if h['priority_score'] >= 3:    # was 8 — too strict for small datasets
            insights.append({
                'type':'insight_card','priority':'high','icon':'⚠️',
                'message': f"**{h['area']}** is the hottest zone — {h['issue_count']} "
                           f"unresolved issues (priority score {h['priority_score']})"
            })
            break  # only show #1

    # 4. Recent trend (24h)
    trend = analyze_trends(issues, hours=24)
    for t in trend['by_tag'][:2]:
        if t['change_pct'] >= 30 and t['recent'] >= 2:
            insights.append({
                'type':'insight_card','priority':'high','icon':'📈',
                'message': f"**{t['tag'].title()}** complaints up {t['change_pct']}% "
                           f"in last 24h ({t['recent']} new)"
            })
        elif t['change_pct'] <= -30 and t['previous'] >= 2:
            insights.append({
                'type':'insight_card','priority':'low','icon':'📉',
                'message': f"**{t['tag'].title()}** complaints dropped "
                           f"{abs(t['change_pct'])}% — improvement signal"
            })

    # 5. Most upvoted single issue
    most_upvoted = max(issues, key=lambda i: i.get('upvotes', 0), default=None)
    if most_upvoted and most_upvoted.get('upvotes', 0) >= 3:
        insights.append({
            'type':'insight_card','priority':'medium','icon':'🔥',
            'message': f"Most-upvoted issue: **{most_upvoted.get('area')}** — "
                       f"\"{(most_upvoted.get('description') or '')[:55]}…\" "
                       f"({most_upvoted.get('upvotes')} upvotes)"
        })

    # 6. Resolution rate
    if total >= 5:
        rate = round(resolved / total * 100)
        emoji = '✅' if rate >= 30 else '🟡' if rate >= 10 else '🔴'
        insights.append({
            'type':'insight_card',
            'priority':'low' if rate >= 30 else 'medium',
            'icon': emoji,
            'message': f"Citywide resolution rate: **{rate}%** ({resolved} of {total} issues fixed)"
        })

    return insights[:6]


# ── 4. MAP INTELLIGENCE ──────────────────────────────────
def build_map_markers(issues, tag_filter=None, severity_filter=None):
    markers = []
    for i in issues:
        if tag_filter and i.get('tag') != tag_filter:
            continue
        if severity_filter and i.get('severity') != severity_filter:
            continue
        if not i.get('lat') or not i.get('lng'):
            continue
        markers.append({
            'lat':      i['lat'],
            'lng':      i['lng'],
            'label':    i.get('description', '')[:60],
            'severity': i.get('severity', 'medium'),
            'tag':      i.get('tag', 'other'),
            'area':     i.get('area', ''),
            'id':       i.get('id'),
        })
    return {'type': 'map_markers', 'data': markers, 'count': len(markers)}


# ── 5. NL ROUTER — "Ask AreaPulse AI" ─────────────────────
# Pollution-related queries map to these civic categories
POLLUTION_TAGS = ['garbage', 'sewage', 'noise']

def ask_ai(query, issues, current_user=None):
    """
    Parses a natural-language question and returns a structured response.
    Returns dict with at least:
        { 'type': 'text'|'table'|'map_markers'|'insight_card'|'copilot',
          'message': '...',
          ...payload... }
    """
    q = (query or '').lower().strip()
    if not q:
        return {'type': 'text', 'message': "Ask me anything about Delhi's civic issues."}

    # ── Identity / greeting questions answered locally (no LLM call) ──
    identity_q = ['who are you', 'who r u', 'who ru', 'whats your name',
                  "what's your name", 'who is this', 'introduce', 'about you',
                  'what can you do', 'what do you do']
    if any(p in q for p in identity_q):
        return {
            'type': 'text',
            'message': ("I'm **AreaPulse Civic AI** — the assistant for Delhi's "
                        "Problem Map platform. I can help you:\n\n"
                        "• See where civic issues are happening (*show me potholes*)\n"
                        "• Compare trends (*compare last 7 days*)\n"
                        "• Check specific areas (*how is Rohini doing*)\n"
                        "• Answer questions about Delhi's civic problems\n"
                        "• Detect spam in reports automatically\n\n"
                        "Just ask in plain English!"),
        }

    greetings = ['hi', 'hello', 'hey', 'hola', 'namaste', 'good morning',
                 'good afternoon', 'good evening']
    if q in greetings or q in [g + '!' for g in greetings] or q in [g + '.' for g in greetings]:
        return {
            'type': 'text',
            'message': ("Hi! I'm **AreaPulse Civic AI**. Ask me about civic issues "
                        "in Delhi — try *show me potholes*, *which area needs most attention*, "
                        "or *why is Delhi polluted*."),
        }

    # ── EXPLANATORY / OPINION questions go straight to GPT ──
    # "why is X", "how does X", "what should we do", "explain X", "advice on X"
    # Use word boundaries so "why" alone matches but not "byway" etc.
    explain_word_triggers = ['why', 'explain', 'suggest', 'advice',
                             'recommend', 'opinion', 'because']
    explain_phrase_triggers = ['how come', 'how can', 'how do', 'how should',
                               'how would', 'what should', 'what can',
                               'what do you think', 'tell me about',
                               'reason for', 'cause of']
    q_words = set(re.findall(r'\b\w+\b', q))
    if (any(w in q_words for w in explain_word_triggers) or
            any(p in q for p in explain_phrase_triggers)):
        return llm_chat(query, issues, current_user)

    # ── Pollution / dirty / polluted (maps to garbage + sewage + noise) ──
    if any(k in q for k in ['pollut','dirty','dirtiest','contaminat','smog','aqi','air quality']):
        return _polluted_areas(issues, q)

    # ── Best / cleanest / safest area ──
    if any(k in q for k in ['cleanest','safest','best area','least problems','fewest']):
        return _cleanest_areas(issues)

    # ── Specific area lookup BEFORE map intent so "pinpoint rohini" filters correctly ──
    area_match = _match_area(q, issues)

    # If user mentions an area + a map verb → plot only that area
    map_verbs = ['where','location','map','show me','plot','heatmap','marker',
                 'near me','nearby','pinpoint','all issues','everything',
                 'show all','show issues','overview map','plot all']
    if area_match and any(k in q for k in map_verbs):
        area_issues = [i for i in issues if i.get('area') == area_match]
        marker_resp = build_map_markers(area_issues)
        marker_resp['message'] = (f"Plotting **{marker_resp['count']}** issues in "
                                   f"**{area_match}**. Click any row to zoom.")
        return marker_resp

    # Plain area question (no map verb): "how is rohini" → text/table summary
    if area_match and not any(k in q for k in map_verbs):
        return _area_summary(area_match, issues)

    # — Map / location queries (no specific area) —
    if any(k in q for k in map_verbs):
        tag = _extract_tag(q)
        sev = 'high' if 'high' in q or 'urgent' in q else None
        marker_resp = build_map_markers(issues, tag_filter=tag, severity_filter=sev)
        if marker_resp['count'] == 0:
            marker_resp['message'] = "No matching issues found to plot."
        else:
            kind = f"{tag} " if tag else ""
            sev_txt = f" with {sev} severity" if sev else ""
            marker_resp['message'] = (f"Plotting **{marker_resp['count']}** {kind}"
                                       f"issues{sev_txt} across Delhi. "
                                       f"Click any row below to zoom on the map.")
        return marker_resp

    # — Compare / table queries —
    if any(k in q for k in ['compare','table','breakdown','category','categories','last 7']):
        return _table_compare(issues, hours=24*7)

    # — Trend queries —
    if any(k in q for k in ['trend','increase','decrease','rising','falling','change','24 hour','last day']):
        t = analyze_trends(issues, hours=24)
        rows = [[r['tag'].title(), r['recent'], r['previous'],
                 f"{r['change_pct']:+}%"] for r in t['by_tag']]
        return {
            'type': 'table',
            'message': f"Trend analysis — last 24h vs. previous 24h ({t['total_recent']} new reports)",
            'columns': ['Category', 'Last 24h', 'Previous 24h', 'Change'],
            'rows': rows,
        }

    # — Hot zones / worst / most problems —
    if any(k in q for k in ['hottest','priority','most problems','worst','attention',
                            'top areas','dirtiest','problematic','bad']):
        hot = hottest_areas(issues, top_n=8)
        rows = [[h['area'], h['issue_count'], h['priority_score']] for h in hot]
        return {
            'type': 'table',
            'message': "Areas ranked by priority (open issues × severity × upvotes)",
            'columns': ['Area', 'Open Issues', 'Priority Score'],
            'rows': rows,
        }

    # — Insight summary —
    if any(k in q for k in ['summary','insight','overview','dashboard','status',
                            'report','what is happening','whats happening']):
        cards = generate_insights(issues)
        return {
            'type': 'insights',
            'message': f"Here are {len(cards)} key insights right now",
            'cards': cards,
        }

    # — Stats —
    if 'how many' in q or 'count' in q or 'total' in q or 'number of' in q:
        tag = _extract_tag(q)
        filtered = [i for i in issues if (not tag or i.get('tag') == tag)]
        open_n = sum(1 for i in filtered if i.get('status') != 'resolved')
        return {
            'type': 'text',
            'message': (f"There are **{len(filtered)}** total {tag or 'civic'} reports — "
                        f"**{open_n}** still open."),
        }

    # — Tag-only query like "garbage" or "potholes" —
    tag = _extract_tag(q)
    if tag:
        marker_resp = build_map_markers(issues, tag_filter=tag)
        marker_resp['message'] = (f"Found **{marker_resp['count']}** {tag} reports across Delhi. "
                                  f"Showing them on the map.")
        return marker_resp

    # — Help / fallback —
    return llm_chat(query, issues, current_user)


# ── Helpers for richer NL handling ───────────────────────
def _polluted_areas(issues, q):
    """Rank areas by pollution-related issues (garbage + sewage + noise)."""
    is_air   = any(k in q for k in ['air','smog','aqi','breath'])
    is_noise = 'noise' in q
    is_water = any(k in q for k in ['water','sewage','dirty water'])

    if is_air:
        relevant_tags = ['garbage', 'noise']
        kind = 'air-pollution'
    elif is_noise:
        relevant_tags = ['noise']
        kind = 'noise-pollution'
    elif is_water:
        relevant_tags = ['sewage', 'water']
        kind = 'water-pollution'
    else:
        relevant_tags = POLLUTION_TAGS
        kind = 'pollution-related'

    score = defaultdict(int)
    counts = defaultdict(lambda: defaultdict(int))
    for i in issues:
        if i.get('tag') not in relevant_tags:
            continue
        if i.get('status') == 'resolved':
            continue
        area = i.get('area') or 'Unknown'
        sev_w = {'high': 3, 'medium': 2, 'low': 1}.get(i.get('severity','medium'), 1)
        score[area] += sev_w
        counts[area][i.get('tag')] += 1

    if not score:
        return {
            'type': 'text',
            'message': (f"I don't see any open **{kind}** reports right now. "
                        f"Note: Delhi has air-quality monitoring stations but this app "
                        f"tracks user-reported civic issues, not real-time AQI data. "
                        f"For AQI, check CPCB or SAFAR-India.")
        }

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:8]
    rows = []
    for area, sc in ranked:
        cats = counts[area]
        breakdown = ', '.join(f"{n} {t}" for t, n in cats.items())
        rows.append([area, sum(cats.values()), breakdown])

    top_area = ranked[0][0]
    return {
        'type': 'table',
        'message': (f"**{top_area}** is the most {kind} area in Delhi "
                    f"based on user reports. Note: this is from civic complaints "
                    f"(garbage, sewage, noise), not live AQI sensors."),
        'columns': ['Area', 'Reports', 'Categories'],
        'rows': rows,
    }


def _cleanest_areas(issues):
    """Areas with fewest open issues."""
    open_counts = defaultdict(int)
    all_areas = set()
    for i in issues:
        area = i.get('area')
        if not area: continue
        all_areas.add(area)
        if i.get('status') != 'resolved':
            open_counts[area] += 1
    if not all_areas:
        return {'type': 'text', 'message': "Not enough data yet."}
    ranked = sorted(all_areas, key=lambda a: open_counts[a])[:8]
    rows = [[a, open_counts[a]] for a in ranked]
    return {
        'type': 'table',
        'message': f"Areas with fewest open civic issues — **{ranked[0]}** is currently the cleanest.",
        'columns': ['Area', 'Open Issues'],
        'rows': rows,
    }


def _match_area(q, issues):
    """If the query mentions a known area name, return it. Tolerates
    missing spaces ('modeltown' → 'Model Town') and case differences."""
    q_squish = re.sub(r'\s+', '', q.lower())   # 'pinpoint modeltown' → 'pinpointmodeltown'
    areas = {(i.get('area') or '') for i in issues if i.get('area')}
    # Sort longer names first so "Greater Kailash" beats "Kailash" if both existed
    for real in sorted(areas, key=len, reverse=True):
        if not real:
            continue
        spaced = real.lower()
        squished = re.sub(r'\s+', '', spaced)
        if spaced in q.lower() or squished in q_squish:
            return real
    return None


def _area_summary(area, issues):
    area_issues = [i for i in issues if i.get('area') == area]
    open_n = sum(1 for i in area_issues if i.get('status') != 'resolved')
    by_tag = Counter(i.get('tag','other') for i in area_issues if i.get('status') != 'resolved')
    if not area_issues:
        return {'type': 'text', 'message': f"No reports found for **{area}**."}
    rows = [[t.title(), n] for t, n in by_tag.most_common()]
    return {
        'type': 'table',
        'message': (f"**{area}** has **{len(area_issues)}** total reports "
                    f"(**{open_n}** open). Breakdown by category:"),
        'columns': ['Category', 'Open Issues'],
        'rows': rows,
    }


def _extract_tag(q):
    from classifier import KEYWORDS
    for tag, kws in KEYWORDS.items():
        if tag in q:
            return tag
        for kw in kws:
            if kw in q:
                return tag
    return None


def _table_compare(issues, hours=24*7):
    cutoff = time.time() - hours*3600
    recent = [i for i in issues if i.get('timestamp', 0) >= cutoff]
    by_tag = Counter(i.get('tag','other') for i in recent)
    by_status = Counter(i.get('status','open') for i in recent)
    rows = [[tag.title(), n] for tag, n in by_tag.most_common()]
    return {
        'type': 'table',
        'message': (f"Last {hours//24} days — {len(recent)} reports across "
                    f"{len(by_tag)} categories. "
                    f"Open: {by_status.get('open',0)}, "
                    f"Verified: {by_status.get('verified',0)}, "
                    f"Resolved: {by_status.get('resolved',0)}."),
        'columns': ['Category', 'Reports'],
        'rows': rows,
    }


# ── 6. HUGGING FACE ROUTER INTEGRATION + SMART FALLBACK ───
# Uses HF's OpenAI-compatible router (Featherless AI for zephyr-7b-beta).
# Free tier: generous, no card needed. Get a token at:
#   https://huggingface.co/settings/tokens
#
# Cache + rate-limit guard keep us responsive even if HF rate-limits.

_LLM_CACHE = {}              # query_hash → (timestamp, response_dict)
_LLM_CALL_TIMES = []         # rolling window of recent call timestamps
_LLM_CACHE_TTL = 600         # 10 min — same question, same answer
_LLM_RATE_WINDOW = 60        # 1 minute window
_LLM_RATE_LIMIT = 30         # safe ceiling for HF free tier


def llm_chat(query, issues, current_user=None):
    """Calls Hugging Face Router (Zephyr-7B via Featherless AI). Falls back to
    deterministic answer if no token, rate-limited, or API fails."""
    import hashlib

    # Accept any of these env-var names so users don't get tripped up
    api_key = (os.environ.get('HF_TOKEN')
               or os.environ.get('HUGGINGFACE_API_KEY')
               or os.environ.get('HUGGINGFACE_TOKEN'))
    print(f"[llm_chat] called | query='{query[:50]}' | "
          f"key_present={bool(api_key)} | "
          f"key_prefix={api_key[:6] if api_key else 'NONE'}")

    # ── Cache check (same question within 10 min → reuse) ──
    cache_key = hashlib.md5(f"{query}|{len(issues)}".encode()).hexdigest()
    now = time.time()
    if cache_key in _LLM_CACHE:
        cached_at, cached_resp = _LLM_CACHE[cache_key]
        if now - cached_at < _LLM_CACHE_TTL:
            print("[llm_chat] cache HIT (saved API call)")
            return cached_resp

    # ── Rate-limit guard ──
    cutoff = now - _LLM_RATE_WINDOW
    _LLM_CALL_TIMES[:] = [t for t in _LLM_CALL_TIMES if t > cutoff]
    if len(_LLM_CALL_TIMES) >= _LLM_RATE_LIMIT:
        print(f"[llm_chat] rate-limit guard hit ({len(_LLM_CALL_TIMES)} calls/min) → fallback")
        api_key = None  # force fallback for this request

    if api_key:
        try:
            from openai import OpenAI
            print("[llm_chat] openai library imported OK")
            client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=api_key,
            )

            # Compact context: top stats + 10 most recent issues
            total = len(issues)
            open_n = sum(1 for i in issues if i.get('status') != 'resolved')
            resolved = sum(1 for i in issues if i.get('status') == 'resolved')
            by_tag = Counter(i.get('tag','other') for i in issues)
            top_tags = ', '.join(f"{t} ({n})" for t, n in by_tag.most_common(5))
            hot = hottest_areas(issues, top_n=3)
            hot_txt = ', '.join(f"{h['area']} ({h['issue_count']} open)" for h in hot)

            recent = sorted(issues, key=lambda i: i.get('timestamp', 0), reverse=True)[:10]
            recent_txt = '\n'.join(
                f"- [{i.get('status','open')}] {i.get('area','?')} / "
                f"{i.get('tag','?')} / {i.get('severity','?')}: "
                f"{(i.get('description') or '')[:90]}"
                for i in recent
            )

            system_prompt = f"""You are AreaPulse Civic AI, an assistant for Delhi's Problem Map platform.

CURRENT REAL-TIME DATA:
- Total reports: {total} ({open_n} open, {resolved} resolved)
- Top categories: {top_tags}
- Hottest areas: {hot_txt}
- 10 most recent issues:
{recent_txt}

STRICT RULES:
- Answer ONLY using the data above. Do NOT invent statistics, studies, or numbers.
- If you don't have data to answer, say "The data I have doesn't cover that" — do NOT speculate.
- Be concise: under 100 words.
- Use **bold** for emphasis (markdown). No headers, no italics, no emojis.
- Do NOT include any meta-tokens like [INST], [/INST], <|...|>, or "user:" / "assistant:" labels in your output.
- Do NOT continue the conversation by writing fake follow-up questions. Only answer what was asked.

The user is: {current_user or 'a citizen of Delhi'}."""

            _LLM_CALL_TIMES.append(now)
            completion = client.chat.completions.create(
                model="meta-llama/Llama-3.1-8B-Instruct:featherless-ai",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": query},
                ],
                max_tokens=300,
                temperature=0.4,   # lower → less invention
                stop=["[USER]", "[ASSISTANT]", "[INST]", "\nUser:", "\nuser:", "<|user|>"],
            )
            answer = (completion.choices[0].message.content or '').strip()

            # ── Defensive cleanup: some models leak chat-template tokens ──
            # Strip everything after a fake follow-up turn (model continuing the convo)
            for cutoff_pattern in ['\nuser:', '\nUser:', '\n[INST]', '\n[USER]', '\n[ASSISTANT]',
                                   '<|im_start|>', '<|user|>', '\nUSER:', '\nASSISTANT:',
                                   '[USER]', '[ASSISTANT]', 'user:', 'User:']:
                idx = answer.find(cutoff_pattern)
                if idx > 0:
                    answer = answer[:idx].rstrip()
            # Remove any remaining template tokens
            for token in ['[INST]', '[/INST]', '[USER]', '[/USER]', '[ASSISTANT]', '[/ASSISTANT]',
                          '<|im_start|>', '<|im_end|>', '<|user|>', '<|assistant|>', '<|system|>',
                          '<s>', '</s>', '[OUT]', '#PriorityPulse']:
                answer = answer.replace(token, '')
            # Remove any "AreaPulse Civic AI:" self-prefix
            answer = re.sub(r'^(AreaPulse Civic AI|Assistant|AI|Bot)\s*:\s*', '',
                            answer, flags=re.IGNORECASE).strip()

            # If after cleanup we have very little left, fall back
            if len(answer) < 20:
                print(f"[llm_chat] response too short after cleanup ({len(answer)} chars), using fallback")
                raise ValueError("Empty response after cleanup")

            print(f"[llm_chat] HF SUCCESS, response length: {len(answer)}")
            if answer:
                result = {'type': 'text', 'message': answer}
                _LLM_CACHE[cache_key] = (now, result)
                return result

        except Exception as e:
            err_str = str(e).lower()
            print(f"[llm_chat] HF call failed: {e}")
            if 'quota' in err_str or '429' in err_str or 'rate' in err_str or 'limit' in err_str:
                return {
                    'type': 'text',
                    'message': ("I've hit the AI rate limit briefly. Please wait a minute "
                                "and try again.\n\nThese all run locally with no API:\n"
                                "• *show me potholes* — map markers\n"
                                "• *compare last 7 days* — table breakdown\n"
                                "• *how is Rohini doing* — area summary\n"
                                "• Open the **Insights** tab"),
                }

    # Deterministic fallback
    total = len(issues)
    open_n = sum(1 for i in issues if i.get('status') != 'resolved')
    by_tag = Counter(i.get('tag','other') for i in issues)
    top_tag = by_tag.most_common(1)[0] if by_tag else None
    hot = hottest_areas(issues, top_n=1)
    top_area = hot[0]['area'] if hot else None

    bits = [f'I\'m not sure how to answer **"{query}"** specifically, but here\'s what I know:']
    bits.append(f"\n📊 **{total}** reports in the system, **{open_n}** still open.")
    if top_tag:
        bits.append(f"🏷️ Most common category: **{top_tag[0]}** ({top_tag[1]} reports).")
    if top_area:
        bits.append(f"📍 Area needing most attention: **{top_area}**.")
    bits.append("\nTry asking:")
    bits.append("• Which area is most polluted?")
    bits.append("• Show me pothole locations on the map")
    bits.append("• Compare last 7 days")
    bits.append("• How is Rohini doing?")
    bits.append("• Which areas are cleanest?")

    return {'type': 'text', 'message': '\n'.join(bits)}


# ════════════════════════════════════════════════════════════════════
# 7. VISION AI — analyze civic-issue photos with Groq Llama-3.2-Vision
# ════════════════════════════════════════════════════════════════════

VISION_PROMPT = """You are analyzing a photo of a possible civic issue in Delhi, India.

Look at the image and respond with ONLY a valid JSON object (no markdown, no extra text) in this exact format:
{
  "category": "pothole" | "water" | "garbage" | "streetlight" | "traffic" | "noise" | "sewage" | "electricity" | "tree" | "other",
  "severity": "low" | "medium" | "high",
  "description": "1-2 sentence description of what is visible (e.g. 'Large pothole on a tarmac road, approximately 1 meter wide. Causes traffic obstruction.')",
  "confidence": 0-100
}

Severity rules:
- "high": dangerous, blocking traffic/access, large-scale, immediate hazard, public safety risk
- "medium": noticeable issue, needs attention but not urgent
- "low": minor, cosmetic, can wait

If the image does NOT show a civic issue (e.g. selfie, indoor photo, abstract), return:
{"category": "other", "severity": "low", "description": "No civic issue detected in image.", "confidence": 0}

Respond with JSON only."""


def analyze_image(image_b64, mime_type='image/jpeg'):
    """
    Analyzes a civic-issue photo using Groq's Llama-3.2-Vision (with Gemini fallback).
    Returns dict: { category, severity, description, confidence, source }
    """
    import json as _json
    import re as _re

    # ── Try Groq first (fast, generous free tier) ──
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key:
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
            )
            print("[analyze_image] calling Groq Llama-3.2-Vision...")
            completion = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                    ],
                }],
                max_tokens=300,
                temperature=0.2,
            )
            raw = (completion.choices[0].message.content or '').strip()
            return _parse_vision_json(raw, source='groq')
        except Exception as e:
            print(f"[analyze_image] Groq failed: {e}")
            # fall through to Gemini

    # ── Fallback: Gemini Vision ──
    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if gemini_key:
        try:
            import google.generativeai as genai
            import base64 as _b64
            genai.configure(api_key=gemini_key)
            print("[analyze_image] calling Gemini Vision...")
            model = genai.GenerativeModel('gemini-1.5-flash')
            img_bytes = _b64.b64decode(image_b64)
            resp = model.generate_content([
                VISION_PROMPT,
                {"mime_type": mime_type, "data": img_bytes},
            ])
            raw = (resp.text or '').strip()
            return _parse_vision_json(raw, source='gemini')
        except Exception as e:
            print(f"[analyze_image] Gemini failed: {e}")

    # ── No vision API available — fall back to nothing ──
    return {
        'category': 'other',
        'severity': 'medium',
        'description': 'AI vision unavailable. Please describe the issue manually.',
        'confidence': 0,
        'source': 'none',
        'error': 'No vision API key configured (set GROQ_API_KEY or GEMINI_API_KEY)',
    }


def _parse_vision_json(raw_text, source='unknown'):
    """Robustly extract JSON from a vision-model response, even if it's wrapped
    in markdown code fences or has extra text."""
    import json as _json, re as _re

    # Strip markdown code fences
    cleaned = _re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
    cleaned = _re.sub(r'\s*```$', '', cleaned).strip()

    # If there's extra prose, find the JSON object
    m = _re.search(r'\{[^{}]*"category"[^{}]*\}', cleaned, _re.DOTALL)
    if m:
        cleaned = m.group(0)

    try:
        data = _json.loads(cleaned)
    except _json.JSONDecodeError:
        # Try greedy match across whole string
        m = _re.search(r'\{.*\}', raw_text, _re.DOTALL)
        if not m:
            return {
                'category': 'other', 'severity': 'medium',
                'description': raw_text[:200] or 'Could not parse AI response',
                'confidence': 0, 'source': source,
                'error': 'JSON parse failed',
            }
        try:
            data = _json.loads(m.group(0))
        except _json.JSONDecodeError:
            return {
                'category': 'other', 'severity': 'medium',
                'description': raw_text[:200],
                'confidence': 0, 'source': source,
                'error': 'JSON parse failed',
            }

    # Validate fields with safe defaults
    valid_cats = {'pothole','water','garbage','streetlight','traffic',
                  'noise','sewage','electricity','tree','other'}
    valid_sev  = {'low','medium','high'}

    return {
        'category':    data.get('category', 'other') if data.get('category') in valid_cats else 'other',
        'severity':    data.get('severity', 'medium') if data.get('severity') in valid_sev else 'medium',
        'description': str(data.get('description', ''))[:300] or 'AI analysis complete',
        'confidence':  max(0, min(100, int(data.get('confidence', 70)))),
        'source':      source,
    }


# ════════════════════════════════════════════════════════════════════
# 8. AUTHORITY DISPATCH — draft formal complaint emails to govt agencies
# ════════════════════════════════════════════════════════════════════

# Maps issue category → preferred authority (matches database.py seeded agencies)
AUTHORITY_BY_TAG = {
    'pothole':     'PWD Delhi (Roads)',
    'water':       'Delhi Jal Board (Helpline)',
    'sewage':      'Delhi Jal Board (Helpline)',
    'garbage':     'MCD',     # zone-specific resolved at runtime
    'streetlight': 'NDMC',    # zone-specific resolved at runtime
    'traffic':     'Delhi Traffic Police',
    'electricity': 'BSES',    # zone-specific resolved at runtime
    'noise':       'Environment Dept Delhi',
    'tree':        'Forest Dept Delhi',
    'other':       'Delhi Citizen Helpline',
}

# Rough zone resolver for MCD / BSES / NDMC variants
def _resolve_zone_authority(tag, area):
    """Pick the right MCD / BSES variant based on Delhi zone."""
    a = (area or '').lower()
    NORTH = {'rohini','pitampura','model town','shalimar bagh','burari','narela',
             'bawana','alipur','mukherjee nagar','gtb nagar','adarsh nagar',
             'ashok vihar','wazirabad','bhalswa','kamla nagar','civil lines'}
    SOUTH = {'saket','vasant kunj','mehrauli','malviya nagar','hauz khas',
             'greater kailash','lajpat nagar','kalkaji','tughlakabad','okhla',
             'badarpur','sangam vihar','govindpuri','sarita vihar','jasola',
             'munirka','rk puram','vasant vihar','chirag delhi','pushp vihar','deoli'}
    EAST  = {'laxmi nagar','preet vihar','shahdara','geeta colony','mayur vihar',
             'patparganj','seelampur','welcome','mustafabad','bhajanpura',
             'vishwas nagar','pandav nagar','mandawali','anand vihar','karkardooma',
             'dilshad garden','jhilmil','vivek vihar','yamuna vihar','karawal nagar',
             'nand nagri','brahmpuri','gokulpuri','jaffrabad','maujpur','khajuri khas'}
    if tag == 'garbage':
        if any(z in a for z in NORTH): return 'MCD North Delhi'
        if any(z in a for z in SOUTH): return 'MCD South Delhi'
        if any(z in a for z in EAST):  return 'MCD East Delhi'
        return 'MCD South Delhi'
    if tag == 'electricity':
        if any(z in a for z in EAST): return 'BSES Yamuna'
        return 'BSES Rajdhani'
    if tag == 'streetlight':
        if 'connaught' in a or 'central' in a: return 'NDMC (New Delhi)'
        # streetlight outside NDMC zone → MCD
        if any(z in a for z in NORTH): return 'MCD North Delhi'
        if any(z in a for z in EAST):  return 'MCD East Delhi'
        return 'MCD South Delhi'
    return AUTHORITY_BY_TAG.get(tag, 'Delhi Citizen Helpline')


def find_authority_for_issue(issue, gov_agencies):
    """Match an issue to the most appropriate government agency.
    Returns the agency dict, or None if no match."""
    if not issue or not gov_agencies:
        return None
    tag = issue.get('tag') or 'other'
    area = issue.get('area') or ''
    target_name = _resolve_zone_authority(tag, area)

    # First try exact name match
    for ag in gov_agencies:
        if ag.get('name') == target_name:
            return ag
    # Loose match (e.g. target=MCD South Delhi → MCD anything)
    for ag in gov_agencies:
        if (target_name.split()[0] in (ag.get('name') or '')
                and ag.get('tag') == tag):
            return ag
    # Fallback: any agency matching the tag
    for ag in gov_agencies:
        if ag.get('tag') == tag:
            return ag
    # Last resort: general helpline
    for ag in gov_agencies:
        if ag.get('tag') == 'other':
            return ag
    return gov_agencies[0] if gov_agencies else None


def draft_dispatch(issue, agency, citizen_name=None):
    """
    Draft a formal complaint email from a citizen to a government agency.
    Uses HF Router (same chat backend) if available, else falls back to a
    deterministic template.

    Returns: { recipient_name, recipient_email, recipient_phone, subject, body, agency }
    """
    if not issue or not agency:
        return None

    # Build the basic facts the LLM (or template) needs
    citizen = citizen_name or issue.get('user') or 'A concerned citizen'
    area = issue.get('area') or 'Delhi'
    tag = (issue.get('tag') or 'civic').replace('_', ' ').title()
    severity = (issue.get('severity') or 'medium').upper()
    description = issue.get('description') or 'No description provided'
    landmark = issue.get('landmark') or ''
    lat = issue.get('lat'); lng = issue.get('lng')
    issue_id = issue.get('id', '?')
    timestamp = issue.get('timestamp')
    if timestamp:
        from datetime import datetime
        date_str = datetime.fromtimestamp(timestamp).strftime('%d %B %Y, %H:%M')
    else:
        date_str = 'recent'

    location_str = area
    if landmark: location_str += f" (near {landmark})"
    if lat and lng: location_str += f" | GPS: {lat:.5f}, {lng:.5f}"
    if lat and lng: maps_link = f"https://maps.google.com/?q={lat},{lng}"
    else: maps_link = None

    # ── Try LLM for a polished draft ──
    api_key = (os.environ.get('HF_TOKEN')
               or os.environ.get('HUGGINGFACE_API_KEY')
               or os.environ.get('HUGGINGFACE_TOKEN'))
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://router.huggingface.co/v1", api_key=api_key)

            sys_prompt = """You are drafting a formal complaint email from a Delhi citizen to a government agency about a civic issue. Tone: respectful, factual, urgent but not aggressive. No emojis, no markdown headers. Include all the provided facts. End with the citizen's name. Keep it under 200 words. Output ONLY the email body — no subject line, no salutation guesses, no 'Sincerely' added by you (we'll handle that). Start directly with 'Dear ...' and end with the citizen's name."""

            user_prompt = f"""Draft a complaint email with these facts:
- Issue: {tag}
- Severity: {severity}
- Location: {location_str}
- Date reported: {date_str}
- Citizen description: "{description}"
- Recipient: {agency.get('name', 'Authority')} ({agency.get('focus','')})
- Citizen name: {citizen}
- Reference Issue ID: PM-{issue_id}
{f'- Map link: {maps_link}' if maps_link else ''}

Draft the email body now."""

            completion = client.chat.completions.create(
                model="meta-llama/Llama-3.1-8B-Instruct:featherless-ai",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=400,
                temperature=0.3,
                stop=["[USER]", "[ASSISTANT]", "[INST]"],
            )
            body = (completion.choices[0].message.content or '').strip()
            # Cleanup
            for token in ['[INST]', '[/INST]', '[USER]', '[ASSISTANT]', '<|im_end|>']:
                body = body.replace(token, '')
            body = body.strip()
            if len(body) < 50:
                raise ValueError("LLM body too short")
            print(f"[draft_dispatch] LLM SUCCESS, length: {len(body)}")
            llm_used = True
        except Exception as e:
            print(f"[draft_dispatch] LLM failed: {e} — using template")
            body = _template_dispatch_body(citizen, agency, tag, severity, location_str,
                                            date_str, description, issue_id, maps_link)
            llm_used = False
    else:
        body = _template_dispatch_body(citizen, agency, tag, severity, location_str,
                                        date_str, description, issue_id, maps_link)
        llm_used = False

    subject = f"Civic Complaint: {tag} reported at {area} (Ref: PM-{issue_id})"

    return {
        'recipient_name':  agency.get('name'),
        'recipient_email': agency.get('email', ''),
        'recipient_phone': agency.get('phone', ''),
        'agency':          agency,
        'subject':         subject,
        'body':            body,
        'llm_drafted':     llm_used,
        'maps_link':       maps_link,
    }


def _template_dispatch_body(citizen, agency, tag, severity, location_str,
                             date_str, description, issue_id, maps_link):
    """Deterministic template used when LLM is unavailable."""
    lines = [
        f"Dear {agency.get('name', 'Concerned Authority')},",
        "",
        f"I am writing to formally report a {tag.lower()} issue in our area that "
        f"requires your urgent attention.",
        "",
        f"Details of the complaint:",
        f"  • Type:        {tag}",
        f"  • Severity:    {severity}",
        f"  • Location:    {location_str}",
        f"  • Reported on: {date_str}",
        f"  • Reference:   PM-{issue_id}",
        "",
        f"Description from citizens at the location:",
        f"\"{description}\"",
        "",
    ]
    if maps_link:
        lines.append(f"Exact location on map: {maps_link}")
        lines.append("")
    lines.extend([
        f"This issue has been reported through Problem Map, Delhi's citizen-led "
        f"civic-reporting platform. We respectfully request that the appropriate "
        f"team be assigned to inspect and resolve this matter at the earliest.",
        "",
        f"We would appreciate an acknowledgement and an estimated resolution timeline.",
        "",
        f"Thank you for your prompt attention to this matter.",
        "",
        f"Sincerely,",
        f"{citizen}",
        f"(via Problem Map — problem-map.onrender.com)",
    ])
    return '\n'.join(lines)