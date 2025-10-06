import re
import json
import sys
from html import escape
from datetime import datetime

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import OuterRef, Min, Subquery
from json_repair import repair_json

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI, GEMINI_GOOGLE
from cybersecurity.models import NewsArticle
from cybersecurity.report_latest_cybersecurity_news import call_chatGPT_api, call_google_gemini_api, \
    get_text_message_from_llm_response


def do_analysis_of_past_4_weeks_get_json(LLM_TO_USE_WITH_THIS_FUNCTION):
    min_dates = NewsArticle.objects.filter(
        story_cluster_id=OuterRef('story_cluster_id')
    ).values(
        'story_cluster_id'
    ).annotate(
        min_date=Min('publish_date')
    ).values('min_date')

    # Filter the main queryset to include only articles
    # whose publish_date matches the min_date for their cluster.
    articles = NewsArticle.objects.filter(
        publish_date=Subquery(min_dates)
    ).values(
        'id',
        'title',
        'summary',
        'url',
        'publish_date',
        'number_of_records_breached',
        'names_of_threat_actors',
    ).order_by('publish_date')
    articles_json = json.dumps(list(articles), cls=DjangoJSONEncoder, indent=2)

    prompt_to_find_trends = f"""
        You are a Cybersecurity Trend Analysis AI Agent. Your task is to analyze news articles about cybersecurity breaches and identify meaningful trends across multiple dimensions.
        
        ## DATA CONTEXT
        You will receive a JSON array of cybersecurity breach articles with the following fields:
        - `title`: Article headline (usually contains the name of the breached organization)
        - 'url' : url of the source article
        - 'summary' : summary of the article
        - `publish_date`: When the article was published (datetime format)
        - `number_of_records_breached`: Number of records compromised (may be null/empty)
        - `names_of_threat_actors`: Known threat actors involved (may be null/empty)
        
        ## ANALYSIS FRAMEWORK
        
        ### PHASE 1: Trends Found Over Time
        Analyze each field independently for temporal patterns:
        
        1. **Title and Summary Trends Analysis:**
           - Extract organization names/types from titles/summaries (e.g., healthcare, financial, government, retail)
           - Identify industry sectors being targeted over time
           - Look for recurring keywords, attack types mentioned in headlines
           - Track geographic patterns (if location mentioned in titles/summaries)
           - Identify seasonal or cyclical patterns in breach announcements
        
        2. **Publication Date Trends:**
           - Identify peak periods of breach reporting
           - Look for seasonal patterns, monthly/quarterly clusters
           - Detect potential reporting delays or disclosure patterns
        
        3. **Records Breached Trends:**
           - Track scale of breaches over time (small vs. large breaches)
           - Identify if breach sizes are increasing/decreasing
           - Look for patterns in breach magnitude by time period
        
        4. **Threat Actor Trends:**
           - Track emergence and activity patterns of specific threat actors
           - Identify periods of increased activity for known groups
           - Look for new threat actors appearing over time
        
        ### PHASE 2: Multi-Field Combination Analysis
        Look for correlations and patterns across field combinations:
        
        1. **Industry + Time Patterns:** Which sectors are targeted during specific periods?
        2. **Threat Actor + Industry:** Which actors target which industries?
        3. **Breach Size + Industry:** Do certain industries experience larger breaches?
        4. **Threat Actor + Breach Size:** Do specific actors tend to cause larger/smaller breaches?
        5. **Geographic + Temporal:** Regional targeting patterns over time
        6. **Attack Method + Industry:** If attack types are mentioned in titles/summries, correlate with industries
        
        ## OUTPUT FORMAT
        Return your analysis as a JSON object with this exact structure:
        ## OUTPUT FORMAT
        Return your analysis as a JSON object with this exact structure:
        ```json
        {{
          "analysis_summary": {{
            "total_articles_analyzed": <number>,
            "date_range": {{
              "earliest": "<date>",
              "latest": "<date>"
            }},
            "analysis_timestamp": "<current_datetime>"
          }},
          "individual_field_trends": [
            {{
              "field": "<field_name>",
              "trend_type": "<temporal/frequency/pattern>",
              "description": "<detailed description of trend>",
              "confidence": "<high/medium/low>",
              "supporting_data": {{
                "key_findings": ["<finding1>", "<finding2>"],
                "time_periods": ["<period1>", "<period2>"],
                "frequency_data": "<relevant counts/percentages>"
                "supporting_links": [Links to all articles from the ANALYSIS_DATA that you reference in your "description" , including a title and url in json format]
              }},
            }}
          ],
          "combination_trends": [
            {{
              "fields_analyzed": ["<field1>", "<field2>"],
              "trend_type": "<correlation/pattern/anomaly>",
              "description": "<detailed description of multi-field trend>",
              "confidence": "<high/medium/low>",
              "supporting_data": {{
                "correlation_strength": "<strong/moderate/weak>",
                "key_examples": ["<example1>", "<example2>"],
                "statistical_significance": "<description>"
                "supporting_links": [Links to all articles from the ANALYSIS_DATA that you reference in your "description" , including a title and url in json format]
              }}
            }}
          ],
          "notable_insights": [
            {{
              "insight": "<key insight description>",
              "implications": "<potential business/security implications>",
              "recommendation": "<actionable recommendation based on trend>"
                "supporting_links": [Links to all articles from the ANALYSIS_DATA that you reference in your "description" , including a title and url in json format]
            }}
          ],
          "data_quality_notes": [
            "<any limitations or data quality issues observed>"
          ]
        }}
    
        
        ANALYSIS GUIDELINES
        
        Look for patterns spanning at least 3 data points to establish trends
        Consider both obvious and subtle patterns
        Pay attention to absence of data (e.g., periods with no breaches reported)
        Be specific about time ranges when describing trends
        Distinguish between correlation and causation
        Assign confidence levels based on data strength and pattern clarity
        Include quantitative support where possible (percentages, counts, ratios)
        Focus on actionable insights that could inform cybersecurity strategy
        
        IMPORTANT NOTES
        
        These are cybersecurity breach articles, so organization names in titles are typically breach victims
        Empty/null fields should be noted but don't ignore articles with missing data
        Look for both increasing and decreasing trends
        Consider external factors that might influence timing (holidays, major events, disclosure requirements)
        Be thorough but concise in your descriptions
        
        Analyze the provided data systematically and return your findings in the specified JSON format.
        
        Here is the data for you to analyze, which we are calling  ANALYSIS_DATA in this prompt_to_find_trends:
        {articles_json}
    """

    if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI:
        response = call_chatGPT_api(prompt_to_find_trends)
    elif LLM_TO_USE_WITH_THIS_FUNCTION == GEMINI_GOOGLE:
        response = call_google_gemini_api(prompt_to_find_trends, model = 'gemini-2.5-pro')
    else:
        print('do_analysis_of_past_4_weeks_get_json - error')
        sys.exit(100)

    html_report_json_cleaned = get_text_message_from_llm_response(LLM_TO_USE_WITH_THIS_FUNCTION, response)
    html_report_json_cleaned = repair_json(html_report_json_cleaned)

    filename = f"seek_trends_raw_json-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
    file_path = settings.BASE_DIR / 'output' / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_report_json_cleaned)

    return html_report_json_cleaned;

