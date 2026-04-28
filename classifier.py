KEYWORDS = {
    'pothole':     ['pothole','crater','hole in road','bump','broken road','khada','damaged road','road damage'],
    'water':       ['water','leak','pipe','flood','waterlog','pani','overflow','pipeline','burst pipe','no water','puddle'],
    'garbage':     ['garbage','waste','trash','kachra','dump','litter','filth','burning waste','stray dog','rats','rodent'],
    'streetlight': ['streetlight','street light','lamp post','dark street','batti','light pole','no light','light not working'],
    'traffic':     ['traffic','signal','jam','congestion','accident','zebra crossing','speed breaker','traffic light'],
    'noise':       ['noise','sound','loud','speaker','music','construction noise','drilling','awaz','loudspeaker','late night'],
    'sewage':      ['sewage','sewer','drain','blocked drain','stink','nali','naali','open drain','manhole'],
    'electricity': ['power cut','electric','current','wire','transformer','outage','bijli','no electricity','power failure','sparking'],
    'tree':        ['tree','branch','fallen tree','blocking tree','ped','uprooted'],
}

def auto_tag(desc: str) -> str:
    d = desc.lower()
    for tag, words in KEYWORDS.items():
        if any(w in d for w in words):
            return tag
    return 'other'