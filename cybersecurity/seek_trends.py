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

def do_analysis_of_past_4_weeks():

def seek_trends(llm_to_use=CHAT_GPT_OPEN_AI, days=30, category= ''):
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

    GET_NEW_JSON_VIA_AGENT = False
    LLM_TO_USE_WITH_THIS_FUNCTION = llm_to_use #Can be CHAT_GPT_OPEN_AI or GEMINI_GOOGLE

    if GET_NEW_JSON_VIA_AGENT:
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
    else:
        filename = f"seek_trends_raw_json-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, 'r', encoding='utf-8') as file:
            html_report_json_cleaned = file.read()

    prompt_to_format_report_as_html = f"""
        You will receive JSON data below. Your task is to:
        1. Parse and understand the data structure
        2. Extract the key information 
        3. Present it as a clean, professional HTML report (not raw JSON)
        4. Use proper HTML formatting with headings, paragraphs, tables, etc.
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

    # system_message_to_make_sure_we_get_html_back = (
    #     "You convert arbitrary JSON into structured, email-safe HTML with inline CSS. "
    #     "You MUST parse and traverse the JSON and render sections/tables/lists as instructed. "
    #     "Return ONLY raw HTML. The very first characters must be: <!doctype html>"
    # )

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

    pass