from flask import Flask, render_template, request, send_file
import feedparser, json, time, math, re, os, requests
from collections import Counter
from io import BytesIO
from PIL import Image, ImageOps
from urllib.parse import quote_plus

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # prevent static caching

DOMAINS = ["land", "air", "sea", "space", "cyber"]
REGIONS = ["europe", "asia", "middle-east", "americas", "africa"]

THUMB_DIR = "thumb_cache"
os.makedirs(THUMB_DIR, exist_ok=True)

# ------------------ Custom Filters ------------------
@app.template_filter("ue")
def urlencode_filter(s):
    """Jinja2 filter to safely URL-encode parameters"""
    return quote_plus(s or "")

@app.template_filter('datetimeformat')
def datetimeformat(value):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M') if value else ''
    except Exception:
        return ''

# ------------------ Feed Handling ------------------
def load_feeds():
    with open("feeds.json", "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_articles():
    feeds = load_feeds()
    articles = []
    for feed in feeds:
        try:
            d = feedparser.parse(feed["url"])
        except Exception:
            continue
        for entry in d.entries:
            # published timestamp
            published_ts = None
            if getattr(entry, "published_parsed", None):
                try:
                    published_ts = time.mktime(entry.published_parsed)
                except Exception:
                    published_ts = None

            # image extraction
            image = None
            if getattr(entry, "media_content", None):
                try:
                    image = entry.media_content[0].get("url")
                except Exception:
                    pass
            if not image and getattr(entry, "media_thumbnail", None):
                try:
                    image = entry.media_thumbnail[0].get("url")
                except Exception:
                    pass
            if not image and getattr(entry, "links", None):
                for l in entry.links:
                    if l.get("type", "").startswith("image/"):
                        image = l.get("href")
                        break

            articles.append({
                "title": getattr(entry, "title", "(untitled)"),
                "link": getattr(entry, "link", "#"),
                "summary": getattr(entry, "summary", ""),
                "source": feed.get("name", "Unknown"),
                "published": published_ts,
                "image": image or ""
            })

    # newest first
    articles.sort(key=lambda x: x["published"] or 0, reverse=True)
    return articles

def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower())

def compute_trends(articles, top_n=10):
    source_counts = Counter(a["source"] for a in articles)
    top_sources = source_counts.most_common(8)

    stop = set("""
    a an the and or of to for with in on at from by as is are was were will would should could can may might 
    about after before over under into out up down new more most other some any each few best top vs amid 
    during despite among than within without against between around including while near world
    air land sea space cyber asia europe americas africa middle east forces defense military armed army navy 
    airforce air-force spaceforce space-force
    """.split())

    words = []
    for a in articles:
        words += [w for w in normalize(a["title"]).split() if len(w) > 3 and w not in stop]
    word_counts = Counter(words).most_common(top_n)
    return top_sources, word_counts

# ------------------ Routes ------------------
@app.route("/")
def index():
    articles = fetch_articles()

    # Query params
    q = (request.args.get("q") or "").strip().lower()
    region = (request.args.get("region") or "").strip().lower()
    domain = (request.args.get("domain") or "").strip().lower()
    source = (request.args.get("source") or "").strip().lower()
    view = (request.args.get("view") or "grid").lower()
    page = int(request.args.get("page", 1))
    per_page = 18

    all_sources = sorted(list({a["source"] for a in articles}))

    def matches(a):
        text = (a["title"] + " " + a["summary"]).lower()
        ok = True
        if q: ok = ok and (q in text)
        if region: ok = ok and (region in text)
        if domain: ok = ok and (domain in text)
        if source: ok = ok and (source == a["source"].lower())
        return ok

    filtered = [a for a in articles if matches(a)]
    total = len(filtered)

    # sidebar trends
    top_sources, top_keywords = compute_trends(filtered)

    # Pagination
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    return render_template(
        "index.html",
        articles=page_items,
        page=page,
        pages=pages,
        q=q,
        region=region,
        domain=domain,
        source=source,
        view=view,
        domains=DOMAINS,
        regions=REGIONS,
        sources=all_sources,
        top_sources=top_sources,
        top_keywords=top_keywords,
        total=total
    )

@app.route("/feeds")
def feeds_page():
    return render_template("feeds.html", feeds=load_feeds())

@app.route("/thumb")
def thumb():
    url = request.args.get("u", "")
    w = int(request.args.get("w", 500))
    h = int(request.args.get("h", 500))
    if not url:
        return "", 404
    key = f"{quote_plus(url)}_{w}x{h}.jpg"
    path = os.path.join(THUMB_DIR, key)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    try:
        r = requests.get(url, timeout=5, stream=True)
        r.raise_for_status()
        im = Image.open(r.raw).convert("RGB")
        im = ImageOps.fit(im, (w, h), Image.LANCZOS)
        im.save(path, "JPEG", quality=80)
        return send_file(path, mimetype="image/jpeg")
    except Exception:
        return "", 404

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
