"""
Firebase Firestore database layer for Problem Map.
Replaces the previous PostgreSQL backend. All public function signatures
are preserved so app.py keeps working without changes.

Setup:
1. Create a Firebase project at https://console.firebase.google.com
2. Enable Firestore (Native mode)
3. Generate a service-account key:  Project Settings → Service accounts → "Generate new private key"
4. Save the JSON file as `firebase_key.json` in the project root
   OR set env var GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
   OR set env var FIREBASE_CREDENTIALS_JSON to the JSON string itself (good for Render/Heroku)
"""

import os, time, math, json
import firebase_admin
from firebase_admin import credentials, firestore

# ── INIT ──────────────────────────────────────────────
_db = None

def _init_firebase():
    global _db
    if firebase_admin._apps:
        _db = firestore.client()
        return _db

    # 1) JSON string in env (for Render / Heroku)
    cred_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
    else:
        # 2) File path (local dev)
        path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'firebase_key.json')
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Firebase credentials not found. Place 'firebase_key.json' in project root "
                f"or set FIREBASE_CREDENTIALS_JSON / GOOGLE_APPLICATION_CREDENTIALS."
            )
        cred = credentials.Certificate(path)

    firebase_admin.initialize_app(cred)
    _db = firestore.client()
    return _db


def get_db():
    """Returns the Firestore client (kept for compatibility)."""
    global _db
    if _db is None:
        _init_firebase()
    return _db


# ── COLLECTION NAMES ──────────────────────────────────
USERS         = 'users'
ISSUES        = 'issues'
NGOS          = 'ngos'
GOV_AGENCIES  = 'gov_agencies'
COMMUNITY     = 'community_posts'
COMMUNITY_LIKES = 'community_likes'
ISSUE_ACTIONS = 'issue_actions'
SPAM_REPORTS  = 'spam_reports'        # NEW — for AI spam moderation
REVIEW_QUEUE  = 'review_queue'        # NEW — moderate queue
AI_INSIGHTS   = 'ai_insights'         # NEW — cached AI insights


# ── INIT (creates indexes / seed data) ────────────────
def init_db():
    """Initialize Firestore — collections are created on first write,
    so we just ensure the client is connected."""
    get_db()
    return True


# ── ID HELPER ─────────────────────────────────────────
def _next_int_id(collection_name):
    """Firestore uses string doc IDs by default. We keep numeric IDs (1,2,3…)
    so existing app.py routes like /upvote/<int:id> keep working."""
    db = get_db()
    counter_ref = db.collection('_counters').document(collection_name)
    snap = counter_ref.get()
    if snap.exists:
        n = snap.to_dict().get('n', 0) + 1
    else:
        n = 1
    counter_ref.set({'n': n})
    return n


# ── ISSUES ────────────────────────────────────────────
def insert_issue(area, description, tag, user, lat, lng,
                 image=None, severity='medium', landmark='', contact=''):
    db = get_db()
    issue_id = _next_int_id(ISSUES)
    doc = {
        'id':          issue_id,
        'area':        area,
        'description': description,
        'tag':         tag,
        'user':        user,
        'lat':         lat,
        'lng':         lng,
        'image':       image,
        'severity':    severity,
        'landmark':    landmark,
        'contact':     contact,
        'timestamp':   time.time(),
        'upvotes':     0,
        'priority':    0.0,
        'verified':    0,
        'status':      'open',
        'assigned_to': None,
    }
    db.collection(ISSUES).document(str(issue_id)).set(doc)
    return issue_id


def get_issues():
    db = get_db()
    try:
        docs = db.collection(ISSUES).stream()
        out = [d.to_dict() for d in docs]
        out.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return out
    except Exception as e:
        print(f"[get_issues] {e}")
        return []


def get_issues_by_user(username):
    db = get_db()
    docs = db.collection(ISSUES).where('user', '==', username).stream()
    out = [d.to_dict() for d in docs]
    out.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return out