def do_analysis_of_past_4_weeks_get_html(json_string):
    def fmt_iso_date(s):
        """Return YYYY-MM-DD from an ISO string, or s if parsing fails."""
        if not s:
            return ""
        try:
            # handle trailing Z
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            return s

    def nonempty(x):
        return x if x else ""

    def clamp_list(items, n=8):
        return list(items or [])[:n]

    def render_kv(label, value):
        if not value:
            return ""
        return f'<p class="kv"><span class="k">{escape(label)}:</span> <span class="v">{escape(str(value))}</span></p>'

    def render_list(items, ordered=False):
        items = clamp_list(items, 10)
        if not items:
            return ""
        tag = "ol" if ordered else "ul"
        lis = "".join(f"<li>{escape(str(i))}</li>" for i in items)
        return f"<{tag}>{lis}</{tag}>"

    def render_links(links, max_items=12):
        links = clamp_list(links, max_items)
        if not links:
            return ""
        lis = []
        for l in links:
            url = escape(l.get("url", "#"))
            title = escape(l.get("title", url))
            lis.append(f'<li><a href="{url}">{title}</a></li>')
        return f"<ul>{''.join(lis)}</ul>"

    # --------------------------
    # Section renderers
    # --------------------------

    def render_analysis_summary(analysis_summary: dict) -> str:
        if not analysis_summary:
            return ""
        total = analysis_summary.get("total_articles_analyzed")
        dr = analysis_summary.get("date_range", {}) or {}
        earliest = fmt_iso_date(dr.get("earliest"))
        latest = fmt_iso_date(dr.get("latest"))
        ts = analysis_summary.get("analysis_timestamp")
        ts_fmt = fmt_iso_date(ts) if ts else ""

        metrics = []
        if total is not None:
            metrics.append(render_kv("Total articles analyzed", total))
        if earliest or latest:
            metrics.append(render_kv("Date range", f"{earliest} → {latest}".strip()))
        if ts_fmt:
            metrics.append(render_kv("Analysis timestamp", ts_fmt))

        return f"""
        <section class="card b1">
          <h2>Analysis Summary</h2>
          {''.join(metrics)}
        </section>
        """

    TREND_TYPE_PLAIN = {
        "temporal": "Changes over time",
        "pattern": "Recurring themes",
        "temporal/pattern": "Recurring time-based pattern",
        "frequency/pattern": "How often things repeat",
        "correlation": "Connections between factors"
    }

    def make_field_and_trend_type_more_readable(field, field_type):
        """
        Returns (pretty_field, plain_trend)
        - field: supports str or list[str]
            * underscores -> spaces
            * Title Case
            * Lists are joined with " + "
        - field_type: mapped to plain English if known
        """
        if isinstance(field, list):
            # Normalize each entry
            parts = [re.sub(r'_+', ' ', (f or '').strip()).title() for f in field if f]
            pretty_field = " + ".join(parts)
        else:
            pretty_field = re.sub(r'_+', ' ', (field or '').strip()).title()

        ft = (field_type or "").lower()
        plain_trend = TREND_TYPE_PLAIN.get(ft, field_type.title())

        return pretty_field, plain_trend


    def render_individual_field_trends(trends: list) -> str:
        if not trends:
            return ""
        cards = []
        for t in clamp_list(trends, 20):
            field = nonempty(t.get("field"))
            trend_type = nonempty(t.get("trend_type"))
            field, trend_type = make_field_and_trend_type_more_readable(field, trend_type)
            desc = nonempty(t.get("description"))
            conf = nonempty(t.get("confidence"))
            sd = t.get("supporting_data") or {}

            # Supporting data blocks (each optional)
            sd_blocks = []
            if sd.get("key_findings"):
                sd_blocks.append(f'<h4>Key Findings</h4>{render_list(sd.get("key_findings"))}')
            if sd.get("time_periods"):
                sd_blocks.append(f'<h4>Key Time Periods</h4>{render_list(sd.get("time_periods"))}')
            if sd.get("frequency_data"):
                sd_blocks.append(f'{render_kv("Frequency / volume", sd.get("frequency_data"))}')
            if sd.get("supporting_links"):
                sd_blocks.append(f'<h4>Sources</h4>{render_links(sd.get("supporting_links"))}')

            subtitle_bits = []
            if field:
                subtitle_bits.append(f'Data analyzed: {field}')
            if trend_type:
                subtitle_bits.append(f"Trend Type: {trend_type}")
            subtitle = ". ".join(subtitle_bits)

            cards.append(f"""
            <article class="card b2">
              <h3>{escape(subtitle) if subtitle else "Trend"}</h3>
              <p class="desc">{escape(desc)}</p>
              {render_kv("Confidence", conf)}
              {''.join(sd_blocks)}
            </article>
            """)
        return f"""
        <section>
          <h2>Trends Found</h2>
          {''.join(cards)}
        </section>
        """

    def render_combination_trends(trends: list) -> str:
        if not trends:
            return ""
        cards = []
        for t in clamp_list(trends, 20):
            fields = t.get("fields_analyzed") or []
            trend_type = nonempty(t.get("trend_type"))
            fields, trend_type = make_field_and_trend_type_more_readable(fields, trend_type)

            desc = nonempty(t.get("description"))
            conf = nonempty(t.get("confidence"))
            sd = t.get("supporting_data") or {}

            header = fields if fields else "Combined Trend"
            header = 'Data examined: ' + header
            subtitle = ". Trend Type: ".join(filter(None, [header, trend_type]))

            sd_blocks = []
            if sd.get("correlation_strength"):
                sd_blocks.append(render_kv("Correlation strength", sd.get("correlation_strength")))
            if sd.get("statistical_significance"):
                sd_blocks.append(render_kv("Statistical significance", sd.get("statistical_significance")))
            if sd.get("key_examples"):
                sd_blocks.append(f'<h4>Key Examples</h4>{render_list(sd.get("key_examples"))}')
            if sd.get("supporting_links"):
                sd_blocks.append(f'<h4>Sources</h4>{render_links(sd.get("supporting_links"))}')

            cards.append(f"""
            <article class="card b3">
              <h3>{escape(subtitle)}</h3>
              <p class="desc">{escape(desc)}</p>
              {render_kv("Confidence", conf)}
              {''.join(sd_blocks)}
            </article>
            """)
        return f"""
        <section>
          <h2>Combination Trends</h2>
          {''.join(cards)}
        </section>
        """

    def render_notable_insights(insights: list) -> str:
        if not insights:
            return ""
        cards = []
        for it in clamp_list(insights, 20):
            insight = nonempty(it.get("insight"))
            implications = nonempty(it.get("implications"))
            recommendation = nonempty(it.get("recommendation"))
            links = it.get("supporting_links") or []
            cards.append(f"""
            <article class="card b4">
              <h3>{escape(insight) if insight else "Insight"}</h3>
              {f'<p class="kv"><span class="k">Implications:</span> <span class="v">{escape(implications)}</span></p>' if implications else ""}
              {f'<p class="kv"><span class="k">Recommendation:</span> <span class="v">{escape(recommendation)}</span></p>' if recommendation else ""}
              {f'<h4>Sources</h4>{render_links(links)}' if links else ""}
            </article>
            """)
        return f"""
        <section>
          <h2>Notable Insights & Recommendations</h2>
          {''.join(cards)}
        </section>
        """

    def render_data_quality_notes(notes: list) -> str:
        if not notes:
            return ""
        return f"""
        <section class="card b1">
          <h2>Data Quality Notes</h2>
          {render_list(notes)}
        </section>
        """

    # --------------------------
    # Main HTML renderer
    # --------------------------

    def render_html(data: dict) -> str:
        """Render the full HTML report from the provided JSON object."""
        analysis_summary = data.get("analysis_summary") or {}
        individual_field_trends = data.get("individual_field_trends") or []
        combination_trends = data.get("combination_trends") or []
        notable_insights = data.get("notable_insights") or []
        data_quality_notes = data.get("data_quality_notes") or []

        # You can customize the title/subtitle here if desired
        page_title = "Breach Landscape Trends Report"
        subtitle = ""
        if analysis_summary:
            dr = analysis_summary.get("date_range") or {}
            earliest = fmt_iso_date(dr.get("earliest"))
            latest = fmt_iso_date(dr.get("latest"))
            if earliest or latest:
                subtitle = f"{earliest} → {latest}"

        return f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8" />
    <title>{escape(page_title)}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        --bg:#ffffff;
        --fg:#0b0b0b;
        --muted:#555;
        --card:#f7f7f8;
        --border1:#1a73e8; /* blue */
        --border2:#ea4335; /* red  */
        --border3:#34a853; /* green */
        --border4:#a142f4; /* purple */
      }}
      html,body {{
        background:var(--bg);
        color:var(--fg);
        font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,"Helvetica Neue",Arial,sans-serif;
        margin:0;padding:0;
      }}
      header{{max-width:1100px;margin:28px auto 8px;padding:0 16px}}
      h1{{font-size:2rem;margin:0 0 6px 0; font-weight:900; letter-spacing:.2px}}
      .subtitle{{color:var(--muted);margin:0 0 6px 0}}
      main{{max-width:1100px;margin:0 auto;padding:8px 16px 64px}}
      section{{margin:18px 0}}
      .card{{background:var(--card);border-radius:12px;padding:18px;margin:18px 0;border-left:8px solid var(--border1)}}
      .b1{{border-left-color:var(--border1)}}
      .b2{{border-left-color:var(--border2)}}
      .b3{{border-left-color:var(--border3)}}
      .b4{{border-left-color:var(--border4)}}
    
      /* Bolder headings per your request */
      h2{{font-size:1.5rem;margin:0 0 10px 0; font-weight:850}}
      h3{{font-size:1.1rem;margin:0 0 8px 0; font-weight:800}}
      h4{{font-size:1rem;margin:10px 0 6px 0; font-weight:750; color:#222}}
    
      .desc{{margin:6px 0}}
      .kv{{margin:6px 0}}
      .kv .k{{font-weight:700; color:#222; margin-right:.25rem}}
      .kv .v{{color:#111}}
      ul,ol{{margin:8px 0 0 0; padding-left:20px}}
      li{{margin:4px 0}}
      a{{color:#0b57d0;text-decoration:none}}
      a:hover,a:focus{{text-decoration:underline}}
    
      /* Small screens */
      @media (max-width:640px){{
        h1{{font-size:1.75rem}}
        h2{{font-size:1.35rem}}
      }}
    
      /* Print tweaks */
      @media print{{
        .card{{break-inside:avoid}}
        a::after{{content:" (" attr(href) ")"; font-size:.85em}}
      }}
    </style>
    </head>
    <body>
    <header>
      <h1>{escape(page_title)}</h1>
      <p class="subtitle">{escape(subtitle)}</p>
    </header>
    
    <main>
      {render_analysis_summary(analysis_summary)}
      {render_individual_field_trends(individual_field_trends)}
      {render_combination_trends(combination_trends)}
      {render_notable_insights(notable_insights)}
      {render_data_quality_notes(data_quality_notes)}
    </main>
    
    </body>
    </html>
    """


    try:
        data = json.loads(json_string)
        past_30_days_report_html = render_html(data)
    except Exception as e:
        print("do_analysis_of_past_4_weeks_get_html: ", e)


    return past_30_days_report_html
