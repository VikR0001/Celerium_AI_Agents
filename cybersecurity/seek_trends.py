from django.db.models import Min
from json_repair import repair_json

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI
from cybersecurity.models import NewsArticle
import json
from django.core.serializers.json import DjangoJSONEncoder
import os
from django.conf import settings
from cybersecurity.report_latest_cybersecurity_news import call_google_gemini_api, call_chatGPT_api, \
    get_text_message_from_llm_response


def seek_trends():
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

    prompt = f"""
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
                "supporting_links": [A few supporting links from the ANALYSIS_DATA, including a title and url in json format]
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
                "supporting_links": [A few supporting links from the ANALYSIS_DATA, including a title and url in json format]
              }}
            }}
          ],
          "notable_insights": [
            {{
              "insight": "<key insight description>",
              "implications": "<potential business/security implications>",
              "recommendation": "<actionable recommendation based on trend>"
                "supporting_links": [A few supporting links from the ANALYSIS_DATA, including a title and url in json format]
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
        
        Here is the data for you to analyze, which we are calling  ANALYSIS_DATA in this prompt:
        {articles_json}
    """

    GET_NEW_JSON_VIA_AGENT = False

    if GET_NEW_JSON_VIA_AGENT:
        response = call_chatGPT_api(prompt)
        html_report_json_cleaned = get_text_message_from_llm_response(CHAT_GPT_OPEN_AI, response)
        html_report_json_cleaned = repair_json(html_report_json_cleaned)

        file_path = settings.BASE_DIR / 'output' / 'seek_trends_raw_jason.json'
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_report_json_cleaned)
    else:
        file_path = settings.BASE_DIR / 'output' / 'seek_trends_raw_jason.json'
        with open(file_path, 'r', encoding='utf-8') as file:
            html_report_json_cleaned = file.read()

    html_report_prompt = f"""
        You are converting structured data into an EMAIL-SAFE HTML document.
        
        INPUT (JSON):
        ```json
        {html_report_json_cleaned}```
        
        TASK:
        Convert the JSON above into a single, self-contained HTML document that can be pasted directly into an email compose window (works in Outlook, Gmail, Apple Mail).
        
        STRICT REQUIREMENTS:
        
        Do not add, change, summarize, or omit any information. Preserve field names, values, order, and numeric/string formatting exactly.
        
        No commentary or explanations—return only the HTML.
        
        No external assets, <script>, <video>, or <form> tags.
        
        All CSS must be INLINE on elements (assume <style> tags may be stripped by email clients).
        
        Use a centered, responsive container (max width 640px).
        
        Use semantic structure where possible, but prefer TABLES for any tabular/array data (email-client safe). Use lists/paragraphs for simple key/value content.
        
        Escape all HTML special characters from the data.
        
        Convert URLs in values to clickable links. Email addresses should use mailto: links. Preserve original text as the link text unless it is excessively long (>80 chars), in which case truncate visually with ellipsis while keeping the full href.
        
        Preserve line breaks in long text fields (use white-space: pre-wrap).
        
        Include accessible attributes (e.g., role="table", scope="col", <th> for headers). Provide alt text if you render any image URLs (but prefer links over images).
        
        Ensure good contrast and readable defaults; avoid dark-mode inversion issues.
        
        LAYOUT & STYLE (INLINE on each element):
        
        Root wrapper: <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0;padding:24px;background:#f6f8fa;">
        
        Inner container (centered): <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="width:100%;max-width:640px;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;">
        
        Header: Title derived from top-level object key or "Report"
        
        Content sections for each top-level key
        
        Global inline styles to apply wherever relevant:
        
        font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        
        color: #111827; line-height: 1.5; font-size: 14px;
        
        Headings: margin: 0 0 8px; font-weight: 700; color: #111827;
        
        Section wrappers: padding: 20px 24px; border-top: 1px solid #f0f2f5; (omit the border for the first section)
        
        Key/value lists (non-tabular): use a two-column table to align labels and values; label cells bold with width ~30%.
        
        Data tables: role="table"; border-collapse: collapse; width: 100%;
        
        <th>: font-weight: 700; text-align: left; border-bottom: 1px solid #e5e7eb; padding: 10px 8px; background: #f9fafb;
        <td>: border-bottom: 1px solid #f3f4f6; padding: 10px 8px; vertical-align: top;
        Zebra rows: alternate row background #fcfcfd;
        
        Code/JSON fragments (if any): <pre> with font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background:#f6f8fa; padding:12px; border:1px solid #e5e7eb; border-radius:8px; white-space: pre-wrap; word-wrap: break-word;
        
        MAPPING RULES:
        
        If the value is:
        
        A primitive (string/number/bool): render in a two-column key/value layout.
        
        A flat object: render as a key/value table.
        
        An array of objects with consistent keys: render a data table (headers from keys) in object key order.
        
        An array of primitives: render as a bulleted list.
        
        Nested objects/arrays: create nested sections with <h2>/<h3> headings reflecting the key path (e.g., "Section › Subsection").
        
        Keep the original key names as labels (title-case for display only; don’t alter acronyms like ID, URL).
        
        For dates/times/numbers: DO NOT reformat—display exactly as provided.
        
        For null/empty: display “—” (em dash) to make empties visible, but do not claim a value.
        
        ACCESSIBILITY & ROBUSTNESS:
        
        Provide table headers with scope="col"; add aria-labels where helpful.
        
        Ensure links have discernible text; long URLs may be shortened visually but not in href.
        
        Avoid background-only color indicators (no meaning should rely solely on color).
        
        OUTPUT:
        Return a single complete HTML document starting with <!doctype html> and including <html>, <body>, and the table-based wrapper structure described. No extra prose.        
        
        
    """

    system_message_to_make_sure_we_get_html_back = (
        "You convert arbitrary JSON into structured, email-safe HTML with inline CSS. "
        "You MUST parse and traverse the JSON and render sections/tables/lists as instructed. "
        "NEVER output the raw JSON or wrap the entire JSON in <pre>. "
        "Only use <pre> for individual values explicitly named code-like (e.g., 'code', 'stack_trace', 'log'). "
        "Return ONLY raw HTML. The very first characters must be: <!doctype html>"
    )
    html_report_response = call_chatGPT_api(prompt, system_message=system_message_to_make_sure_we_get_html_back)
    html_report_html = get_text_message_from_llm_response(CHAT_GPT_OPEN_AI, html_report_response)


    file_path = settings.BASE_DIR / 'output' / 'seek_trends_html_report.html'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_report_html)

    pass