def upvote_issue(issue_id):
    db = get_db()
    ref = db.collection(ISSUES).document(str(issue_id))
    ref.update({'upvotes': firestore.Increment(1)})


def verify_issue(issue_id):
    db = get_db()
    ref = db.collection(ISSUES).document(str(issue_id))
    ref.update({'verified': firestore.Increment(1), 'status': 'verified'})


def resolve_issue(issue_id, assigned_to=None):
    db = get_db()
    ref = db.collection(ISSUES).document(str(issue_id))
    update = {'status': 'resolved'}
    if assigned_to:
        update['assigned_to'] = assigned_to
    ref.update(update)


def escalate_issue(issue_id, assigned_to=None):
    db = get_db()
    ref = db.collection(ISSUES).document(str(issue_id))
    update = {'status': 'escalated'}
    if assigned_to:
        update['assigned_to'] = assigned_to
    ref.update(update)


# ── ISSUE ACTIONS (toggle: upvote, verify, escalate) ──
def toggle_issue_action(user, issue_id, action):
    """Toggle a user action on an issue. Returns 'added' or 'removed'."""
    db = get_db()
    key = f"{user}__{issue_id}__{action}"
    ref = db.collection(ISSUE_ACTIONS).document(key)
    snap = ref.get()
    issue_ref = db.collection(ISSUES).document(str(issue_id))

    if snap.exists:
        ref.delete()
        if action == 'upvote':
            issue_ref.update({'upvotes': firestore.Increment(-1)})
        elif action == 'verify':
            issue_ref.update({'verified': firestore.Increment(-1)})
        return 'removed'
    else:
        ref.set({'user_name': user, 'issue_id': issue_id, 'action': action,
                 'timestamp': time.time()})
        if action == 'upvote':
            issue_ref.update({'upvotes': firestore.Increment(1)})
        elif action == 'verify':
            issue_ref.update({'verified': firestore.Increment(1), 'status': 'verified'})
        elif action == 'escalate':
            issue_ref.update({'status': 'escalated'})
        return 'added'


def get_user_actions(user, issue_ids):
    """Returns dict: { issue_id: set('upvote','verify','escalate') }
    Uses single-field query + client-side filter to avoid composite indexes."""
    if not user or not issue_ids:
        return {}
    db = get_db()
    result = {}
    issue_id_set = set(issue_ids)
    try:
        # Single where → no composite index required
        docs = db.collection(ISSUE_ACTIONS).where('user_name', '==', user).stream()
        for d in docs:
            data = d.to_dict()
            iid = data.get('issue_id')
            if iid in issue_id_set:
                result.setdefault(iid, set()).add(data.get('action'))
    except Exception as e:
        print(f"[get_user_actions] {e}")
    return result


# ── USERS / POINTS ────────────────────────────────────
def add_points(user, pts):
    if not user or not user.strip():
        return
    db = get_db()
    ref = db.collection(USERS).document(user)
    snap = ref.get()
    if snap.exists:
        ref.update({'points': firestore.Increment(pts)})
    else:
        ref.set({'name': user, 'points': max(0, pts)})


def get_user_stats(username):
    db = get_db()
    user_doc = db.collection(USERS).document(username).get()
    points = user_doc.to_dict().get('points', 0) if user_doc.exists else 0

    issues = list(db.collection(ISSUES).where('user', '==', username).stream())
    total = len(issues)
    resolved = sum(1 for i in issues if i.to_dict().get('status') == 'resolved')

    return {'points': points, 'total_reported': total, 'total_resolved': resolved}


# ── NGOs ──────────────────────────────────────────────
def get_ngos(tag_filter=None, area_filter=None, sort_by='resolved'):
    db = get_db()
    q = db.collection(NGOS)
    if tag_filter:
        q = q.where('tag', '==', tag_filter)
    if area_filter:
        q = q.where('area', '==', area_filter)
    rows = [d.to_dict() for d in q.stream()]
    if sort_by == 'rating':
        rows.sort(key=lambda x: x.get('rating', 0), reverse=True)
    else:
        rows.sort(key=lambda x: x.get('issues_resolved', 0), reverse=True)
    return rows


