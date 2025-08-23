"""
Cybersecurity Breach News AI Agent
This agent searches for cybersecurity breach news from today and sends email alerts.
"""
import os
import re
from google import genai
from google.genai import types
import os
from PIL import Image
import requests
from io import BytesIO
from django.conf import settings
import requests
import json
from datetime import datetime, date, time
from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass
from enum import Enum
from newspaper import Article

total_cost = 0

AI_MODEL_ALL = 'sonar-pro'
AI_MODEL_GET_NEWS = 'sonar-reasoning-pro'

class NewsItem:
    """Data class to store news item information"""
    title: str
    url: str
    source: str
    summary: str
    published_date: str
    full_text_of_article: str
    number_of_records_breached: str
    names_of_threat_actors: str


def call_gemini_api(prompt, model_specifier = ''):
    global total_cost

    GOOGLE_GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY')
    client = genai.Client(api_key=GOOGLE_GEMINI_API_KEY)

    # Define the grounding tool
    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    # Configure generation settings to use the tool
    config = types.GenerateContentConfig(
        tools=[grounding_tool]
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents= prompt,
        config=config,
    )

    try:
        # Costs per 1 million tokens for gemini-2.5-flash
        INPUT_COST_PER_M_TOKENS = 0.30  # USD [1]
        OUTPUT_COST_PER_M_TOKENS = 2.50  # USD [1]

        # Cost per 1000 requests for Grounding with Google Search
        GROUNDING_COST_PER_K_REQUESTS = 35.00  # USD [1]

        # free for up to 1500 requests per day, so it's free to us
        GROUNDING_COST_PER_K_REQUESTS = 0

        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

        # Check if grounding was used by looking for the `grounding_metadata` field.
        # The `web_search_queries` array lists the searches performed by the model.[3]
        if hasattr(response.candidates, 'grounding_metadata'):
            search_queries_count = len(response.candidates.grounding_metadata.web_search_queries)
        else:
            search_queries_count = 0

        # --- Step 4: Calculate the total cost ---

        # Calculate token costs
        input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_M_TOKENS
        output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_M_TOKENS

        # Calculate grounding cost (this is only billed after the free tier)
        grounding_cost = (search_queries_count / 1_000) * GROUNDING_COST_PER_K_REQUESTS

        cost = input_cost + output_cost + grounding_cost

        total_cost += cost
        print('Total cost so far:', total_cost)
    except Exception as e:
        print("Couldn't get gemini cost: ", e)

    return response

def call_perplexity_api(prompt: str, model: str):
    global total_cost

    """Call Perplexity API"""
    API_URL = "https://api.perplexity.ai/chat/completions"
    PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(API_URL, headers=headers, json=data)
    result = None
    try:
        result = response.json()
    except Exception as e:
        print('call_perplexity_api: ', e, 'status code: ', response.status_code)
        if response.status_code == 401:
            print('Need to top off perplexity account funds')
        breakpoint()

    try:
        input_tokens = result['usage']['prompt_tokens']
        output_tokens = result['usage']['completion_tokens']
        total_tokens = result['usage']['total_tokens']
        cost = (input_tokens / 1_000_000) * 3 + (output_tokens / 1_000_000) * 15 + 0.005
        total_cost += cost
        print('Total cost so far:', total_cost)
    except Exception as e:
        print("Couldn't get perplexity cost: ", e)

    # Perplexity (March/August 2025), the pricing for the “sonar-pro” model is:
    # Input tokens: $3 per 1M tokens
    # Output tokens: $15 per 1M tokens
    # Each API request: $5 per 1,000 requests (i.e., $0.005 per request)

    return result

import os
import requests # Make sure you have this import at the top of your file

def link_returns_status_200(url):
    result = False
    try:
        # via gemini:
        # Q: I've got a url that when I put it in the browser, it loads just fine. But when I test it like this, I get a 403 response. How can that be?
        #    response = requests.get(url)
        #
        # A: That discrepancy occurs because your browser and the requests library send different information in their web requests. Websites often use this information to distinguish between human users and automated scripts.
        # A 403 Forbidden error means the server understood your request but is refusing to authorize it. In this case, the website's anti-bot or security measures likely detected your Python script and blocked it, while your browser request was seen as legitimate.

        #gemini recommends trying these headers:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
        }

        # Add headers to the GET request
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            result = True
    except Exception as e:
        pass;

    return result


