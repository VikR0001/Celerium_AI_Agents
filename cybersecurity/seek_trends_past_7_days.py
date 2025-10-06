import json
import re
import sys
from datetime import timedelta
from hashlib import md5
from html import escape

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Min
from django.utils import timezone
from json_repair import repair_json

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI
from cybersecurity.models import NewsArticle
from cybersecurity.report_latest_cybersecurity_news import call_chatGPT_api, get_text_message_from_llm_response


def do_analysis_of_how_the_past_7_days_fits_into_the_trends(LLM_TO_USE_WITH_THIS_FUNCTION, trend_analysis_object):
    def badge_key(name: str) -> str:
        """css-safe, normalized key (and class suffix) for a badge name."""
        return re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-') or 'badge'

    SEED_BADGE_COLORS = {
        # Preseed your common ones so they stay consistent
        'new': '#0b69ff',
        'escalation': '#e11d48',
        'corroborated': '#16a34a',
        'ransomware': '#b00020',
        'identity': '#a8660e',
        'alleged': '#6b7280',
        'state': '#0f766e',
        'insider': '#8b5cf6',
        'supply': '#2563eb',
        'third': '#0ea5e9',
        'vuln': '#b45309',
        'social': '#059669',
        'arrest': '#7c3aed',
    }

    # A broad, accessible palette (no specific order needed)
    PALETTE = [
        "#7c3aed", "#0ea5e9", "#16a34a", "#e11d48", "#0b69ff",
        "#f97316", "#14b8a6", "#a855f7", "#f59e0b", "#ef4444",
        "#22c55e", "#3b82f6", "#06b6d4", "#10b981", "#8b5cf6",
        "#f43f5e", "#a3e635", "#84cc16", "#eab308", "#fb7185",
        "#38bdf8", "#34d399", "#f87171", "#60a5fa", "#f472b6",
    ]

    def deterministic_pick_color(key: str, used_colors: set) -> str:
        """Pick a palette color deterministically for a given key, skipping ones already used."""
        # Hash the key to get a stable index into the palette
        h = int(md5(key.encode("utf-8")).hexdigest(), 16)
        for i in range(len(PALETTE)):
            color = PALETTE[(h + i) % len(PALETTE)]
            if color not in used_colors:
                return color
        # Fallback: if all used, just return a hashed palette index (will repeat)
        return PALETTE[h % len(PALETTE)]

    def collect_all_badges(data) -> set:
        """Traverse the report dict and collect all badge names.
        Supports key_findings as either:
          - list of {key, items: [bullet,...]} (new), or
          - dict[str, [bullet,...]] (legacy).
        """
        names = set()

        def from_items(items):
            if not isinstance(items, list):
                return
            for b in items[:6]:
                badges = b.get("badges")
                if not isinstance(badges, list):
                    continue
                for n in badges[:6]:
                    if isinstance(n, str):
                        n = n.strip()
                        if n:
                            names.add(n)

        # Fixed sections
        for section in ("intro", "exec_summary", "observations", "glossary", "methodology"):
            from_items(data.get(section))

        # key_findings: new shape = list of groups; legacy shape = dict of lists
        kf = data.get("key_findings")
        if isinstance(kf, list):
            # schema allows up to ~20 groups; cap defensively
            for group in kf[:20]:
                if isinstance(group, dict):
                    from_items(group.get("items"))
        elif isinstance(kf, dict):
            for items in kf.values():
                from_items(items)

        return names


    def build_badge_color_map(all_badge_names: set, seed_map=None) -> dict:
        """Return {normalized_key: hex_color} for all badges, extending seeds for new ones."""
        seed_map = dict(seed_map or {})
        # Track colors already taken so we avoid dupes where possible
        used = set(seed_map.values())
        color_map = dict(seed_map)

        for original in sorted(all_badge_names):  # sorted for determinism across runs
            key = badge_key(original)
            if key not in color_map:
                color = deterministic_pick_color(key, used)
                color_map[key] = color
                used.add(color)
        return color_map

    def render_badge_css(color_map: dict) -> str:
        """Create .badge-{key} css classes from color map."""
        rules = []
        for key, color in color_map.items():
            rules.append(f".badge-{key}{{background:{color};}}")
        return "\n".join(rules)

    # ---------- Your existing funcs (modified) ----------

    def split_even(items):
        n = min(len(items or []), 6)
        left_count = (n + 1) // 2
        return (items or [])[:left_count], (items or [])[left_count:n]

    def render_li(b):
        t = escape(b["text"])
        badges = "".join(
            # aria-label keeps the original text; class uses normalized key
            (lambda _name, _key: f'<span class="badge badge-{_key}" aria-label="{escape(_name)}">{escape(_name)}</span>')(
                name, badge_key(name)
            )
            for name in (b.get("badges") or [])[:6]
        )
        return f"<li>{t}{badges}</li>"

    def render_links(links):
        links = (links or [])[:6]
        return "".join(f'<li><a href="{escape(l["url"])}">{escape(l["title"])}</a></li>' for l in links)

    def render_grid_and_mso(items):
        items = (items or [])[:6]
        ul = "".join(render_li(b) for b in items)
        left, right = split_even(items)
        left_ul  = "".join(render_li(b) for b in left)
        right_ul = "".join(render_li(b) for b in right)
        return (
            f'<ul class="grid-list">{ul}</ul>\n'
            '<!--[if mso]>\n'
            '<table class="grid-table" role="presentation"><tr>'
            f'<td><ul>{left_ul}</ul></td>'
            f'<td><ul>{right_ul}</ul></td>'
            '</tr></table>\n<![endif]-->'
        )

    def render_key_findings(kf_obj):
        """Render key findings.
        Supports:
          - New shape: list[ { "key": str, "items": [bullet,...] }, ... ]
          - Legacy shape: dict[str, list[bullet]]
        """
        parts = []
        if not kf_obj:
            return ""

        def render_one(title, items):
            title = "" if title is None else str(title)
            if title.strip():
                parts.append(f'<h3 class="muted">{escape(title)}</h3>')
            # schema caps at 6; slice defensively
            render_items = items if isinstance(items, list) else []
            parts.append(render_grid_and_mso(render_items[:6]))

        if isinstance(kf_obj, list):
            # Preserve given order; ignore malformed entries
            for group in kf_obj[:20]:  # defensive cap
                if isinstance(group, dict):
                    render_one(group.get("key"), group.get("items"))
        elif isinstance(kf_obj, dict):
            # Legacy dict: {title: items}
            for title, items in kf_obj.items():
                render_one(title, items)

        return "".join(parts)





    def _count(arr):
        return min(len(arr or []), 6)

    def render_html(data):
        # 1) Build a color map that includes all badges we will render
        all_badge_names = collect_all_badges(data)
        color_map = build_badge_color_map(all_badge_names, SEED_BADGE_COLORS)

        # 2) Generate CSS for badges we discovered
        dynamic_badge_css = render_badge_css(color_map)

        subtitle = escape(data.get("subtitle", "[YOUR SUBTITLE HERE]"))
        sources_and_dates = escape(data.get("sources_and_dates", "[YOUR SOURCES AND DATES HERE]"))

        intro_html = render_grid_and_mso(data.get("intro"))
        exec_html  = render_grid_and_mso(data.get("exec_summary"))
        obs_html   = render_grid_and_mso(data.get("observations"))
        glo_html   = render_grid_and_mso(data.get("glossary"))
        met_html   = render_grid_and_mso(data.get("methodology"))
        kf_html    = render_key_findings(data.get("key_findings"))

        s_intro = render_links(data.get("sources_intro"))
        s_exec  = render_links(data.get("sources_exec"))
        s_obs   = render_links(data.get("sources_observations"))

        counts_comment = (
            f"intro={_count(data.get('intro'))}; "
            f"exec_summary={_count(data.get('exec_summary'))}; "
            f"observations={_count(data.get('observations'))}; "
            f"glossary={_count(data.get('glossary'))}; "
            f"methodology={_count(data.get('methodology'))}"
        )

        intro_take = escape(data.get('intro_takeaway','[YOUR TAKEAWAY]'))
        intro_why  = escape(data.get('intro_why','[YOUR EXPLANATION]'))
        exec_take  = escape(data.get('exec_takeaway','[YOUR TAKEAWAY]'))
        exec_why   = escape(data.get('exec_why','[YOUR EXPLANATION]'))
        obs_take   = escape(data.get('observations_takeaway', data.get('obs_takeaway','[YOUR TAKEAWAY]')))
        obs_why    = escape(data.get('observations_why', data.get('obs_why','[YOUR EXPLANATION]')))
        meth_take  = escape(data.get('meth_takeaway','[YOUR TAKEAWAY]'))
        meth_why   = escape(data.get('meth_why','[YOUR EXPLANATION]'))
        key_findings_take = escape(data.get('kf_takeaway','[YOUR EXPLANATION]'))
        key_findings_why = escape(data.get('kf_why','[YOUR EXPLANATION]'))

        # NOTE: we keep your original base CSS but remove the hard-coded per-badge
        # classes—our dynamic_badge_css below will cover them all (including seeded ones).
        return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>Cyber Breach Trend Insights: 7-Day vs 30-Day</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root {{
        --bg:#ffffff;
        --text:#111111;
        --muted:#555555;
        --card:#f7f7f8;
        --border1:#2a7ade;
        --border2:#e4572e;
        --border3:#2e9e51;
        --border4:#a23db5;
      }}
      html,body{{background:var(--bg);color:var(--text);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,"Helvetica Neue",Arial,sans-serif;margin:0;padding:0}}
      header{{max-width:1100px;margin:24px auto 8px;padding:0 16px}}
      h1{{font-size:1.75rem;margin:0 0 6px 0}}
      .subtitle{{color:var(--muted);margin:0 0 6px 0}}
      .sources{{color:var(--muted);font-size:.95rem}}
      main{{max-width:1100px;margin:0 auto;padding:8px 16px 64px}}
      .card{{background:var(--card);border-radius:10px;padding:18px 18px 16px 18px;margin:18px 0;border-left:6px solid var(--border1)}}
      .b2{{border-left-color:var(--border2)}}
      .b3{{border-left-color:var(--border3)}}
      .b4{{border-left-color:var(--border4)}}
      h2{{font-size:1.35rem;margin:0 0 10px 0}}
      .takeaway{{font-weight:700;margin:6px 0 10px 0}}
      .muted{{color:var(--muted)}}
      ul{{margin:8px 0 0 0;padding-left:18px}}
      li{{margin:4px 0}}
      .grid-list{{display:grid;grid-template-columns:1fr;gap:6px 24px;list-style:disc inside}}
      @media (min-width:860px){{ .grid-list{{grid-template-columns:1fr 1fr}} }}
      .grid-table{{width:100%;border-collapse:collapse;margin:8px 0 0 0}}
      .grid-table td{{width:50%;padding:0 12px 0 0;vertical-align:top}}
      .grid-table ul{{margin:0;padding-left:18px;list-style:disc}}
      .grid-table li{{margin:4px 0}}
      a{{color:#0b57d0;text-decoration:none}}
      a:focus, a:hover{{text-decoration:underline}}
    
      /* Base badge */
      .badge{{display:inline-block;margin-left:6px;padding:.1rem .45rem;border-radius:999px;font-size:.75rem;color:#fff;background:#222;vertical-align:baseline}}
      .badge[aria-label]{{outline:none}}
    
      /* Dynamically generated per-badge colors */
      {dynamic_badge_css}
    </style>
    
    <!--[if mso]>
    <style type="text/css">
      .grid-list {{ display: none !important; }}
      .grid-table {{ display: table !important; }}
      .badge {{ display: inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 12px; font-size: 11px; color: #ffffff; background-color: #222222; }}
      /* Duplicate dynamic colors for Outlook */
      {dynamic_badge_css}
    </style>
    <![endif]-->
    </head>
    <body>
    <header>
      <h1>Cyber Breach Trend Insights: 7-Day vs 30-Day</h1>
      <p class="subtitle">{subtitle}</p>
      <p class="sources">{sources_and_dates}</p>
    </header>
    
    <main>
      <section class="card b1">
        <h2>1) Introduction</h2>
        <p class="takeaway">{intro_take}</p>
        <p><strong>Why it matters:</strong> {intro_why}</p>
        {intro_html}
        <div class="src-list">
          <p class="kv"><strong>Evidence &amp; sources:</strong></p>
          <ul>{s_intro}</ul>
        </div>
      </section>
    
      <section class="card b2">
        <h2>2) Executive Summary</h2>
        <p class="takeaway">{exec_take}</p>
        <p><strong>Why it matters:</strong> {exec_why}</p>
        {exec_html}
        <div class="src-list">
          <p class="kv"><strong>Evidence &amp; sources:</strong></p>
          <ul>{s_exec}</ul>
        </div>
      </section>
    
      <section class="card b3">
        <h2>3) Key Findings</h2>
        <p class="takeaway">{key_findings_take}</p>
        <p><strong>Why it matters:</strong> {key_findings_why}</p>
        {kf_html}
      </section>
    
      <section class="card b4">
        <h2>4) Observations (carryovers, ongoing trends)</h2>
        <p class="takeaway">{obs_take}</p>
        <p><strong>Why it matters:</strong> {obs_why}</p>
        {obs_html}
        <div class="src-list"><p class="kv"><strong>Evidence &amp; sources:</strong></p>
          <ul>{s_obs}</ul></div>
      </section>
    
      <section class="card b1">
        <h2>5) Glossary</h2>
        <p class="takeaway">Plain terms used in this report.</p>
        <p><strong>Why it matters:</strong> Simple definitions reduce confusion and help skim quickly.</p>
        {glo_html}
      </section>
    
      <section class="card b2">
        <h2>6) Methodology / Notes</h2>
        <p class="takeaway">{meth_take}</p>
        <p><strong>Why it matters:</strong> {meth_why}</p>
        {met_html}
      </section>
    </main>
    
    <!-- BULLET_COUNTS: {counts_comment} -->
    </body></html>
    """


    articles_from_past_7_days = NewsArticle.objects.filter(
        publish_date__gte=timezone.now() - timedelta(days=7)
    ).values('story_cluster_id').annotate(
        earliest_date=Min('publish_date')
    ).values(
        'id',
        'title',
        'summary',
        'url',
        'publish_date',
        'number_of_records_breached',
        'names_of_threat_actors',
    ).order_by('publish_date')

    articles_from_past_7_days = json.dumps(list(articles_from_past_7_days), cls=DjangoJSONEncoder, indent=2)

    prompt_to_find_trends = f"""
        You will be provided with:
        - TREND_ANALYSIS (json of past 30 days breach patterns)
        - LATEST_ARTICLES (json of past 7 days breach articles; fields include: title, url, summary, publish_date, number_of_records_breached, names_of_threat_actors)
        
        TREND_ANALYSIS:
        {trend_analysis_object}
        
        LATEST_ARTICLES:
        {articles_from_past_7_days}
        
        Tasks:
        1) Generate candidate bullets per section and for key findings subsections you deem relevant (e.g., “Ransomware operators”, “Sectors under pressure”, “Initial access vectors”, etc.). Each bullet: {{text, optional badges[≤6], optional score}}.
        2) Score and rank per the system scoring rules.
        3) Keep only top 6 per list. If overflow, merge related items first; re-score/re-rank; then cap at 6.
        4) Produce TAKEAWAYS and EXPLANATIONS ("why it matters") as follows:
           - One section-level pair for Key Findings: fields `kf_takeaway` and `kf_why` (1–2 sentences each).
           - Optionally, for each key finding group, include `takeaway` and `why` (each 1 sentence) that summarize that group.
        5) Populate the JSON fields exactly as defined by the schema (no extra keys). If a list has no strong items, return an empty array for that list.
        6) Return ONLY the JSON object that conforms to the schema enforced by the API.

        """

    JSON_SCHEMA_FOR_RESPONSE = {
        "name": "trend_bullets",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "subtitle": {"type": "string", "nullable": True},
                "sources_and_dates": {"type": "string", "nullable": True},

                "intro":        {"type": "array", "items": {"$ref": "#/definitions/bullet"}, "maxItems": 6},
                "exec_summary": {"type": "array", "items": {"$ref": "#/definitions/bullet"}, "maxItems": 6},
                "observations": {"type": "array", "items": {"$ref": "#/definitions/bullet"}, "maxItems": 6},
                "glossary":     {"type": "array", "items": {"$ref": "#/definitions/bullet"}, "maxItems": 6},
                "methodology":  {"type": "array", "items": {"$ref": "#/definitions/bullet"}, "maxItems": 6},

                # Section-level takeaways/explanations for ALL sections
                "intro_takeaway": {"type": "string", "nullable": True},
                "intro_why":      {"type": "string", "nullable": True},
                "exec_takeaway":  {"type": "string", "nullable": True},
                "exec_why":       {"type": "string", "nullable": True},
                "obs_takeaway":   {"type": "string", "nullable": True},
                "obs_why":        {"type": "string", "nullable": True},
                "gloss_takeaway": {"type": "string", "nullable": True},
                "gloss_why":      {"type": "string", "nullable": True},
                "meth_takeaway":  {"type": "string", "nullable": True},
                "meth_why":       {"type": "string", "nullable": True},

                # Key Findings: section-level pair
                "kf_takeaway": {"type": "string", "nullable": True},
                "kf_why":      {"type": "string", "nullable": True},

                # Key Findings groups (per-group takeaway/why now required but nullable)
                "key_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "key": {"type": "string"},
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/bullet"},
                                "maxItems": 6
                            },
                            "takeaway": {"type": "string", "nullable": True},
                            "why":      {"type": "string", "nullable": True}
                        },
                        "required": ["key", "items", "takeaway", "why"]
                    },
                    "maxItems": 20,
                    "nullable": True
                },

                "sources_intro":        {"type": "array", "items": {"$ref": "#/definitions/link"}, "maxItems": 6, "nullable": True},
                "sources_exec":         {"type": "array", "items": {"$ref": "#/definitions/link"}, "maxItems": 6, "nullable": True},
                "sources_observations": {"type": "array", "items": {"$ref": "#/definitions/link"}, "maxItems": 6, "nullable": True}
            },
            "required": [
                "subtitle",
                "sources_and_dates",

                "intro",
                "exec_summary",
                "observations",
                "glossary",
                "methodology",

                "intro_takeaway",
                "intro_why",
                "exec_takeaway",
                "exec_why",
                "obs_takeaway",
                "obs_why",
                "gloss_takeaway",
                "gloss_why",
                "meth_takeaway",
                "meth_why",

                "kf_takeaway",
                "kf_why",
                "key_findings",

                "sources_intro",
                "sources_exec",
                "sources_observations"
            ],
            "definitions": {
                "bullet": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text":   {"type": "string"},
                        "badges": {"type": "array", "items": {"type": "string"}, "maxItems": 6, "nullable": True},
                        "score":  {"type": "integer", "nullable": True}
                    },
                    "required": ["text", "badges", "score"]
                },
                "link": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "url":   {"type": "string"}
                    },
                    "required": ["title", "url"]
                }
            }
        }
    }







    system_message = """You are a Cybersecurity Trend Analysis AI Agent.
        Follow these steps:
        1) Generate candidate bullets, score them (+3 new vs baseline, +2 escalation, +1 corroboration, +1 actionability).
        2) Sort by score desc, then recency desc.
        3) Keep only top 6 per list (schema will cap you).
        4) If more feel essential, merge briefly into single items before returning.
        Return ONLY the JSON per schema; do NOT include HTML.
        """

    response_as_text = None
    filename = f"how-past-7-days_fit_into_trends-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
    try:
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, 'r', encoding='utf-8') as file:
            response_as_text = file.read()
    except FileNotFoundError:
        if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI:
            response = call_chatGPT_api(prompt_to_find_trends, system_message = system_message, response_format={
                "type": "json_schema",
                "json_schema": JSON_SCHEMA_FOR_RESPONSE
            })
            response_as_text = get_text_message_from_llm_response(LLM_TO_USE_WITH_THIS_FUNCTION, response)
            file_path = settings.BASE_DIR / 'output' / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(repair_json(response_as_text))
        else:
            print('do_analysis_of_how_the_past_7_days_fits_into_the_trends - error')
            sys.exit(100)

    response_as_json = json.loads(repair_json(response_as_text))
    html_report = render_html(response_as_json)

    filename = f"how-past-7-days_fit_into_trends-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.html"
    file_path = settings.BASE_DIR / 'output' / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_report)

    return html_report;