def get_gov_agencies(tag_filter=None, area_filter=None):
    db = get_db()
    q = db.collection(GOV_AGENCIES)
    if tag_filter:
        q = q.where('tag', '==', tag_filter)
    if area_filter:
        q = q.where('area', '==', area_filter)
    rows = [d.to_dict() for d in q.stream()]
    rows.sort(key=lambda x: x.get('name', ''))
    return rows


def get_nearby_ngos(lat, lng, tag=None, limit=5):
    db = get_db()
    q = db.collection(NGOS)
    if tag and tag != 'other':
        # Firestore can't do OR easily — fetch tag matches + 'other' separately
        rows1 = [d.to_dict() for d in q.where('tag', '==', tag).stream()]
        rows2 = [d.to_dict() for d in q.where('tag', '==', 'other').stream()]
        rows = rows1 + rows2
    else:
        rows = [d.to_dict() for d in q.stream()]

    for r in rows:
        if r.get('lat') is None or r.get('lng') is None:
            r['distance_km'] = 999
            continue
        d = math.sqrt((lat - r['lat']) ** 2 + (lng - r['lng']) ** 2)
        r['distance_km'] = round(d * 111, 1)
    rows.sort(key=lambda x: x['distance_km'])
    return rows[:limit]


# ── COMMUNITY POSTS ──────────────────────────────────
def get_community_posts(area=None, limit=30):
    db = get_db()
    q = db.collection(COMMUNITY)
    if area:
        q = q.where('area', '==', area)
    rows = [d.to_dict() for d in q.stream()]
    rows.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return rows[:limit]


def add_community_post(user, message, area, post_type='update'):
    db = get_db()
    pid = _next_int_id(COMMUNITY)
    db.collection(COMMUNITY).document(str(pid)).set({
        'id':        pid,
        'user':      user,
        'message':   message,
        'area':      area,
        'post_type': post_type,
        'timestamp': time.time(),
        'likes':     0,
    })
    return pid


def like_post(post_id, user):
    db = get_db()
    key = f"{user}__{post_id}"
    ref = db.collection(COMMUNITY_LIKES).document(key)
    if ref.get().exists:
        return False
    ref.set({'user_name': user, 'post_id': post_id, 'timestamp': time.time()})
    db.collection(COMMUNITY).document(str(post_id)).update({
        'likes': firestore.Increment(1)
    })
    return True


# ── SPAM / MODERATION (NEW for AI) ────────────────────
def save_spam_report(report_data, ai_analysis):
    """Move a flagged report into spam_reports (does NOT delete original)."""
    db = get_db()
    sid = _next_int_id(SPAM_REPORTS)
    db.collection(SPAM_REPORTS).document(str(sid)).set({
        'id':          sid,
        'report':      report_data,
        'ai_analysis': ai_analysis,
        'timestamp':   time.time(),
    })
    return sid


def add_to_review_queue(report_data, ai_analysis):
    db = get_db()
    rid = _next_int_id(REVIEW_QUEUE)
    db.collection(REVIEW_QUEUE).document(str(rid)).set({
        'id':          rid,
        'report':      report_data,
        'ai_analysis': ai_analysis,
        'reviewed':    False,
        'timestamp':   time.time(),
    })
    return rid


def get_spam_reports(limit=50):
    db = get_db()
    try:
        docs = db.collection(SPAM_REPORTS).stream()
        out = [d.to_dict() for d in docs]
        out.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return out[:limit]
    except Exception as e:
        print(f"[get_spam_reports] {e}")
        return []


def get_review_queue(limit=50):
    db = get_db()
    try:
        docs = db.collection(REVIEW_QUEUE).stream()
        out = [d.to_dict() for d in docs if not d.to_dict().get('reviewed')]
        return out[:limit]
    except Exception as e:
        print(f"[get_review_queue] {e}")
        return []


