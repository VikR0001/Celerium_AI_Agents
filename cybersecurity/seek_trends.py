from django.db.models import Min

from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI
from cybersecurity.models import NewsArticle
import json
from django.core.serializers.json import DjangoJSONEncoder
import os
from django.conf import settings
from cybersecurity.report_latest_cybersecurity_news import call_google_gemini_api, call_chatGPT_api, \
    get_text_message_from_llm_response
from json_repair import repair_json

def seek_trends():
    articles = NewsArticle.objects.values('story_cluster_id').annotate(
        earliest_date=Min('publish_date')
    ).values(
        'id',
        'title',
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
        - `publish_date`: When the article was published (datetime format)
        - `number_of_records_breached`: Number of records compromised (may be null/empty)
        - `names_of_threat_actors`: Known threat actors involved (may be null/empty)
        
        ## ANALYSIS FRAMEWORK
        
        ### PHASE 1: Individual Field Trends Over Time
        Analyze each field independently for temporal patterns:
        
        1. **Title Trends Analysis:**
           - Extract organization names/types from titles (e.g., healthcare, financial, government, retail)
           - Identify industry sectors being targeted over time
           - Look for recurring keywords, attack types mentioned in headlines
           - Track geographic patterns (if location mentioned in titles)
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
        6. **Attack Method + Industry:** If attack types are mentioned in titles, correlate with industries
        
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
              }}
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
              }}
            }}
          ],
          "notable_insights": [
            {{
              "insight": "<key insight description>",
              "implications": "<potential business/security implications>",
              "recommendation": "<actionable recommendation based on trend>"
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
        
        Here is the data for you to analyze:
        
        {articles_json}
    """

    response = call_chatGPT_api(prompt)
    response_message_text = get_text_message_from_llm_response(CHAT_GPT_OPEN_AI, response)
    trend_json = repair_json(response_message_text)

    file_path = settings.BASE_DIR / 'output' / 'seek_trends_raw_jason.json'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(trend_json, indent=2))


    html_report_prompt = f"""
        You are an Executive Cybersecurity Report Generator AI Agent. 
        Your task is to convert technical trend analysis data into a professional, executive-level HTML report that provides clear insights and actionable recommendations for decision-makers
        who are not cyber-security experts.  Theey 
        
        ## INPUT DATA
        You will receive a JSON object containing cybersecurity breach trend analysis with the following structure:
            - analysis_summary: Basic statistics and metadata
        - individual_field_trends: Trends found in individual data fields
        - combination_trends: Multi-field correlation patterns
        - notable_insights: Key discoveries from the analysis
        - data_quality_notes: Limitations and data quality observations
        
        ## REPORT REQUIREMENTS
        
        ### TARGET AUDIENCE
        - C-suite executives (CEO, CISO, CTO)
        - Security managers and directors
        - Risk management professionals
        - Board members with cybersecurity oversight
        
        ### WRITING STYLE GUIDELINES
        - **Executive-friendly language**: Avoid technical jargon, use business terms
        - **Action-oriented**: Focus on "what this means" and "what to do about it"
        - **Quantified insights**: Include specific numbers, percentages, and timeframes
        - **Risk-focused**: Emphasize business impact and security implications
        - **Scannable format**: Use headers, bullet points, and visual hierarchy
        - **Concise but comprehensive**: Thorough analysis in digestible chunks
        
        ## HTML STRUCTURE REQUIREMENTS
        
        Create a complete HTML document with the following sections:
        
        ### 1. EXECUTIVE SUMMARY (300-400 words)
        - **Overview**: Brief description of the analysis scope and timeframe
        - **Key statistics**: Total articles analyzed, date range, most significant numbers
        - **Top 3 critical findings**: Most important trends that require immediate attention
        - **Bottom line**: Single paragraph summarizing the overall threat landscape and urgency level
        
        ### 2. KEY FINDINGS (Organized by priority)
        For each significant finding:
        - **Clear headline**: What the trend is in plain English
        - **Business impact**: Why this matters to the organization
        - **Supporting evidence**: Specific data points and examples
        - **Trend direction**: Is this getting better, worse, or stable?
        - **Timeframe**: When this trend was observed
        
        Organize findings by:
        - **CRITICAL** (red): Immediate threats requiring urgent action
        - **IMPORTANT** (orange): Significant trends requiring attention
        - **NOTABLE** (yellow): Emerging patterns to monitor
        
        ### 3. RECOMMENDATIONS (Actionable and prioritized)
        For each recommendation:
        - **Action item**: Specific step to take
        - **Timeline**: When to implement (immediate/30 days/90 days)
        - **Responsible party**: Who should lead this initiative
        - **Expected outcome**: What this will accomplish
        - **Resource requirements**: High-level estimate of effort/cost
        
        ### 4. INDUSTRY & THREAT ACTOR INTELLIGENCE
        - **Most targeted industries**: Which sectors are at highest risk
        - **Emerging threat actors**: New or increasingly active groups
        - **Attack trends**: Common methods and their evolution
        - **Geographic patterns**: Regional targeting preferences
        
        ### 5. DATA INSIGHTS & METHODOLOGY
        - **Analysis period**: Date range and scope
        - **Data quality**: Limitations and confidence levels
        - **Methodology notes**: How trends were identified
        - **Recommendations for data improvement**: If applicable
        
        ## HTML FORMATTING REQUIREMENTS
        ```html
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Cybersecurity Threat Trends Analysis Report</title>
        <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        line-height: 1.6;
        margin: 0;
        padding: 20px;
        background-color: #f5f5f5;
        color: #333;
        }}
        .container {{
            max-width: 1000px;
        margin: 0 auto;
        background: white;
        padding: 40px;
        border-radius: 10px;
        box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
        border-bottom: 3px solid #2c3e50;
        padding-bottom: 20px;
        margin-bottom: 30px;
        }}
        .report-title {{
                           color: #2c3e50;
                               font-size: 2.2em;
        margin-bottom: 10px;
        font-weight: 300;
        }}
        .report-subtitle {{
                              color: #7f8c8d;
                                  font-size: 1.1em;
        margin-bottom: 5px;
        }}
        .date-range {{
                         color: #95a5a6;
                             font-size: 0.9em;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section-title {{
                            color: #2c3e50;
                                font-size: 1.8em;
        border-left: 5px solid #3498db;
        padding-left: 15px;
        margin-bottom: 20px;
        }}
        .executive-summary {{
                                background: #ecf0f1;
                                    padding: 25px;
        border-radius: 8px;
        border-left: 5px solid #3498db;
        }}
        .finding {{
            margin-bottom: 25px;
        padding: 20px;
        border-radius: 8px;
        border-left: 5px solid;
        }}
        .finding.critical {{
                               background: #fdf2f2;
                                   border-left-color: #e74c3c;
                           }}
        .finding.important {{
                                background: #fef9e7;
                                    border-left-color: #f39c12;
                            }}
        .finding.notable {{
                              background: #fffacd;
                                  border-left-color: #f1c40f;
                          }}
        .finding-title {{
            font-size: 1.3em;
        font-weight: 600;
        margin-bottom: 10px;
        color: #2c3e50;
        }}
        .finding-impact {{
            font-weight: 500;
        margin-bottom: 8px;
        color: #8e44ad;
        }}
        .recommendation {{
                             background: #e8f6f3;
                                 padding: 20px;
        margin-bottom: 20px;
        border-radius: 8px;
        border-left: 5px solid #27ae60;
        }}
        .rec-title {{
            font-size: 1.2em;
        font-weight: 600;
        color: #27ae60;
        margin-bottom: 10px;
        }}
        .priority-high {{ background: #fdf2f2; border-left-color: #e74c3c; }}
                        .priority-medium {{ background: #fef9e7; border-left-color: #f39c12; }}
                                          .priority-low {{ background: #eafaf1; border-left-color: #27ae60; }}
                                                         .stats-grid {{
            display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin: 20px 0;
        }}
        .stat-box {{
                       background: #34495e;
                           color: white;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
        }}
        .stat-number {{
            font-size: 2.5em;
        font-weight: 300;
        display: block;
        }}
        .stat-label {{
            font-size: 0.9em;
        opacity: 0.8;
        }}
        .timeline {{
                       background: #f8f9fa;
                           padding: 15px;
        border-radius: 5px;
        font-weight: 500;
        }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 8px; }}
        .highlight {{ background: #fff3cd; padding: 2px 6px; border-radius: 3px; }}
                    </style>
                   </head>
                     <body>
                     <!-- Your generated content here -->
        </body>
          </html>
            CONTENT GENERATION GUIDELINES
        Executive Summary Best Practices:
        
        Start with the big picture and narrow down to specifics
        Use quantified statements: "X% increase in attacks targeting Y industry"
        Include comparative context: "highest level seen since..." or "represents a X% change from..."
        End with a clear call-to-action or priority focus area
        
        Key Findings Presentation:
        
            Lead with business impact, then provide technical details
        Use trend indicators: ↑ ↓ → for visual quick reference
        Include specific examples with anonymized organization types
        Group related findings together for better comprehension
        
        Recommendations Structure:
        
            Prioritize by risk level and implementation feasibility
        Include both immediate actions and long-term strategic initiatives
        Provide clear success metrics where possible
        Consider resource constraints and realistic timelines
        
        Data Visualization in Text:
        
        Convert percentages to relatable comparisons
        Use phrases like "nearly doubled", "more than half", "one in four"
        Include context for what constitutes "normal" vs "concerning" levels
        Highlight both positive and negative trends for balanced perspective
        
        QUALITY STANDARDS
        
        Accuracy: All claims must be supported by the provided data
        Clarity: Complex concepts explained in business terms
        Completeness: Address all significant trends from the input data
        Actionability: Every insight should lead to a clear recommendation
        Professional presentation: Clean, scannable, executive-appropriate formatting
        
        Generate a complete, professional HTML report that transforms the technical analysis into strategic intelligence for cybersecurity decision-makers.
            
        Here is the data for you to analyze:
        
        {trend_json}
    """

    html_report_response = call_chatGPT_api(html_report_prompt)
    response_message_text = get_text_message_from_llm_response(CHAT_GPT_OPEN_AI, html_report_response)

    file_path = settings.BASE_DIR / 'output' / 'seek_trends_html_report.json'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(response_message_text, indent=2))

    pass