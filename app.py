from flask import Flask, render_template, request
import feedparser, json, time, math, re

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # avoid stale CSS during dev

# Filters for dropdowns (kept simple & explicit)
REGIONS = ["americas", "europe", "asia", "middle-east", "africa", "global"]
DOMAINS = ["general", "land", "air", "sea", "space", "cyber", "policy", "industry", "analysis"]

# ---------- Utilities ----------

def load_feeds():
    with open("feeds.json", "r", encoding="utf-8") as f:
        return json.load(f)

def _strip_html(s):
    if not s:
        return ""
    # remove tags
    s = re.sub(r"<[^>]+>", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _find_image(entry):
    """
    Try several places where feeds commonly put images.
    Return a URL string or "" if none found.
    """
    # media_content
    if getattr(entry, "media_content", None):
        try:
            url = entry.media_content[0].get("url")
            if url: return url
        except Exception:
            pass

    # media_thumbnail
    if getattr(entry, "media_thumbnail", None):
        try:
            url = entry.media_thumbnail[0].get("url")
            if url: return url
        except Exception:
            pass

    # enclosures/links with type=image/*
    for attr in ("links", "enclosures"):
        items = getattr(entry, attr, None)
        if items:
            for l in items:
                t = (l.get("type") or "").lower()
                if t.startswith("image/"):
                    url = l.get("href")
                    if url: return url

    # look inside summary for an <img src=...>
    html = getattr(entry, "summary", "") or getattr(entry, "content", [{}])[0].get("value", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    return ""

def _published_timestamp(entry):
    for attr in ("published_parsed", "updated_parsed"):
        ts = getattr(entry, attr, None)
        if ts:
            try:
                return time.mktime(ts)
            except Exception:
                continue
    return None

def _fmt_datetime(ts):
    if not ts:
        return ""
    try:
        import datetime
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

# ---------- Data fetch ----------

def fetch_articles():
    """
    Pull feeds and return a list of normalized article dicts.
    Performance: only keep last 5 per feed AND only items within last 24h.
    """
    feeds = load_feeds()
    articles = []
    cutoff = time.time() - 24 * 3600  # 24 hours ago

    for feed in feeds:
        url = feed.get("url")
        name = feed.get("name", "Unknown")
        region = (feed.get("region") or "").lower()
        domain = (feed.get("domain") or "").lower()

        if not url:
            continue

        try:
            d = feedparser.parse(url)
        except Exception:
            continue

        added = 0
        for entry in d.entries:
            if added >= 5:
                break

            published_ts = _published_timestamp(entry)
            # strictly require timestamp & freshness for speed and relevance
            if not published_ts or published_ts < cutoff:
                continue

            title = getattr(entry, "title", "(untitled)") or "(untitled)"
            link = getattr(entry, "link", "#") or "#"
            raw_summary = getattr(entry, "summary", "") or ""
            image = _find_image(entry)

            # keep summaries readable & shortish (~700 chars soft cap)
            summary = _strip_html(raw_summary)
            if len(summary) > 700:
                summary = summary[:700].rstrip() + "…"

            articles.append({
                "title": title,
                "link": link,
                "summary": summary,
                "source": name,
                "published": published_ts,
                "image": image,
                "region": region,
                "domain": domain
            })
            added += 1

    # newest first
    articles.sort(key=lambda x: x["published"] or 0, reverse=True)
    return articles

# ---------- Routes ----------

@app.route("/")
def index():
    articles = fetch_articles()

    # Query params
    q = (request.args.get("q") or "").strip().lower()
    region = (request.args.get("region") or "").strip().lower()
    domain = (request.args.get("domain") or "").strip().lower()
    page = int(request.args.get("page", 1))
    per_page = 15  # 3 cols x 5 rows like your screenshot

    def matches(a):
        if q:
            t = (a["title"] + " " + a["summary"]).lower()
            if q not in t:
                return False
        if region and a["region"] != region:
            return False
        if domain and a["domain"] != domain:
            return False
        return True

    filtered = [a for a in articles if matches(a)]
    total = len(filtered)

    # pagination
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
        regions=REGIONS,
        domains=DOMAINS,
        total=total,
        fmt_datetime=_fmt_datetime
    )

if __name__ == "__main__":
    # local dev
    app.run(host="0.0.0.0", port=5000, debug=True)