def count_user_recent_reports(user, seconds=300):
    """Count reports by a user in the last `seconds`. Used for spam detection.
    Avoids composite-index requirement by filtering timestamp client-side."""
    if not user:
        return 0
    db = get_db()
    cutoff = time.time() - seconds
    try:
        docs = db.collection(ISSUES).where('user', '==', user).stream()
        return sum(1 for d in docs if d.to_dict().get('timestamp', 0) >= cutoff)
    except Exception as e:
        print(f"[count_user_recent_reports] {e}")
        return 0


# ── SEEDING (NGOs, gov, demo issues) ─────────────────
def seed_real_issues():
    """Seed initial NGOs, government agencies, and demo issues if empty."""
    db = get_db()

    # Seed NGOs
    if not list(db.collection(NGOS).limit(1).stream()):
        ngos = [
            ('WaterAid India','water','+91-11-4052-4444','info@wateraid.org','Hauz Khas, South Delhi','Hauz Khas',28.5494,77.2001,'💧','Clean water & sanitation infrastructure',42,18,4.6),
            ('Delhi Jal Board (Citizens)','sewage','1916','citizen@djb.delhi.gov.in','Jhandewalan, New Delhi','Karol Bagh',28.6514,77.1907,'🚰','Sewage, drainage & water supply complaints',67,34,4.2),
            ('Road Safety Network India','pothole','+91-98100-00001','roads@rsni.org','Connaught Place, New Delhi','Connaught Place',28.6315,77.2167,'🛣️','Road safety & pothole repair advocacy',38,22,4.5),
            ('SaveLIFE Foundation','traffic','+91-22-4900-2220','info@savelifefoundation.org','Lajpat Nagar, South Delhi','Lajpat Nagar',28.5677,77.2378,'🚦','Traffic safety, road accidents & signals',55,29,4.7),
            ('Chintan Environmental','garbage','+91-11-2753-2346','info@chintan-india.org','Shahdara, East Delhi','Shahdara',28.6706,77.2944,'♻️','Waste management, recycling & clean-up',89,41,4.8),
            ('Delhi Power Citizens Forum','streetlight','+91-11-2345-6789','help@dpcf.in','Karol Bagh, West Delhi','Karol Bagh',28.6514,77.1907,'💡','Streetlights & BSES electricity complaints',31,15,4.1),
            ('Awaaz Foundation','noise','+91-22-2369-7571','awaaz@awaazfoundation.org','Rohini, North Delhi','Rohini',28.7041,77.1025,'🔇','Noise pollution & air quality advocacy',28,12,4.3),
            ('Delhi Tree Society','tree','+91-11-2300-0001','dts@delhitrees.org','Mehrauli, South Delhi','Mehrauli',28.5244,77.1855,'🌳','Tree plantation & fallen tree removal',19,9,4.4),
            ('BSES Rajdhani Consumer Cell','electricity','19123','consumer@bsesrajdhani.com','Nehru Place, South Delhi','Greater Kailash',28.5494,77.2378,'⚡','Power cuts, meter & electrical safety',74,33,4.0),
            ('Paryavaran Mitra Delhi','garbage','+91-11-4100-2200','contact@paryavaranmitra.org','Pitampura, North Delhi','Pitampura',28.7007,77.1311,'🌿','Environmental cleanliness & waste mgmt',45,20,4.5),
            ('Delhi Road Repair Forum','pothole','+91-98111-55566','info@delhiroads.org','Dwarka, South West Delhi','Dwarka',28.5921,77.0460,'🚧','Pothole complaints & road repair follow-up',33,16,4.2),
            ('Safai Sena','garbage','+91-11-2950-1234','safaisena@gmail.com','Okhla Industrial Area','Okhla',28.5355,77.2780,'🧹','Garbage collection & street cleaning drives',62,28,4.6),
            ('Vatavaran Foundation','water','+91-11-4150-9900','info@vatavaran.org','Vasant Kunj, South Delhi','Vasant Kunj',28.5200,77.1590,'💦','Rainwater harvesting & water conservation',22,11,4.4),
            ('Green Delhi Foundation','tree','+91-98102-33445','greendelhi@gdf.org','Model Town, North Delhi','Model Town',28.7167,77.1900,'🌱','Urban greening & park maintenance',17,8,4.3),
            ('Delhi Pollution Control Cmt','noise','+91-11-2233-0400','dpcc@nic.in','Pragati Vihar, Central','Daryaganj',28.6417,77.2353,'📊','Pollution & industrial violation complaints',34,18,4.1),
            ('Delhi Citizen Helpline','other','1031','pgrams@delhi.gov.in','Connaught Place, New Delhi','Connaught Place',28.6315,77.2167,'🏛️','General civic issues & govt complaints',120,67,3.9),
        ]
        for n in ngos:
            nid = _next_int_id(NGOS)
            db.collection(NGOS).document(str(nid)).set({
                'id': nid, 'name': n[0], 'tag': n[1], 'phone': n[2], 'email': n[3],
                'address': n[4], 'area': n[5], 'lat': n[6], 'lng': n[7],
                'icon': n[8], 'focus': n[9],
                'issues_resolved': n[10], 'issues_escalated': n[11], 'rating': n[12],
                'org_type': 'ngo',
            })

    # Seed Government agencies
    if not list(db.collection(GOV_AGENCIES).limit(1).stream()):
        agencies = [
            ('MCD North Delhi','garbage','155305','northdelhi@mcd.gov.in','Civic Centre, New Delhi','Connaught Place',28.6315,77.2167,'🏛️','North Delhi garbage & civic complaints','Municipal Corporation of Delhi'),
            ('MCD South Delhi','garbage','155303','southdelhi@mcd.gov.in','Green Park Extension','Hauz Khas',28.5494,77.2001,'🏛️','South Delhi garbage & civic complaints','Municipal Corporation of Delhi'),
            ('MCD East Delhi','garbage','155304','eastdelhi@mcd.gov.in','Laxmi Nagar, East Delhi','Laxmi Nagar',28.6310,77.2780,'🏛️','East Delhi garbage & civic complaints','Municipal Corporation of Delhi'),
            ('PWD Delhi (Roads)','pothole','011-23490175','secy.pwd@delhi.gov.in','Indraprastha Estate','Daryaganj',28.6417,77.2353,'🛣️','Delhi public works — road repair & pothole','Public Works Department'),
            ('Delhi Traffic Police','traffic','011-23490162','trafficdelhi@nic.in','ITO, Central Delhi','Daryaganj',28.6417,77.2353,'👮','Traffic violations, signals & road accidents','Delhi Police'),
            ('Delhi Jal Board (Helpline)','water','1916','md@djb.delhi.gov.in','Varunalaya Phase II','Civil Lines',28.6800,77.2250,'💧','Water supply, pipeline & sewage issues','Delhi Jal Board'),
            ('BSES Yamuna','electricity','19122','consumer@bsesyamuna.com','Karkardooma, East Delhi','Preet Vihar',28.6355,77.2944,'⚡','East Delhi power cuts & electricity issues','BSES Yamuna Power Ltd'),
            ('BSES Rajdhani','electricity','19123','consumer@bsesrajdhani.com','Nehru Place, South Delhi','Greater Kailash',28.5494,77.2378,'⚡','South/West Delhi electricity complaints','BSES Rajdhani Power Ltd'),
            ('NDMC (New Delhi)','streetlight','1533','grievance@ndmc.gov.in','Palika Bhawan, New Delhi','Connaught Place',28.6315,77.2167,'🏙️','NDMC area: lights, roads & drains','New Delhi Municipal Council'),
            ('Delhi Fire Service','other','101','dfs@delhi.gov.in','Connaught Place, New Delhi','Connaught Place',28.6315,77.2167,'🚒','Fire hazards & emergency response','Delhi Fire Service'),
            ('Environment Dept Delhi','noise','+91-11-2336-1800','envt@delhi.gov.in','Paryavaran Bhawan','Daryaganj',28.6417,77.2353,'🌍','Air, noise & environmental violations','Delhi Govt Environment Dept'),
            ('Forest Dept Delhi','tree','+91-11-2306-4911','forest@delhi.gov.in','Aruna Asaf Ali Marg','Daryaganj',28.6417,77.2353,'🌳','Tree cutting permissions & fallen trees','Delhi Forest Department'),
        ]
        for a in agencies:
            aid = _next_int_id(GOV_AGENCIES)
            db.collection(GOV_AGENCIES).document(str(aid)).set({
                'id': aid, 'name': a[0], 'tag': a[1], 'phone': a[2], 'email': a[3],
                'address': a[4], 'area': a[5], 'lat': a[6], 'lng': a[7],
                'icon': a[8], 'focus': a[9], 'department': a[10],
            })

    # Seed demo issues
    if not list(db.collection(ISSUES).limit(1).stream()):
        seeds = [
            ('Rohini',          'Massive pothole on Sector 3 road near D-Mall causing daily accidents', 'pothole', 'system_seed', 'open',     14, 28.7041, 77.1025, 'high'),
            ('Connaught Place', 'Streetlight not working on Outer Circle for past 2 weeks',              'streetlight','system_seed','open',  6, 28.6315, 77.2167, 'medium'),
            ('Lajpat Nagar',    'Garbage piling up near Central Market - nobody is collecting',         'garbage', 'system_seed','open',     11, 28.5677, 77.2378, 'high'),
            ('Dwarka',          'Sewage overflow on Sector 6 main road, very bad smell',                'sewage',  'system_seed','verified', 9, 28.5921, 77.0460, 'high'),
            ('Karol Bagh',      'Water pipeline leak flooding basement of nearby shops',                'water',   'system_seed','escalated',7, 28.6514, 77.1907, 'medium'),
            ('Hauz Khas',       'Traffic signal not functioning at main junction during peak hours',    'traffic', 'system_seed','open',    13, 28.5494, 77.2001, 'high'),
            ('Saket',           'Loud construction noise late at night near residential area',          'noise',   'system_seed','open',     5, 28.5244, 77.2090, 'medium'),
            ('Shahdara',        'Power cut for 6+ hours daily, transformer issue',                      'electricity','system_seed','open', 8, 28.6706, 77.2944, 'high'),
            ('Mayur Vihar',     'Fallen tree blocking the road after recent storm',                     'tree',    'system_seed','resolved',4, 28.6090, 77.2944, 'medium'),
            ('Janakpuri',       'Pothole near A-block causing two-wheeler accidents',                   'pothole', 'system_seed','open',    10, 28.6219, 77.0878, 'high'),
            ('Pitampura',       'Open drain near community park is dangerous for children',             'sewage',  'system_seed','verified',6, 28.7007, 77.1311, 'medium'),
            ('Vasant Kunj',     'Streetlights flickering on Sector C roads',                            'streetlight','system_seed','open', 3, 28.5200, 77.1590, 'low'),
        ]
        for s in seeds:
            iid = _next_int_id(ISSUES)
            db.collection(ISSUES).document(str(iid)).set({
                'id': iid, 'area': s[0], 'description': s[1], 'tag': s[2],
                'user': s[3], 'status': s[4], 'upvotes': s[5],
                'lat': s[6], 'lng': s[7], 'severity': s[8],
                'image': None, 'landmark': '', 'contact': '',
                'priority': 0.0, 'verified': 1 if s[4] != 'open' else 0,
                'assigned_to': None, 'timestamp': time.time() - (3600 * (12 - len(s)))
            })
