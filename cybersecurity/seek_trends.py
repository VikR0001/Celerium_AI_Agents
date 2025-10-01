from django.db.models import Min
from json_repair import repair_json

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI, GEMINI_GOOGLE
from cybersecurity.models import NewsArticle
import json
from django.core.serializers.json import DjangoJSONEncoder
import os
from django.conf import settings
from cybersecurity.report_latest_cybersecurity_news import call_google_gemini_api, call_chatGPT_api, \
    get_text_message_from_llm_response
from django.utils import timezone
from datetime import timedelta

def do_analysis_of_how_the_past_7_days_fits_into_the_trends(LLM_TO_USE_WITH_THIS_FUNCTION, trend_analysis_object):
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
        You are a Cybersecurity Trend Analysis AI Agent.
        
        You will be provided with:
        - TREND_ANALYSIS (json of past 30 days breach patterns)
        - LATEST_ARTICLES (json of past 7 days breach articles, with fields: title, url, summary, publish_date, number_of_records_breached, names_of_threat_actors)
        
        Here is the TREND_ANALYSIS object:
        {trend_analysis_object}
        
        Here is the LATEST_ARTICLES object:
        {articles_from_past_7_days}  
        
        YOUR JOB
        Compare LATEST_ARTICLES against TREND_ANALYSIS. Identify new or sharper patterns not seen previously.
        
        ABSOLUTE LIST-LENGTH RULES (HARD CAPS — DO NOT VIOLATE)
        - For EVERY bullet list (any <ul> that holds bullets for a section or subsection), the total number of <li> items MUST be ≤ 6, across BOTH columns combined.
        - When an Outlook two-column fallback is required, you MUST split those ≤ 6 items across the two <td> columns as evenly as possible (e.g., 3 & 3 if there are 6; 3 & 2 if 5; 2 & 2 if 4; etc.). Never exceed 3 in either column when the cap is 6.
        - Where the template says “LIMIT OF 6 LINKS,” include ≤ 6 <li> links. Where no limit is stated, prefer ≤ 6 for consistency.
        - BADGE LIMIT: Use ≤ 6 distinct badge types per section (not per bullet). If more badges are relevant, pick the most important ones and drop the rest.
        
        HOW TO ENFORCE THE CAPS (DO THIS BEFORE YOU WRITE HTML)
        1) Generate a candidate list of bullets for each section/subsection.
        2) Score each candidate (higher is better) using:
           - Net-new vs 30-day baseline (new actor/TTP/sector) = +3
           - Material escalation (impact, speed-to-ransom, arrests, macro disruption) = +2
           - Cross-source corroboration or official disclosure = +1
           - Clarity/actionability for CISOs (controls, risk framing) = +1
        3) Sort candidates by score (desc), then by recency (desc).
        4) KEEP ONLY THE TOP 6. If more than 6 still feel essential, MERGE adjacent related items into a single bullet (use concise clauses) and re-apply the cap.
        5) For Outlook versions, split the final ≤ 6 items into two columns as evenly as possible; never replicate or add items beyond those ≤ 6.
        
        SELF-CHECK BEFORE FINAL OUTPUT (REQUIRED)
        - After drafting the HTML but BEFORE returning it, count each bullet list:
          - If any <ul> intended for bullets contains > 6 <li>, REDUCE by dropping the lowest-scored items until count ≤ 6.
          - If any Outlook fallback column would exceed its share (e.g., > 3 when total is 6), rebalance.
        - Add a single HTML comment at the very end confirming counts, like:
          <!-- BULLET_COUNTS: intro=6; exec_summary=6; key_findings_A=5; key_findings_B=4; observations=6; glossary=6; methodology=6 -->
        
        OUTPUT
        Return a complete, self-contained HTML page using THE EXACT TEMPLATE STRUCTURE AND CSS PROVIDED BELOW.
        
        **CRITICAL: You must use this exact HTML structure and CSS. Do not modify the styles, layout, or structure. Only replace the content within the sections.**
        
        **IMPORTANT: For each two-column list, you MUST provide BOTH versions:**
        1) The `<ul class="grid-list">` version for modern browsers
        2) The `<!--[if mso]>` table version for Outlook — manually split your bullets across the two `<td>` cells per the caps above
        
        **BADGE LIMIT: Use a maximum of 6 different badge types per section. Choose the most important/relevant badges only.**
        
        ### REQUIRED HTML TEMPLATE STRUCTURE:
        ```html
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Cyber Breach Trend Insights: 7-Day vs 30-Day</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          :root{{
            --bg:#ffffff;
            --text:#111111;
            --muted:#555555;
            --card:#f7f7f8;
            --border1:#2a7ade;
            --border2:#e4572e;
            --border3:#2e9e51;
            --border4:#a23db5;
            --badge:#222;
            --badge-bg:#eaecef;
            --badge-new:#0b69ff;
            --badge-ransom:#b00020;
            --badge-identity:#a8660e;
            --badge-alleged:#6b7280;
            --badge-state:#0f766e;
            --badge-insider:#8b5cf6;
            --badge-supply:#2563eb;
            --badge-third:#0ea5e9;
            --badge-vuln:#b45309;
            --badge-social:#059669;
            --badge-arrest:#7c3aed;
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
          .badge{{display:inline-block;margin-left:6px;padding:.1rem .45rem;border-radius:999px;font-size:.75rem;color:#fff;background:#222;vertical-align:baseline}}
          .badge[aria-label]{{outline:none}}
          .badge-new{{background:#0b69ff}}
          .badge-ransomware{{background:#b00020}}
          .badge-identity{{background:#a8660e}}
          .badge-alleged{{background:#6b7280}}
          .badge-state{{background:#0f766e}}
          .badge-insider{{background:#8b5cf6}}
          .badge-supply{{background:#2563eb}}
          .badge-third{{background:#0ea5e9}}
          .badge-vuln{{background:#b45309}}
          .badge-social{{background:#059669}}
          .badge-arrest{{background:#7c3aed}}
          .src-list a{{word-break:break-word}}
          .kv{{margin:2px 0}}
          h3.muted{{color:var(--muted);font-size:1.1rem;margin:16px 0 8px 0}}
          @media print{{
            @page{{margin:14mm}}
            header{{page-break-after:always}}
            h2{{page-break-before:always}}
            .card{{break-inside:avoid}}
            a[href]:after{{content:" (" attr(href) ")";color:#000}}
            .footer{{position:fixed;bottom:0;left:0;right:0;font-size:10pt;color:#000}}
            body{{counter-reset:page}}
            .pageno:after{{counter-increment:page;content:counter(page)}}
          }}
          .footer{{position:fixed;bottom:0;left:0;right:0;padding:8px 16px;color:var(--muted);background:linear-gradient(180deg, rgba(255,255,255,0), rgba(255,255,255,.9));font-size:.9rem}}
        </style>
        <!--[if mso]>
        <style type="text/css">
          .grid-list {{ display: none !important; }}
          .grid-table {{ display: table !important; }}
          .badge {{ display: inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 12px; font-size: 11px; color: #ffffff; background-color: #222222; }}
          .badge-new {{ background-color: #0b69ff; }}
          .badge-ransomware {{ background-color: #b00020; }}
          .badge-identity {{ background-color: #a8660e; }}
          .badge-alleged {{ background-color: #6b7280; }}
          .badge-state {{ background-color: #0f766e; }}
          .badge-insider {{ background-color: #8b5cf6; }}
          .badge-supply {{ background-color: #2563eb; }}
          .badge-third {{ background-color: #0ea5e9; }}
          .badge-vuln {{ background-color: #b45309; }}
          .badge-social {{ background-color: #059669; }}
          .badge-arrest {{ background-color: #7c3aed; }}
        </style>
        <![endif]-->
        </head>
        <body>
        <header>
          <h1>Cyber Breach Trend Insights: 7-Day vs 30-Day</h1>
          <p class="subtitle">[YOUR SUBTITLE HERE]</p>
          <p class="sources">[YOUR SOURCES AND DATES HERE]</p>
        </header>
        
        <main>
          <!-- Section 1: Introduction -->
          <section class="card b1">
            <h2>1) Introduction</h2>
            <p class="takeaway">[YOUR TAKEAWAY]</p>
            <p><strong>Why it matters:</strong> [YOUR EXPLANATION]</p>
            <!-- Modern browsers -->
            <ul class="grid-list">
              [YOUR BULLETS WITH BADGES — TOTAL ≤ 6 ITEMS]
            </ul>
            <!--[if mso]>
            <table class="grid-table" role="presentation"><tr>
              <td><ul>[YOUR BULLETS — FIRST HALF (≤ 3 ITEMS)]</ul></td>
              <td><ul>[YOUR BULLETS — SECOND HALF (≤ 3 ITEMS)]</ul></td>
            </tr></table>
            <![endif]-->
            <div class="src-list">
              <p class="kv"><strong>Evidence &amp; sources:</strong></p>
              <ul>[YOUR SOURCES WITH LINKS — ≤ 6 LINKS]</ul>
            </div>
          </section>
        
          <!-- Section 2: Executive Summary -->
          <section class="card b2">
            <h2>2) Executive Summary</h2>
            <p class="takeaway">[YOUR TAKEAWAY]</p>
            <p><strong>Why it matters:</strong> [YOUR EXPLANATION]</p>
            <ul class="grid-list">[YOUR BULLETS — TOTAL ≤ 6 ITEMS]</ul>
            <!--[if mso]-->
            <table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table>
            <!--[endif]-->
            <div class="src-list">
              <p class="kv"><strong>Evidence &amp; sources:</strong></p>
              <ul>[YOUR SOURCES WITH LINKS — ≤ 6 LINKS]</ul>
            </div>
          </section>
        
          <!-- Section 3: Key Findings -->
          <section class="card b3">
            <h2>3) Key Findings</h2>
            <p class="takeaway">[YOUR TAKEAWAY]</p>
            <p><strong>Why it matters:</strong> [YOUR EXPLANATION]</p>
        
            <h3 class="muted">[SUBSECTION A TITLE]</h3>
            <ul class="grid-list">[BULLETS — TOTAL ≤ 6]</ul>
            <!--[if mso]--><table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table><!--[endif]-->
            <div class="src-list"><p class="kv"><strong>Evidence &amp; sources:</strong></p>
              <ul>[LINKS — ≤ 6]</ul></div>
        
            <h3 class="muted">[SUBSECTION B TITLE]</h3>
            <ul class="grid-list">[BULLETS — TOTAL ≤ 6]</ul>
            <!--[if mso]--><table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table><!--[endif]-->
            <div class="src-list"><p class="kv"><strong>Evidence &amp; sources:</strong></p>
              <ul>[LINKS — ≤ 6]</ul></div>
        
            [REPEAT FOR C, D, E, F, G AS NEEDED — EACH SUBSECTION MUST OBEY THE ≤ 6 BULLET RULE]
          </section>
        
          <!-- Section 4: Observations -->
          <section class="card b4">
            <h2>4) Observations (carryovers, ongoing trends)</h2>
            <p class="takeaway">[YOUR TAKEAWAY]</p>
            <p><strong>Why it matters:</strong> [YOUR EXPLANATION]</p>
            <ul class="grid-list">[BULLETS — TOTAL ≤ 6]</ul>
            <!--[if mso]--><table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table><!--[endif]-->
            <div class="src-list"><p class="kv"><strong>Evidence &amp; sources:</strong></p>
              <ul>[LINKS — ≤ 6]</ul></div>
          </section>
        
          <!-- Section 5: Glossary -->
          <section class="card b1">
            <h2>5) Glossary</h2>
            <p class="takeaway">Plain terms used in this report.</p>
            <p><strong>Why it matters:</strong> Simple definitions reduce confusion and help skim quickly.</p>
            <ul class="grid-list">[YOUR DEFINITIONS — TOTAL ≤ 6 ITEMS]</ul>
            <!--[if mso]--><table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table><!--[endif]-->
          </section>
        
          <!-- Section 6: Methodology -->
          <section class="card b2">
            <h2>6) Methodology / Notes</h2>
            <p class="takeaway">[YOUR TAKEAWAY]</p>
            <p><strong>Why it matters:</strong> [YOUR EXPLANATION]</p>
            <ul class="grid-list">[BULLETS — TOTAL ≤ 6]</ul>
            <!--[if mso]--><table class="grid-table" role="presentation"><tr>
              <td><ul>[FIRST HALF — ≤ 3]</ul></td>
              <td><ul>[SECOND HALF — ≤ 3]</ul></td>
            </tr></table><!--[endif]-->
            <div class="src-list">
              <p class="kv"><strong>Baseline reference:</strong> [YOUR REFERENCE]</p>
            </div>
          </
        """
    if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI:
        response = call_chatGPT_api(prompt_to_find_trends)
    elif LLM_TO_USE_WITH_THIS_FUNCTION == GEMINI_GOOGLE:
        response = call_google_gemini_api(prompt_to_find_trends, model = 'gemini-2.5-pro')
    else:
        breakpoint()

    html_report = get_text_message_from_llm_response(LLM_TO_USE_WITH_THIS_FUNCTION, response)

    filename = f"how-past-7-days_fit_into_trends-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.html"
    file_path = settings.BASE_DIR / 'output' / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_report)

    return html_report;

def do_analysis_of_past_4_weeks(LLM_TO_USE_WITH_THIS_FUNCTION):
    articles = NewsArticle.objects.values('story_cluster_id').annotate(
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
        
        ### PHASE 1: Individual Field Trends Over Time
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
        breakpoint()

    html_report_json_cleaned = get_text_message_from_llm_response(LLM_TO_USE_WITH_THIS_FUNCTION, response)
    html_report_json_cleaned = repair_json(html_report_json_cleaned)

    filename = f"seek_trends_raw_json-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
    file_path = settings.BASE_DIR / 'output' / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_report_json_cleaned)

    return html_report_json_cleaned;

def seek_trends(llm_to_use=CHAT_GPT_OPEN_AI, days=30, category= ''):
    LLM_TO_USE_WITH_THIS_FUNCTION = llm_to_use #Can be CHAT_GPT_OPEN_AI or GEMINI_GOOGLE
    PERFORM_NEW_ANALYSIS_OF_PAST_30_DAYS = False
    OUTPUT_NEW_HTML_REPORT_FOR_PAST_30_DAYS = False

    if PERFORM_NEW_ANALYSIS_OF_PAST_30_DAYS:
        html_report_json_cleaned = do_analysis_of_past_4_weeks(LLM_TO_USE_WITH_THIS_FUNCTION)
    else:
        filename = f"seek_trends_raw_json-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, 'r', encoding='utf-8') as file:
            html_report_json_cleaned = file.read()

    if OUTPUT_NEW_HTML_REPORT_FOR_PAST_30_DAYS:
        prompt_to_format_report_as_html = f"""
            You will receive JSON data below. Your task is to:
            1. Parse and understand the data structure
            2. Extract the key information 
            3. Present it as a clean, professional HTML report (not raw JSON)
            4. Use proper HTML formatting with headings, paragraphs, bullet points, etc.
            5. Include inline CSS for professional email styling
            
            JSON data:
            {html_report_json_cleaned}
    
            The report should be easy for non-experts to read and understand. It should use some color and also bullet points so as to be easy for non-experts to understand.
            
            It should have these sections:
            - Introduction
            - Executive Summary
            - Key Findings
            - Summary of Findings
        """

        html_report_response = None
        if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI:
            html_report_response = call_chatGPT_api(prompt_to_format_report_as_html)
        elif LLM_TO_USE_WITH_THIS_FUNCTION == GEMINI_GOOGLE:
            html_report_response = call_google_gemini_api(prompt_to_format_report_as_html, model = 'gemini-2.5-pro')
        else:
            breakpoint()

        html_report_html = get_text_message_from_llm_response(LLM_TO_USE_WITH_THIS_FUNCTION, html_report_response)

        filename = f"seek_trends_html_report-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.html"
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_report_html)

    past_7_days_trends_html = do_analysis_of_how_the_past_7_days_fits_into_the_trends(LLM_TO_USE_WITH_THIS_FUNCTION, html_report_json_cleaned)

    pass