def confirm_article_url(article, today_str):

    # some of these vertex article_urls resolve to the real article
    if 'vertex' in article['url']:
        final_url = requests.head(article['url'], allow_redirects=True).url
        article['url'] = final_url

    final_url = article['url']
    if link_returns_status_200(final_url):
        article['url'] = final_url
        return article

    # and, some only resolve to a 404
    # let's try to look up the correct url

    prompt = f"""
        Find the url from today, {today_str}, that talks about this:
        
        {article['summary']}
        
        Return data about one single url. The published data for the url must be in this range: ["{today_str} 00:00" to "{today_str} 23:59" UTC].

        Return the results as a JSON array. Include:
        
        - title
        - url
        - source
        - summary
        - published_date
        - full_text_of_article
        - number_of_records_breached (if unknown, put "unknown")
        - names_of_threat_actors (if unknown, put "unknown")
    """

    retry_count = 0
    MAX_RETRY_ATTEMPTS = 5
    got_our_data = False
    while not got_our_data and retry_count < MAX_RETRY_ATTEMPTS:
        python_object = call_perplexity_api(prompt, AI_MODEL_ALL)
        try:
            if python_object is None:
                continue
            article_string = python_object["choices"][0]["message"]["content"]
            clean_json = article_string.strip().removeprefix('```json').removesuffix('```').strip()
            article_new =json.loads(clean_json)

            #confirm url is not a 404
            try:
                url = article_new["url"]
            except Exception as e:
                url =  article_new[0]['url']

            if link_returns_status_200(url):
                got_our_data = True
        except Exception as e:
            print('confirm_article_url: ', e)
            retry_count += 1
            got_our_data = False

    return article_new[0]


    # I tried doing it this way but a lot of the time it gave me a wrong url
    # e.g. something from the wrong date, or a link to a site in chines
    # api_key = os.getenv('GOOGLE_CUSTOM_SEARCH_API_KEY')
    # search_engine_id = os.getenv('GOOGLE_CUSTOM_API_SEARCH_ENGINE_ID')
    #
    # api_url = "https://www.googleapis.com/customsearch/v1"
    # params = {
    #     'key': api_key,
    #     'cx': search_engine_id,
    #     'q': article_summary,
    #     'num': 5
    # }
    #
    # try: # Begin try block for error handling
    #     response = requests.get(api_url, params=params)
    #     response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
    #     results = response.json()
    #
    #     if 'items' in results:
    #         # First, try to find a non-Facebook link
    #         non_facebook_link = None
    #         for item in results['items']:
    #             if 'facebook.com' not in item['link'].lower():  # Using .lower() for case-insensitive check
    #                 print(f"Title: {item['title']}")
    #                 print(f"URL: {item['link']}")
    #                 print("---")
    #                 non_facebook_link = item['link']
    #                 break  # Return the first non-Facebook link found
    #
    #         if non_facebook_link:
    #             return non_facebook_link  # Return the non-Facebook link if found
    #
    #         # If no non-Facebook link found, return the first Facebook link (if any)
    #         if results['items']:  # Ensure 'items' isn't empty before accessing
    #             facebook_link = results['items'][0]['link']
    #             print(f"Title: {results['items'][0]['title']}")
    #             print(f"URL: {facebook_link}")
    #             print("---")
    #             return facebook_link
    # except Exception as e:
    #     print(f"confirm_article_url: {e}")  # e.g., 400, 404, 500

    return None  # Return None if no links found in the results or an error occurred

def extract_reasoning_and_json(text):
    """
    Extracts content inside <think>...</think> to 'reasoning',
    and first JSON array inside triple backticks (``````) to 'response_object'.
    """
    # Extract everything inside <think>...</think>
    reasoning_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else None

    # Extract the JSON block between ``````
    pattern = r'```json\s*(.*?)(?:```|$)'
    match = re.search(pattern, text, re.DOTALL)
    response_object = json.loads(match.group(1).strip()) if match else None

    return reasoning, response_object


# Configure logging to track agent decisions
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BreachCategory(Enum):
    HOSPITAL = "hospital"
    MEDICAL = "medical"
    BUSINESS = "business"

class SeverityLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class BreachIncident:
    title: str
    breach_category: BreachCategory
    severity: SeverityLevel
    affected_count: int
    source: str
    url: str
    summary: str
    publish_date: str
    ai_reasoning: str
    full_text_of_article: str
    number_of_records_breached: str
    names_of_threat_actors: str

class LLMClient:
    """
    Interface for LLM API calls - replace with your preferred LLM service
    (OpenAI, Anthropic, local models, etc.)
    """

    def __init__(self, api_key: str = None, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
        # In real implementation, initialize your LLM client here
        # self.client = openai.OpenAI(api_key=api_key)

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Make LLM API call - replace with actual API integration
        """
        # MOCK RESPONSE - Replace with real LLM API call
        # Example: response = self.client.chat.completions.create(...)

        # For demo purposes, returning realistic mock responses
        if "categorize this cybersecurity incident" in prompt.lower():
            return """
            Category: HOSPITAL
            Reasoning: This incident involves a healthcare system with patient data (PHI) and medical records, which directly affects hospital operations and patient privacy. The mention of "Healthcare System" and "2.3M Patients" clearly indicates this is a hospital-level incident requiring immediate attention from healthcare cybersecurity professionals.
            """
        elif "assess the severity" in prompt.lower():
            return """
            Severity: HIGH
            Affected Count: 2300000
            Reasoning: This is a high-severity incident due to the massive scale (2.3M affected individuals), the sensitive nature of healthcare data (PHI, medical records), and the operational impact on patient care. Healthcare data breaches carry additional regulatory and safety implications beyond typical business breaches.
            """
        elif "extract technical details" in prompt.lower():
            return """
            Technical Details:
            - Attack vector: Ransomware deployment via compromised third-party vendor credentials
            - Threat actor: RansomHub ransomware group (preliminary attribution based on TTPs)
            - Data types compromised: PHI, SSNs, medical records, billing information
            - Systems affected: Primary EHR platform and patient portal
            - Impact duration: Systems offline for 72+ hours affecting patient care operations
            - Recovery status: Partial systems restoration in progress
            """
        else:
            return "Mock LLM response - replace with actual API integration"

    def parse_structured_response(self, response: str, expected_fields: List[str]) -> Dict[str, str]:
        """Parse LLM response for structured data"""
        parsed = {}
        lines = response.strip().split('\n')

        for line in lines:
            for field in expected_fields:
                if line.strip().startswith(f"{field}:"):
                    parsed[field.lower()] = line.split(':', 1)[1].strip()

        if 'reasoning' in [field.lower() for field in expected_fields]:
            reasoning_index = response.find('Reasoning:')
            if reasoning_index != -1:
                # Get everything after "Reasoning:" and strip leading/trailing whitespace
                reasoning_text = response[reasoning_index + len('Reasoning:'):].strip()
                parsed['reasoning'] = reasoning_text

        return parsed

class TrueAIBreachAgent:
    """
    True AI Agent that uses LLM calls for all decision-making rather than hardcoded rules
    """

    def __init__(self, llm_client: LLMClient, healthcare_focus: bool = True):
        self.llm = llm_client
        self.healthcare_focus = healthcare_focus
        self.decision_log = []
        self.context_memory = []  # Agent maintains context across decisions

    def log_ai_decision(self, decision_type: str, decision_title: str, ai_reasoning: str, outcome: Any = None):
        """Track AI agent's decision-making process"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "title": decision_title,
            "timestamp": timestamp,
            "decision_type": decision_type,
            "ai_reasoning": ai_reasoning,
            "outcome": str(outcome) if outcome else None
        }
        self.decision_log.append(log_entry)
        self.context_memory.append(f"{decision_type}: {ai_reasoning}")
        logging.info(f"AI AGENT DECISION: {decision_type} - {ai_reasoning}")

    def get_news_from_llm(self) -> List[NewsItem]:
        """Get news from Perplexity API"""
        today_str = datetime.now().strftime("%B %d, %Y")

        prompt = f"""Retrieve all unique news stories published today about companies that experienced a cybersecurity breach.
    
                        If there are no news stories today, reply "No news today".
                        
                        Perform a thorough search, reviewing multiple reputable sources to ensure completeness.
                        
                        Do not omit any relevant stories found.
                        
                        Return results as a JSON array. For each story, include:
                        
                        - title
                        - url
                        - source
                        - summary
                        - published_date
                        - full_text_of_article
                        - number_of_records_breached (if unknown, put "unknown")
                        - names_of_threat_actors (if unknown, put "unknown")
                        
                        For multiple news articles about the same breach at the same company, include only the most comprehensive or earliest story in your results.
                        
                        Maximum of 30 unique companies (breaches). List up to one story per company or breach.
                        
                        To ensure consistency across runs:
                        
                        Always use the same date range: ["{today_str} 00:00" to "{today_str} 23:59" UTC].
                        
                        Consistently define a "unique" breach as one where the affected company and incident are distinct.
                        
                        Sort the stories in the same, deterministic way (e.g., alphabetical order by company name or by published time descending).
                        
                        Ensure stories are not omitted due to deduplication.
                        
                        Return only the formatted JSON.
        """

        python_object = call_gemini_api(prompt, AI_MODEL_ALL)

        try:
            # this works for objects returned by perplexity
            articles = python_object["choices"][0]["message"]["content"]
            clean_json = articles.strip().removeprefix('```json').removesuffix('```').strip()
            reasoning, articles_object = extract_reasoning_and_json(clean_json)
        except Exception as e:
            # this works for objects returned by Gemini
            reasoning, articles_object =  extract_reasoning_and_json(python_object.text)
            # google likes to provide vertexaisearch.cloud.google.com urls that redirect to the real url
            # let's get the real url
            for idx, article in enumerate(articles_object):
                url = article['url']
                article_new = confirm_article_url(article, today_str)
                articles_object[idx] = article_new

        self.log_ai_decision("Get News Articles", 'Initial article retrieval', reasoning, None)
        return articles_object

    def ai_categorize_incident(self, search_result: Dict) -> tuple[BreachCategory, str]:
            """
            AI DECISION POINT 2: Let AI analyze and categorize each incident
            """
            article_full_text = search_result['full_text_of_article']

            categorization_prompt = f"""
            You are a cybersecurity analyst specializing in healthcare industry threats.
            
            Analyze and categorize this cybersecurity incident:
            
            FullText: {article_full_text}
            
            Categories to choose from:
            - HOSPITAL: Direct hospital/health system incidents
            - MEDICAL: Other medical/healthcare related (clinics, medical devices, etc.)
            - BUSINESS: Non-healthcare business incidents (but relevant for threat intelligence)
            
            Only assign an article to the HOSPITAL category if the company that was breached is specifically called a hospital in the article. 
            
            For healthcare cybersecurity professionals, consider:
            - PHI/medical data involvement
            - Healthcare infrastructure relevance
            - Regulatory implications (HIPAA, etc.)
            - Direct patient care impact
            
            Respond in this format:
            Category: [HOSPITAL/MEDICAL/BUSINESS]
            Reasoning: [Your detailed analysis of why this categorization is appropriate]
            """

            ai_response_object = call_perplexity_api(categorization_prompt, AI_MODEL_ALL)
            ai_response_message = ai_response_object["choices"][0]["message"]["content"]
            clean_string = ai_response_message.strip().removeprefix('```json').removesuffix('```').strip()

            parsed = self.llm.parse_structured_response(clean_string, ["Category", "Reasoning"])

            category_str = parsed.get("category", "BUSINESS").upper()
            reasoning = parsed.get("reasoning", "AI categorization reasoning not parsed correctly")

            if "medical" in category_str.lower():
                a = 100
            try:
                category = BreachCategory(category_str.replace('*', '').lower())
            except ValueError:
                category = BreachCategory.BUSINESS
                reasoning += f" (Note: AI returned '{category_str}', defaulted to BUSINESS)"

            self.log_ai_decision("Incident Categorization", search_result['title'], reasoning, category.value)
            return category, reasoning

    def ai_assess_severity(self, search_result: Dict, category: BreachCategory) -> tuple[SeverityLevel, int, str]:
        """
        AI DECISION POINT 3: Let AI assess severity with full context
        """
        severity_prompt = f"""
        You are a cybersecurity risk analyst with expertise in healthcare threat assessment.
        
        Previous context and decisions:
        {chr(10).join(self.context_memory[-5:]) if self.context_memory else "None"}
        
        Assess the severity of this cybersecurity incident:
        
        Title: {search_result['title']}
        Content: {search_result['summary']}
        Category: {category.value}
        Source: {search_result['source']}
        
        Consider for severity assessment:
        - Healthcare-specific factors (PHI, HIPAA, patient safety, care disruption)
        - Relevance to hospital cybersecurity
        - Regulatory implications
        - Operational impact
        - Number of people affected (extract from content)
        - Attack sophistication
        - Type of data compromised
        
        Severity levels:
        - HIGH: Major incidents requiring immediate attention
        - MEDIUM: Significant incidents requiring monitoring  
        - LOW: Minor incidents for awareness
        
        Respond in this format:
        Severity: [HIGH/MEDIUM/LOW]
        Affected Count: [number]
        Reasoning: [Your detailed severity analysis considering all factors]
        """

        ai_response_object = call_perplexity_api(severity_prompt, AI_MODEL_ALL)
        ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        clean_string = ai_response_message.strip().removeprefix('```json').removesuffix('```').strip()

        parsed = self.llm.parse_structured_response(clean_string, ["Severity", "Affected Count", "Reasoning"])

        severity_str = parsed.get("severity", "MEDIUM").upper()
        affected_str = parsed.get("affected count", "0")
        reasoning = parsed.get("reasoning", "AI severity assessment reasoning not parsed correctly")

        try:
            severity = SeverityLevel(severity_str.replace('*', '').lower())
        except ValueError:
            severity = SeverityLevel.MEDIUM
            reasoning += f" (Note: AI returned '{severity_str}', defaulted to MEDIUM)"

        # Extract affected count
        try:
            affected_count = int(''.join(filter(str.isdigit, affected_str)))
        except:
            affected_count = 0

        self.log_ai_decision(f"{search_result['title']} Severity Assessment", search_result['title'], reasoning, f"{severity.value}/{affected_count}")
        return severity, affected_count, reasoning

    def ai_extract_technical_details(self, search_result: Dict, category: BreachCategory) -> tuple[List[str], str]:
        """
        AI DECISION POINT 4: Let AI extract relevant technical details for the audience
        """
        detail_extraction_prompt = f"""
        You are a cybersecurity intelligence analyst preparing a briefing for healthcare cybersecurity professionals.
        
        Context from analysis so far:
        {chr(10).join(self.context_memory[-3:]) if self.context_memory else "None"}
        
        Extract the most important technical details from this incident:
        
        Title: {search_result['title']}
        Content: {search_result['summary']}
        Category: {category.value}
        Full Article: {search_result.get('full_content', 'Not available')}
        
        Your audience consists of healthcare cybersecurity professionals who need:
        - Attack vectors and TTPs
        - Technical indicators (CVEs, malware families, etc.)
        - Infrastructure details
        - Impact on healthcare operations
        - Defensive recommendations
        
        Extract 3-5 key technical details that would be most valuable for this audience.
        
        Respond in this format:
        Technical Details:
        - [Detail 1]
        - [Detail 2]
        - [Detail 3]
        - [Detail 4]
        - [Detail 5]
        
        Reasoning: [Why these details are most relevant for healthcare cybersecurity professionals]
        """

        ai_response = self.llm.generate(detail_extraction_prompt)
        reasoning_start = ai_response.find("Reasoning:")

        if reasoning_start != -1:
            details_section = ai_response[:reasoning_start].strip()
            reasoning = ai_response[reasoning_start+10:].strip()
        else:
            details_section = ai_response
            reasoning = "AI extracted technical details based on healthcare cybersecurity relevance"

        # Parse bullet points
        details = []
        for line in details_section.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('•'):
                details.append(line[1:].strip())

        self.log_ai_decision("Technical Detail Extraction", search_result['title'], reasoning, f"{len(details)} details extracted")
        return details, reasoning

    def ai_prioritize_incidents(self, incidents: List[BreachIncident]) -> tuple[List[BreachIncident], str]:
        """
        AI DECISION POINT 5: Let AI determine optimal prioritization strategy
        """
        incident_summaries = []
        for i, incident in enumerate(incidents):
            summary = f"{i+1}. {incident.title} | {incident.breach_category} | {incident.severity} | {incident.number_of_records_breached} records"
            incident_summaries.append(summary)

        prioritization_prompt = f"""
        You are a cybersecurity intelligence analyst organizing a daily threat briefing for healthcare cybersecurity professionals.
        
        Here are today's incidents to prioritize:
        {chr(10).join(incident_summaries)}
        
        Your audience priorities:
        1. Direct threats to hospital/healthcare operations
        2. Incidents with applicable lessons for healthcare security
        3. Emerging threat patterns that could affect healthcare
        
        Determine the optimal order for presenting these incidents. Consider:
        - Incidents with the category HOSPITAL have the highest priority
        - Incidents with the category MEDIAL have the second-highest priority
        - Incidents with the category BUSINESS have the third-highest priority
        - Within each category, prioritize items in order of the following:
        -- Severity and scale of impact  
        -- Urgency of response needed
        
        Provide the optimal order (by incident number) and explain your prioritization reasoning.
        
        Respond in this format:
        Priority Order: [incident numbers in order, e.g., "3, 1, 2"]
        Reasoning: [Your detailed prioritization logic]
        """

        ai_response_object = call_perplexity_api(prioritization_prompt, AI_MODEL_ALL)
        ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        clean_string = ai_response_message.strip().removeprefix('```json').removesuffix('```').strip()
        parsed = self.llm.parse_structured_response(clean_string, ["Priority Order", "Reasoning"])

        priority_order_str = parsed.get("priority order", "1, 2, 3")
        reasoning = parsed.get("reasoning", "AI prioritization reasoning not parsed correctly")

        # Parse the priority order
        try:
            priority_indices = [int(x.strip()) - 1 for x in priority_order_str.split(',')]
            prioritized_incidents = [incidents[i] for i in priority_indices if 0 <= i < len(incidents)]

            # Add any incidents that weren't included
            included_indices = set(priority_indices)
            for i, incident in enumerate(incidents):
                if i not in included_indices:
                    prioritized_incidents.append(incident)

        except (ValueError, IndexError):
            # Fallback if AI response parsing fails
            prioritized_incidents = incidents
            reasoning += " (Note: Used fallback prioritization due to parsing error)"

        self.log_ai_decision("Incident Prioritization", "Prioritize Incidents", reasoning, f"Reordered {len(incidents)} incidents")
        return prioritized_incidents, reasoning

    def ai_generate_email_format(self, incidents: List[BreachIncident]) -> tuple[str, str]:
        """
        AI DECISION POINT 6: Let AI determine optimal presentation format
        """
        incident_data = []
        for incident in incidents:
            incident_data.append({
                "title": incident.title,
                "breach_category": incident.breach_category,
                "affected": incident.affected_count,
                "summary": incident.summary,  # Limit for prompt size
                "source": incident.source,
                "severity": incident.severity,
                "url": incident.url,
                "date": incident.publish_date,
                "names_of_potential_threat_actors": incident.names_of_threat_actors,
                "number_of_records_breached": incident.number_of_records_breached
            })

        format_prompt = f"""
        You are designing an email briefing format for healthcare cybersecurity professionals.
        
        Context: Daily threat intelligence briefing
        Audience: Healthcare CISOs, security analysts, IT directors
        Delivery: HTML email
        
        Here is the title shown in the email:
        Cyber Breaches in the News Today
        
        Put that title in white text on a #3965bc background.
        
        Incident data to present:
        {json.dumps(incident_data, indent=2)}
        
        Design decisions to make:
        - How to make the email look professionally-designed?
        - How should incidents be visually differentiated?
        - What information should be most prominent?
        - What visual hierarchy works best for busy executives?
        
        Provide your formatting strategy and reasoning, then generate the HTML.
        
        Use this color scheme:
        - Primary accent: #3965bc
        
        For breach_category, use these highlight colors:
        - Hospital: white text on green rounded rect
        - Medical:  white text on light green rounded rect
        - Business: white text on #3965bc rounded rect
        
        Make sure to put breach_category on its own separate line
    
        For each article, MAKE SURE TO INCLUDE EACH OF THE FOLLOWING:
        - Title
        - Summary
        - breach_category
        - publish_date
        - severity
        - Clicking the article title should take us to the url of the source
        - Number of records breached (if that is known)
        - Names of the potential threat actors (if that is known)
        - Source
        
        Respond in this format:
        Format Strategy: [Your design reasoning and approach]
        HTML: [Complete HTML email code]
        """

        ai_response_object = call_perplexity_api(format_prompt, AI_MODEL_ALL)
        ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        html_match = re.search(r'HTML:\s*```html\s*(.*?)\s*```', ai_response_message, re.DOTALL)
        if html_match:
            clean_string = html_match.group(1).strip()

        strategy_reasoning = "AI determined optimal visual hierarchy with healthcare-specific iconography and severity color coding for rapid threat assessment by busy cybersecurity professionals."

        self.log_ai_decision("Email Format Generation", "Generate Email Format", strategy_reasoning, f"Generated {len(clean_string)} character HTML")
        return clean_string, strategy_reasoning

    def run_ai_agent(self) -> Dict[str, Any]:
        """
        Execute the complete AI agent workflow where AI makes all decisions
        """
        self.log_ai_decision("AI Agent Initialization", "Starting true AI-driven cybersecurity breach analysis for healthcare industry", "STARTED")

        # AI Decision Pipeline - each step uses LLM calls
        search_results = self.get_news_from_llm()

        processed_incidents = []
        for result in search_results:
            # Let AI make all the decisions for each incident
            category, cat_reasoning = self.ai_categorize_incident(result)
            severity, affected_count, sev_reasoning = self.ai_assess_severity(result, category)
            # details, det_reasoning = self.ai_extract_technical_details(result, category)

            incident = BreachIncident(
                title=result["title"],
                breach_category=category.name,
                severity=severity.name,
                affected_count=affected_count,
                source=result["source"],
                url=result["url"],
                summary=result["summary"],
                full_text_of_article = result["full_text_of_article"],
                number_of_records_breached = result["number_of_records_breached"],
                names_of_threat_actors = result["names_of_threat_actors"],
                publish_date= '',
                ai_reasoning = ''
            )

            processed_incidents.append(incident)

        # Let AI prioritize the incidents
        prioritized_incidents, prioritization_reasoning = self.ai_prioritize_incidents(processed_incidents)

        # Let AI generate the email format
        email_html, format_reasoning = self.ai_generate_email_format(prioritized_incidents)

        # Final AI summary
        summary_prompt = f"""
        Summarize the AI agent's performance in this cybersecurity intelligence gathering session. 
        For each value of 'title', and within that for each value of 'decision_type', summarize the 'ai_reasoning'
        
        Here is the data to be summarized: {json.dumps(self.decision_log, indent=2)}
        
        Provide the results in html format with a nice report format.
        """

        ai_response_object = call_perplexity_api(summary_prompt, AI_MODEL_ALL)
        ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        self.log_ai_decision("Final AI Summary", 'Wrap-Up', ai_response_message, "COMPLETED")

        return {
            "summary_of_ai_decisions": ai_response_message,
            "incidents_found": len(search_results),
            "incidents_processed": prioritized_incidents,
            "email_html": email_html,
            "decision_log": self.decision_log,
            "ai_summary": '',
            "total_ai_decisions": len(self.decision_log)
        }

def startAI_Agent():
    global total_cost

    # Initialize LLM client (replace with real API integration)
    llm_client = LLMClient(api_key="your-api-key-here", model="gpt-4")

    # Initialize the TRUE AI agent
    ai_agent = TrueAIBreachAgent(llm_client, healthcare_focus=True)

    print("🤖 Starting TRUE AI Cybersecurity Breach Agent...")
    print("🧠 All decisions will be made by AI, not hardcoded rules")
    print("=" * 70)

    results = ai_agent.run_ai_agent()

    # Display results
    print(f"\n📊 AI AGENT RESULTS:")
    print(f"Incidents found: {results['incidents_found']}")
    print(f"AI decisions made: {results['total_ai_decisions']}")
    print(f"AI summary: {results['ai_summary']}")

    file_path = settings.BASE_DIR / 'output' / 'reasoning.html'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('AI Agent Reasoning')

    file_path = settings.BASE_DIR / 'output' / 'summary_of_ai_decisions.html'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(results['summary_of_ai_decisions'])

    print(f"\n📧 AI-GENERATED EMAIL HTML:")
    print("HTML email ready for delivery (length:", len(results['email_html']), "characters)")

    # Save HTML to file
    file_path = settings.BASE_DIR / 'output' / 'ai_breach_report.html'
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(results['email_html'])
    print("✅ AI-generated HTML report saved to 'ai_breach_report.html'")

    print(f"\n🎯 KEY DIFFERENCE:")
    print("This agent uses LLM API calls for EVERY decision, not hardcoded Python logic!")
    print("Each categorization, severity assessment, and prioritization is made by AI.")

    print('Total Cost: ', total_cost)