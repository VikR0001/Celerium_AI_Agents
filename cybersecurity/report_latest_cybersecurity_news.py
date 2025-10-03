"""
Cybersecurity Breach News AI Agent
This agent searches for cybersecurity breach news from today and sends email alerts.
"""
import re

import openai
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
from django.db.models import F, OuterRef, Subquery
from newspaper import Article
from json_repair import repair_json

from cybersecurity.analysis_settings import START_DATE, END_DATE, LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS, CHAT_GPT_OPEN_AI, \
    PERPLEXITY, CLAUDE_ANTHROPIC, GEMINI_GOOGLE
from cybersecurity.embedding_utils import generate_article_embeddings, logger, recluster_all_articles
from cybersecurity.models import NewsArticle

total_cost = 0

OPENAI_API_KEY = os.getenv('CHAT_GPT_OPEN_AI_KEY')

openAI_client = openai.OpenAI(
    api_key=OPENAI_API_KEY
)

class NewsItem:
    """Data class to store news item information"""
    title: str
    url: str
    source: str
    summary: str
    publish_date: str
    full_text_of_article: str
    number_of_records_breached: str
    names_of_threat_actors: str
from dateutil import parser


def regularize_date_format_for_use_in_database(date_input):
    """
    Convert various date formats to ISO-like format: YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ]

    Handles virtually any date format using dateutil parser.
    Examples:
    - "August 23, 2025 00:00 UTC" -> "2025-08-23 00:00:00+00:00"
    - "2025-08-23" -> "2025-08-23 00:00:00"
    - "2025-08-24T14:14:00Z" -> "2025-08-24 14:14:00+00:00"
    - "Aug 24, 2025" -> "2025-08-24 00:00:00"
    - "24/08/2025" -> "2025-08-24 00:00:00"
    - And many more...
    """

    try:
        # Check if the input is already a datetime object
        if isinstance(date_input, datetime):
            parsed_date = date_input
        else:
            # If it's a string, strip whitespace and parse it
            date_string = date_input.strip()
            parsed_date = parser.parse(date_string)

        # Format the datetime object into the desired ISO-like format
        # This handles timezone info if present
        if parsed_date.tzinfo is not None:
            # Has timezone info - include it
            if parsed_date.microsecond > 0:
                # Include microseconds if present
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S.%f%z")
            else:
                # No microseconds
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S%z")
        else:
            # No timezone info
            if parsed_date.microsecond > 0:
                # Include microseconds if present
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                # Standard format without microseconds
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S")

    except (ValueError, parser.ParserError, AttributeError):
        # If parsing fails or the input is not a string or datetime object,
        # return the original value.
        return date_input


def regularize_date_format_for_use_in_html(date_input):
    """
    Convert various date formats to 'Aug 23, 2025' format.

    Handles virtually any date format using dateutil parser.
    Examples:
    - "August 23, 2025 00:00 UTC"
    - "2025-08-23"
    - "2025-08-24T14:14:00Z"
    - "Aug 24, 2025"
    - "24/08/2025"
    - And many more...
    """

    try:
        # Check if the input is already a datetime object
        if isinstance(date_input, datetime):
            parsed_date = date_input
        else:
            # If it's a string, strip whitespace and parse it
            date_string = date_input.strip()
            parsed_date = parser.parse(date_string)

        # Format the datetime object into the desired string format
        return parsed_date.strftime("%b %d, %Y")

    except (ValueError, parser.ParserError, AttributeError):
        # If parsing fails or the input is not a string or datetime object,
        # return the original value.
        return date_input

def get_text_message_from_llm_response(LLM_used, LLM_response):
    if LLM_used == CHAT_GPT_OPEN_AI:
        ai_response_message = LLM_response.choices[0].message.content
    elif LLM_used == PERPLEXITY:
        ai_response_message = LLM_response["choices"][0]["message"]["content"]
    elif LLM_used == CLAUDE_ANTHROPIC:
        ai_response_message = LLM_response.content[0].text
    elif LLM_used == GEMINI_GOOGLE:
        ai_response_message = LLM_response.text;

    return ai_response_message

def call_claude_anthropic_api(prompt):
    import anthropic
    global total_cost
    GOOGLE_GEMINI_API_KEY = os.getenv('CLAUDE_ANTHROPIC_API_KEY')

    def calculate_claude_cost(model, input_tokens, output_tokens, cache_write_tokens=0, cache_read_tokens=0, cache_type="5m"):
        """
        Calculate the cost of a Claude API call based on token usage.

        Args:
            model: Claude model name (e.g., "claude-sonnet-4", "claude-haiku-3.5")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_write_tokens: Number of cache write tokens (optional)
            cache_read_tokens: Number of cache read tokens (optional)
            cache_type: Cache type "5m" or "1h" for cache duration (optional)

        Returns:
            Total cost in USD
        """

        normalized = model.replace('_', '.').split('-')[:-1]  # Remove date part
        model = '-'.join(normalized)

        # Pricing per million tokens (MTok) from Claude docs
        pricing = {
            "claude-opus-4-1": {"input": 15, "output": 75, "cache_5m": 18.75, "cache_1h": 30, "cache_read": 1.50},
            "claude-opus-4": {"input": 15, "output": 75, "cache_5m": 18.75, "cache_1h": 30, "cache_read": 1.50},
            "claude-sonnet-4": {"input": 3, "output": 15, "cache_5m": 3.75, "cache_1h": 6, "cache_read": 0.30},
            "claude-sonnet-3-7": {"input": 3, "output": 15, "cache_5m": 3.75, "cache_1h": 6, "cache_read": 0.30},
            "claude-haiku-3-5": {"input": 0.80, "output": 4, "cache_5m": 1, "cache_1h": 1.6, "cache_read": 0.08},
            "claude-haiku-3": {"input": 0.25, "output": 1.25, "cache_5m": 0.30, "cache_1h": 0.50, "cache_read": 0.03}
        }

        if model not in pricing:
            raise ValueError(f"Model {model} not found in pricing table")

        model_pricing = pricing[model]

        # Calculate costs (convert tokens to millions)
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]

        cache_write_cost = 0
        if cache_write_tokens > 0:
            cache_key = f"cache_{cache_type}"
            if cache_key in model_pricing:
                cache_write_cost = (cache_write_tokens / 1_000_000) * model_pricing[cache_key]

        cache_read_cost = 0
        if cache_read_tokens > 0:
            cache_read_cost = (cache_read_tokens / 1_000_000) * model_pricing["cache_read"]

        total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost
        return total_cost

    model = 'claude-opus-4-1-20250805'

    client = anthropic.Anthropic(  # defaults to os.environ.get("ANTHROPIC_API_KEY")
        api_key=GOOGLE_GEMINI_API_KEY,
    )
    response = client.messages.create(
        model= model,
        max_tokens=2000,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    model_name = response.model

    # Calculate the cost
    cost = calculate_claude_cost(
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )

    total_cost += cost
    print('Total cost so far:', total_cost)

    return response

def call_google_gemini_api(prompt, model = 'gemini-2.5-flash'):
    global total_cost
    model = model

    # Note: Pricing tiers are based on the length of the prompt (in tokens).
    MODEL_PRICES = {
        "gemini-2.5-pro": {
            "short_prompt": {
                "input": 1.25,  # $1.25 per million tokens for prompts <= 200k tokens
                "output": 10.0, # $10.00 per million tokens
            },
            "long_prompt": {
                "input": 2.50,  # $2.50 per million tokens for prompts > 200k tokens
                "output": 15.0, # $15.00 per million tokens
            },
        },
        "gemini-2.5-flash": {
            "input": 0.30,  # $0.30 per million input tokens
            "output": 2.50, # $2.50 per million output tokens
        },
        "gemini-2.5-flash-lite": {
            "input": 0.10,  # $0.10 per million input tokens
            "output": 0.40, # $0.40 per million output tokens
        },
    }

    #https://share.google/aimode/R6xP4VaGOoDciawap
    def estimate_google_gemini_cost(response, model: str) -> float:
        """
        Estimate the dollar cost of a Google Gemini API response.

        Args:
            response: API response object from a Gemini client call.
            model: string, the model name (e.g., "gemini-2.5-pro", "gemini-2.5-flash").

        Returns:
            float: estimated cost in USD
        """

        #google gemini said the tokens would be in response.usage, but
        #I'm seeing them in usage_metadata
        got_token_counts = False
        try:
            usage = response.usage
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            got_token_counts = True
        except Exception as e:
            try:
                #response.usage not found
                #try response usage_metadata
                usage_metadata = response.usage_metadata
                input_tokens = usage_metadata.prompt_token_count
                output_tokens = usage_metadata.candidates_token_count + usage_metadata.thoughts_token_count
                got_token_counts = True
            except Exception as e:
                print('in estimate_google_gemini_cost for google gemini: ', e)
                return 0

        if model not in MODEL_PRICES:
            print(f"Pricing not defined for model: {model}")
            breakpoint()
            return 0

        # Handle tiered pricing for Gemini 2.5 Pro
        if model == "gemini-2.5-pro":
            if input_tokens > 200_000:
                prices = MODEL_PRICES[model]["long_prompt"]
            else:
                prices = MODEL_PRICES[model]["short_prompt"]
        else:
            prices = MODEL_PRICES[model]

        # Calculate cost per million tokens
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return input_cost + output_cost


    # model = 'gemini-2.5-pro'
    model = 'gemini-2.5-flash'
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
        model=model,
        contents= prompt,
        config=config,
    )

    cost = 0
    cost = estimate_google_gemini_cost(response, model)

    total_cost += cost
    print('Total cost so far:', total_cost)

    return response

def call_chatGPT_api(prompt, model_specifier = 'gpt-5', system_message = "You are an expert in cyber security breaches.", response_format = None):

    MODEL_PRICES = {
        "gpt-4o": {"input": 5.0, "output": 15.0},   # $5 / $15
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-5": {"input": 10.0, "output": 30.0},   # Example placeholder
    }

    def estimate_ChatGPT_cost(response, model: str) -> float:
        """
        Estimate the dollar cost of an OpenAI API response.

        Args:
            response: API response object from client.chat.completions.create()
            model: string, the model name (e.g., "gpt-4o", "gpt-5")

        Returns:
            float: estimated cost in USD
        """
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        if model not in MODEL_PRICES:
            raise ValueError(f"Pricing not defined for model: {model}")

        prices = MODEL_PRICES[model]
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return input_cost + output_cost



    global total_cost

    MODEL = model_specifier


    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]

    kwargs = {
        "model": model_specifier,
        "messages": messages,
    }

    # Only include response_format if it's provided
    if response_format is not None:
        kwargs["response_format"] = response_format

    response = openAI_client.chat.completions.create(**kwargs)

    cost = estimate_ChatGPT_cost(response, MODEL)
    total_cost += cost
    print('Total cost so far:', total_cost)

    return response

def call_perplexity_api(prompt: str):
    global total_cost

    """Call Perplexity API"""
    API_URL = "https://api.perplexity.ai/chat/completions"
    PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
    model = 'sonar-pro'

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
            print('May need to top off perplexity account funds. Buy more at https://www.perplexity.ai/account/api/billing')
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

def remove_duplicate_titles(articles):
    seen = set()
    return [article for article in articles
            if article['title'] not in seen and not seen.add(article['title'])]

def link_returns_status_200(url, title):
    result = False
    final_resolved_url = url

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
            final_resolved_url = response.url
    except Exception as e:
        pass

    if result:
        html_content = response.text
        result = False

        prompt = f"""
                I have this content from a web page: 
                {html_content}
                
                Does that content discuss the subject described in this text:?
                {title}
                
                Please respond with a JSON object containing these fields:
                
                "Match" - contains the text "true" if there is a match, or the text "false" if there is not a match, or the text "not sure" if it is not possible to tell.
                "Reasoning" - your reasoning 
            """

        # Google has the best access to breaking news stories
        try:
            ai_response_object = call_google_gemini_api(prompt)
            ai_response_message = get_text_message_from_llm_response(GEMINI_GOOGLE, ai_response_object)
            ai_response_message = repair_json(ai_response_message)
            ai_response_json = json.loads(ai_response_message)
            result = "false" not in ai_response_json['Match'].lower()
        except Exception as e:
            result = True

    return result, final_resolved_url


def confirm_article_url(article):
    today_str = datetime.now().strftime("%B %d, %Y")
    title = article['title']
    title = title.lower()
    # if 'eskom' in title or 'lotte' in title or 'community' in title:
    #     breakpoint()

    # some of these vertex article_urls resolve to the real article
    if 'vertex' in article['url']:
        try:
            final_url = requests.head(article['url'], allow_redirects=True).url
            article['url'] = final_url
            got_final_url = True
        except Exception as e:
            pass #sometimes requests throws a max retries error, meaning it couldn't resolve the url

    final_url = article['url']
    link_returns_200, final_resolved_url = link_returns_status_200(final_url, article['title'])
    article['url'] = final_resolved_url

    # and, some only resolve to a 404
    # let's try to look up the correct url

    prompt = f"""
        Find news articles that feature the same or a similar breach at the same target organization:
        
        {article['title']}
        
        They MUST have a publish date in this range: ["{today_str} 00:00" to "{today_str} 23:59" UTC]. This is VERY IMPORTANT! 
        
        Return a JSON array. For each matching article, return a JSON object in the array, with the following info:

        - title
        - url
        - source
        - summary
        - publish_date
        - full_text_of_article
        - number_of_records_breached (if unknown, put "unknown")
        - names_of_threat_actors (if unknown, put "unknown")
        
        If no such articles can be found, return a single json object with a field named "Result" that has the contents, "No matching articles found".
    """

    article_new = None
    python_object = call_google_gemini_api(prompt)
    if python_object is not None:
        try:
            article_string = python_object.text;
            reasoning, candidates = extract_reasoning_and_json(article_string)

            okay_to_continue = candidates is not None
            okay_to_continue = okay_to_continue and not('No articles found' in article_string)
            if okay_to_continue:
                for index, candidate in enumerate(candidates):
                    #confirm url is not a 404
                    link_returns_200, final_resolved_url = link_returns_status_200(candidate['url'], candidate['title'])
                    if link_returns_200:
                        candidate['url'] = final_resolved_url
                        article_new = candidate
                        break
        except Exception as e:
            print('confirm_article_url: ', e)

        return article_new

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
    reasoning = ''
    response_object = None

    #find start of json
    search_string = '[\n  {\n    "'
    try:
        position = text.find(search_string)
    except Exception as e:
        print('extract_reasoning_and_json: ', e)


    if position != -1:
        reasoning = text[:position]
        json_object_as_string = text[position:]

        # Regex pattern to find the incorrect closing double-quote
        # It looks for a double-quote followed by a comma, which is followed by
        # a newline and another double-quote (the start of the next key)
        # or end of the json object.
        # pattern = r'(?<!\\)"(?=\s*,(?:\s*"))'
        # json_object_as_string = re.sub(pattern, '', json_object_as_string)

        #sometimes the LLM returns anomalies. check for known anomalies
        brackets = [(m.start(), m.group()) for m in re.finditer(r'[\[\]]', json_object_as_string)]
        print("Last few brackets:", brackets[-10:])

        # Try to find what comes after the first complete JSON structure
        try:
            # Parse incrementally to find where valid JSON ends
            decoder = json.JSONDecoder()
            json_object_as_string = repair_json(json_object_as_string) #a lot of times LLMs return invalid json
            response_object, idx = decoder.raw_decode(json_object_as_string)
        except json.JSONDecodeError as e:
            print("Decoder error:", e, "probably the LLM returned invalid json")
            # breakpoint()
    else:
        print("Search string not found - article not found")

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

    # def generate(self, prompt: str, max_tokens: int = 500) -> str:
    #     """
    #     Make LLM API call - replace with actual API integration
    #     """
    #     # MOCK RESPONSE - Replace with real LLM API call
    #     # Example: response = self.client.chat.completions.create(...)
    #
    #     # For demo purposes, returning realistic mock responses
    #     if "categorize this cybersecurity incident" in prompt.lower():
    #         return """
    #         Category: HOSPITAL
    #         Reasoning: This incident involves a healthcare system with patient data (PHI) and medical records, which directly affects hospital operations and patient privacy. The mention of "Healthcare System" and "2.3M Patients" clearly indicates this is a hospital-level incident requiring immediate attention from healthcare cybersecurity professionals.
    #         """
    #     elif "assess the severity" in prompt.lower():
    #         return """
    #         Severity: HIGH
    #         Affected Count: 2300000
    #         Reasoning: This is a high-severity incident due to the massive scale (2.3M affected individuals), the sensitive nature of healthcare data (PHI, medical records), and the operational impact on patient care. Healthcare data breaches carry additional regulatory and safety implications beyond typical business breaches.
    #         """
    #     elif "extract technical details" in prompt.lower():
    #         return """
    #         Technical Details:
    #         - Attack vector: Ransomware deployment via compromised third-party vendor credentials
    #         - Threat actor: RansomHub ransomware group (preliminary attribution based on TTPs)
    #         - Data types compromised: PHI, SSNs, medical records, billing information
    #         - Systems affected: Primary EHR platform and patient portal
    #         - Impact duration: Systems offline for 72+ hours affecting patient care operations
    #         - Recovery status: Partial systems restoration in progress
    #         """
    #     else:
    #         return "Mock LLM response - replace with actual API integration"

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
        """Retrieve today's cybersecurity breach news using Gemini or Perplexity responses."""
        today_str = datetime.now().strftime("%B %d, %Y")
        new_articles_object = None

        prompt = f"""You are a specialized AI assistant for news retrieval with a single purpose: to find articles aboutcybersecurity breaches.
            The articles you find MUST have a publish date in this range: ["{today_str} 00:00" to "{today_str} 23:59" UTC]. This is VERY IMPORTANT! 

            **Your process must be as follows:**
            
            1.  **Initial Search (Hospitals & Medical Companies):**
                * Perform a series of broad and specific Google Searches to find news stories published today about cybersecurity breaches involving hospitals, medical companies, and healthcare providers.
                * Example search queries (you must use these as a starting point, but can and should generate more):
                    * "hospital data breach today"
                    * "medical company cyberattack today"
                    * "healthcare cybersecurity breach [today's date]"
            
            2.  **Second Search (All Other Companies):**
                * Conduct a separate, extensive series of Google Searches for any other companies that have experienced a cybersecurity breach today.
                * Example search queries (you must use these as a starting point, but can and should generate more):
                    * "company data breach today"
                    * "cyberattack on [company type e.g., 'financial institution'] today"
                    * "hacked today"
            
            3.  **Data Extraction & Filtering:**
                * Review all articles found in both searches.
                * Identify and extract all unique news stories about a distinct cybersecurity breach.
                * A "unique" breach is one where the affected company and the incident are distinct.
                * If multiple articles cover the same unique breach, select only one. Prioritize the article that includes details on threat actors and amount of data and/or records breached.
            
            4.  **Structured Output Generation:**
                * If no relevant news stories are found, return the exact string "No news today".
                * If stories are found, compile them into a JSON array.
                * For each story, ensure the following keys are present and populated. If a value is not available in the article, use the string "unknown".
                    * `title` (string)
                    * `url` (string)
                    * `source` (string)
                    * `summary` (string - a concise, 2-3 sentence summary)
                    * `publish_date` (string - format YYYY-MM-DD)
                    * `full_text_of_article` (string - capture the complete, unedited text of the article)
                    * `number_of_records_breached` (string or integer)
                    * `names_of_threat_actors` (string or array of strings)
                * The final JSON array should contain a maximum of 15 unique companies/breaches.
                * The final JSON array must be sorted alphabetically by company name.
                * Return the reasoning and the formatted JSON . Put the reasoning inside a single <think></think> tag. Include in the reasoning how publish_date was determined.
            
            **Constraints:**
            * Today's date is {today_str}.
            * Search date range: {today_str} 00:00 UTC to {today_str} 23:59 UTC.
            * Ensure all relevant stories are included and none are omitted due to incorrect deduplication.
        """

        python_object = call_google_gemini_api(prompt)
        if python_object is None:
            print('get_news_from_llm - No news stories found')
            exit(1)

        reasoning = None
        articles_object = None
        new_articles_object: List[dict] = []

        # First try: Perplexity-style dict response
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
            today_str = regularize_date_format_for_use_in_html(today_str)
            if articles_object is None:
                #no articles found
                return new_articles_object

            for article in articles_object:
                article_new = confirm_article_url(article)
                okay_to_add_this_article = article_new is not None
                if okay_to_add_this_article:
                    publish_date_of_this_article = article_new["publish_date"]
                    publish_date_of_this_article = regularize_date_format_for_use_in_html(publish_date_of_this_article)
                    if publish_date_of_this_article != today_str:
                        okay_to_add_this_article = False
                    if okay_to_add_this_article:
                        new_articles_object.append(article_new)
                else:
                    print(f"***Couldn't find a url and/or a date for this one: {article['title']}")

        new_articles_object = remove_duplicate_titles(new_articles_object)

        # Persist raw JSON for inspection
        file_path = settings.BASE_DIR / 'output' / 'articles_raw_json.json'
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(new_articles_object, indent=2))

        self.log_ai_decision("Get News Articles", 'Initial article retrieval', reasoning or 'N/A', None)
        print('Total articles retrieved: {}'.format(len(new_articles_object)))
        return new_articles_object

    def ai_categorize_incident(self, search_result: Dict) -> tuple[BreachCategory, str]:
        """
        AI DECISION POINT 2: Let AI analyze and categorize each incident
        """
        article_full_text = search_result.full_text_of_article

        categorization_prompt = f"""
            You are a cybersecurity analyst specializing in healthcare industry threats.
            
            Analyze and categorize this cybersecurity incident:
            
            FullText: {article_full_text}
            
            Categories to choose from:
            - HOSPITAL: Direct hospital/health system incidents
            - MEDICAL: Other medical/healthcare related (clinics, medical device companies, laboratories, direct patient care providers, etc.)
            - BUSINESS: Non-healthcare business incidents (companies not primarily involved in providing healthcare products or services, such as banks, law firms, venture capital, insurance, or general businesses, but relevant for threat intelligence)
            
            Guidelines:
            - Only assign an article to the HOSPITAL category if the breached company is specifically called a hospital or health system in the article.
            - Assign MEDICAL only if the organization provides direct medical products, services, patient care, operates clinics, medical device manufacturing, or healthcare delivery.
            - Exclude investors, venture capital firms, banks, insurance, consulting, or law firms from MEDICAL unless they directly provide medical/healthcare services or are clearly described as such in the article.
            - Default to BUSINESS for incidents involving entities that invest in, support, or provide services to healthcare/medical organizations, but do not themselves deliver medical/healthcare care or products.
            
            For healthcare cybersecurity professionals, consider:
            - PHI/medical data involvement
            - Healthcare infrastructure relevance
            - Regulatory implications (HIPAA, etc.)
            - Direct patient care impact
            
            Respond in this format:
            Category: [HOSPITAL/MEDICAL/BUSINESS]
            Reasoning: [Your detailed analysis of why this categorization is appropriate, clearly justifying your choice according to the above instructions]

            """

        if LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CHAT_GPT_OPEN_AI:
            ai_response_object = call_chatGPT_api(categorization_prompt)
        elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == PERPLEXITY:
            ai_response_object = call_perplexity_api(categorization_prompt)
        elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CLAUDE_ANTHROPIC:
            ai_response_object = call_claude_anthropic_api(categorization_prompt)

        ai_response_message = get_text_message_from_llm_response(LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS, ai_response_object)

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

        self.log_ai_decision("Incident Categorization", search_result.title, reasoning, category.value)
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
        
        Title: {search_result.title}
        Content: {search_result.summary}
        Category: {category.value}
        Source: {search_result.source}
        
        Consider for severity assessment:
        - Number of records breached (extract from content)
        - Number of people affected (extract from content)
        - Healthcare-specific factors (PHI, HIPAA, patient safety, care disruption)
        - Relevance to hospital cybersecurity
        - Regulatory implications
        - Operational impact
        - Attack sophistication
        - Type of data compromised
        
        Severity levels:
        - HIGH: Major incidents with many records breached
        - MEDIUM: Significant incidents with records breached
        - LOW: Minor incidents for awareness
        
        Respond in this format:
        Severity: [HIGH/MEDIUM/LOW]
        Affected Count: [number]
        Reasoning: [Your detailed severity analysis considering all factors]
        
        If an article duplicates an article that has a higher priority, include this text in the reasoning: "DUPLICATE ARTICLE"
        """

        try:
            if LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CHAT_GPT_OPEN_AI:
                ai_response_object = call_chatGPT_api(severity_prompt)
                ai_response_message = ai_response_object.choices[0].message.content
            elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == PERPLEXITY:
                ai_response_object = call_perplexity_api(severity_prompt)
                ai_response_message = ai_response_object["choices"][0]["message"]["content"]
            elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CLAUDE_ANTHROPIC:
                ai_response_object = call_claude_anthropic_api(severity_prompt)
                ai_response_message = ai_response_object.content[0].text

            clean_string = ai_response_message.strip().removeprefix('```json').removesuffix('```').strip()
            parsed = self.llm.parse_structured_response(clean_string, ["Severity", "Affected Count", "Reasoning"])
        except Exception as e:
            print('unexpected response from LLM for severity_prompt')
            # breakpoint()
            exit(1)

        severity_str = parsed.get("severity", "MEDIUM").upper()
        affected_str = parsed.get("affected count", "0")
        reasoning = parsed.get("reasoning", "AI severity assessment reasoning not parsed correctly")

        try:
            severity = SeverityLevel(severity_str.replace('*', '').lower())
        except ValueError:
            # breakpoint()
            reasoning += f" (Note: AI returned '{severity_str}', defaulted to MEDIUM)"

        # Extract affected count
        try:
            affected_count = int(''.join(filter(str.isdigit, affected_str)))
        except:
            affected_count = 0

        self.log_ai_decision(f"{search_result.title} Severity Assessment", search_result.title, reasoning, f"{severity.value}/{affected_count}")
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
        
        Title: {search_result.title}
        Content: {search_result.summary}
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
        -- Number of records breached
        -- Number of people affected
        -- Urgency of response needed
        
        Provide the optimal order (by incident number) and explain your prioritization reasoning.
        
        Respond in this format:
        Priority Order: [incident numbers in order, e.g., "3, 1, 2"]
        Reasoning: [Your detailed prioritization logic]
        """

        if LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CHAT_GPT_OPEN_AI:
            ai_response_object = call_chatGPT_api(prioritization_prompt)
            ai_response_message = ai_response_object.choices[0].message.content
        elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == PERPLEXITY:
            ai_response_object = call_perplexity_api(prioritization_prompt)
            ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        elif LLM_TO_USE_FOR_EVERYTHING_BUT_NEWS == CLAUDE_ANTHROPIC:
            ai_response_object = call_claude_anthropic_api(prioritization_prompt)
            ai_response_message = ai_response_object.content[0].text

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
        email_html = ""
        BREACH_COLORS = {
            'hospital': '#008000',
            'medical': '#008080',
            'business': '#3965bc'
        }

        SEVERITY_COLORS = {
            'high': '#d32f2f',
            'medium': '#fbc02d',
            'low': '#388e3c',
        }

        email_html += f"""
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <title>Cyber Breaches in the News Today</title>
            </head>
            <body style="margin:0;padding:0;background:#f7f7fa;font-family:Segoe UI, Arial, sans-serif;">
              <!-- Header -->
              <div style="background:#3965bc;padding:24px 0;text-align:center;">
                <span style="color:#fff;font-size:28px;font-weight:600;letter-spacing:0.5px;line-height:1.2;">Cyber Breaches in the News Today</span>
              </div>
              <!-- Container -->
              <div style="max-width:680px;margin:32px auto;padding:0 16px;">
    
        """
        incident_data = []
        for incident in incidents:
            color_for_breach_category = BREACH_COLORS[incident.breach_category.lower()]
            color_for_severity = SEVERITY_COLORS[incident.severity.lower()]
            email_html += f"""
                <!-- Incident Card: {incident.title} -->
                <div style="background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(57,101,188,0.07);margin-bottom:24px;padding:24px;">
                  <a href="{incident.url}" style="font-size:20px;font-weight:600;color:#3965bc;text-decoration:none;line-height:1.4;display:block;">{incident.title}</a>
                    
                    <!-- Badges row (Outlook-safe) -->
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:12px 0 8px 0;">
                      <tr>
                        <td style="white-space:nowrap;">
                          <span style="background:{color_for_breach_category};color:#ffffff;border-radius:18px;padding:4px 14px;font-size:13px;font-weight:500;display:inline-block;mso-line-height-rule:exactly;">{incident.breach_category}</span>
                        </td>
                        <td style="width:10px;font-size:0;line-height:0;">&nbsp;</td>
                        <td style="white-space:nowrap;">
                          <span style="background:{color_for_severity};color:#ffffff;border-radius:14px;padding:2px 10px;font-size:12px;font-weight:500;display:inline-block;mso-line-height-rule:exactly;">{incident.severity}</span>
                        </td>
                      </tr>
                    </table>
                    
                  <div style="font-size:15px;color:#222;margin-bottom:14px;line-height:1.6;">
                    {incident.summary}
                  </div>
                  <div style="font-size:13px;color:#555;line-height:1.7;">
                    <strong>Publish Date:</strong> {incident.publish_date}<br>
                    <strong>Number of Records Breached:</strong> {incident.number_of_records_breached}<br>
                    <strong>Potential Threat Actors:</strong> {incident.names_of_threat_actors}<br>
                    <strong>Source:</strong> {incident.source}<br>
                  </div>
                </div>
            """

        email_html += f"""  </div>
            </body>
            </html>
        """

        # IF YOU GIVE AI TOO MANY STORIES IT GETS CONFUSED AND ONLY GIVES YOU BACK 5-8 STORIES
        # HERE'S THE CODE
        """
        # AI DECISION POINT 6: Let AI determine optimal presentation format
 
        # incident_data = []
        # for incident in incidents:
        #     incident_data.append({
        #         "title": incident.title,
        #         "breach_category": incident.breach_category,
        #         "affected": incident.affected_count,
        #         "summary": incident.summary,  # Limit for prompt size
        #         "source": incident.source,
        #         "severity": incident.severity,
        #         "url": incident.url,
        #         "publish_date": regularize_date_format_for_use_in_html(incident.publish_date),
        #         "names_of_potential_threat_actors": incident.names_of_threat_actors,
        #         "number_of_records_breached": incident.number_of_records_breached
        #     })
        #
        # format_prompt = f"""
        # You are designing an email briefing format for healthcare cybersecurity professionals.
        #
        # Context: Daily threat intelligence briefing
        # Audience: Healthcare CISOs, security analysts, IT directors
        # Delivery: HTML email
        #
        # Here is the title shown in the email:
        # Cyber Breaches in the News Today
        #
        # Put that title in white text on a #3965bc background.
        #
        # Incident data to present:
        # {json.dumps(incident_data, indent=2)}
        #
        # Design decisions to make:
        # - How to make the email look professionally-designed?
        # - How should incidents be visually differentiated?
        # - What information should be most prominent?
        # - What visual hierarchy works best for busy executives?
        # - How to make sure the HTML will work in an email?
        #
        # Provide your formatting strategy and reasoning, then generate the HTML.
        #
        # Use this color scheme:
        # - Primary accent: #3965bc
        #
        # For breach_category, use these highlight colors:
        # - Hospital: white text on green rounded rect
        # - Medical:  white text on #008080 rounded rect
        # - Business: white text on #3965bc rounded rect
        #
        # Make sure to put breach_category on its own separate line
        #
        # For each article, MAKE SURE TO INCLUDE EACH OF THE FOLLOWING:
        # - Title
        # - Summary
        # - breach_category
        # - publish_date
        # - severity
        # - Clicking the article title should take us to the url of the source
        # - Number of records breached (if that is known)
        # - Names of the potential threat actors (if that is known)
        # - Source
        #
        # Respond in this format:
        # Format Strategy: [Your design reasoning and approach]
        # HTML: [Complete HTML email code]
        # """
        #
        # ai_response_object = call_perplexity_api(format_prompt)
        # ai_response_message = ai_response_object["choices"][0]["message"]["content"]
        # html_match = re.search(r'HTML:\s*```html\s*(.*?)\s*```', ai_response_message, re.DOTALL)
        # if html_match:
        #     clean_string = html_match.group(1).strip()
        #
        # strategy_reasoning = "AI determined optimal visual hierarchy with healthcare-specific iconography and severity color coding for rapid threat assessment by busy cybersecurity professionals."
        #
        # self.log_ai_decision("Email Format Generation", "Generate Email Format", strategy_reasoning, f"Generated {len(clean_string)} character HTML")
        return email_html, ""

    def run_ai_agent(self, gather_articles_only) -> Dict[str, Any]:
        """
        Execute the complete AI agent workflow where AI makes all decisions
        """
        self.log_ai_decision("AI Agent Initialization", "Starting true AI-driven cybersecurity breach analysis for healthcare industry", "STARTED")

        # AI Decision Pipeline - each step uses LLM calls

        if gather_articles_only:
            search_results = self.get_news_from_llm()
            for result in search_results:
                try:
                    embedding_data = generate_article_embeddings(result)

                    # Create article with embeddings
                    incident, created = NewsArticle.objects.get_or_create(
                        url=result["url"],
                        defaults={
                            'title': result["title"],
                            'source': result["source"],
                            'summary': result["summary"],
                            'full_text_of_article': result["full_text_of_article"],
                            'number_of_records_breached': result["number_of_records_breached"],
                            'names_of_threat_actors': result["names_of_threat_actors"],
                            'publish_date': regularize_date_format_for_use_in_database(result['publish_date']),
                            # Add embeddings
                            **embedding_data
                        }
                    )

                    if created:
                        logger.info(f"Created new article with embeddings: {incident.title}")
                    else:
                        logger.info(f"Article already exists: {incident.title}")
                except Exception as e:
                    print('gather_articles_only: ', e)


            recluster_all_articles()
            return {
                "summary_of_ai_decisions": "",
                "incidents_found": len(search_results),
                "incidents_processed": 0,
                "email_html": 0,
                "decision_log": self.decision_log,
                "ai_summary": '',
                "total_ai_decisions": len(self.decision_log)
            }


        processed_incidents = []

        # recluster_all_articles()

        articles = NewsArticle.objects.filter(
            created_at__range=(START_DATE, END_DATE)
        ).order_by('story_cluster_id', 'created_at')

        print('total articles before de-duplication: ', articles.count())
        story_cluster_ids = []

        for result in articles:
            if result.story_cluster_id in story_cluster_ids:
                print('Found duplicate story cluster id:', result.story_cluster_id)
                continue

            link_returns_200, final_resolved_url = link_returns_status_200(result.url, result.title)
            result.url = final_resolved_url
            if not link_returns_200:
                continue

            story_cluster_ids.append(result.story_cluster_id)

            # Let AI make all the decisions for each incident
            category, cat_reasoning = self.ai_categorize_incident(result)
            severity, affected_count, sev_reasoning = self.ai_assess_severity(result, category)
            # details, det_reasoning = self.ai_extract_technical_details(result, category)

            incident = BreachIncident(
                title=result.title,
                breach_category=category.name,
                severity=severity.name,
                affected_count=affected_count,
                source=result.source,
                url=result.url,
                summary=result.summary,
                full_text_of_article = result.full_text_of_article,
                number_of_records_breached = result.number_of_records_breached,
                names_of_threat_actors = result.names_of_threat_actors,
                publish_date= result.publish_date,
                ai_reasoning = ''
            )

            processed_incidents.append(incident)

        print('total articles after de-duplication: ', len(processed_incidents))

        # Let AI prioritize the incidents
        prioritized_incidents, prioritization_reasoning = self.ai_prioritize_incidents(processed_incidents)

        # Let AI generate the email format
        email_html, format_reasoning = self.ai_generate_email_format(prioritized_incidents)

        # Final AI summary
        summary_prompt = f"""
        Summarize the AI agent's performance in this cybersecurity intelligence gathering session. 
        For each value of 'title', and within that for each value of 'decision_type', summarize the 'ai_reasoning'
        
        Use this HTML for the email:
        
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>AI Agent Performance Summary – Cybersecurity Intelligence Gathering Session</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f7f7fa; color: #222; margin: 0; padding: 0; }}
                .container {{ max-width: 900px; margin: 40px auto; background: #fff; padding: 32px 36px 36px 36px; border-radius: 10px; box-shadow: 0 2px 10px rgba(60,60,80,0.10);}}
                h1 {{ color: #294166; margin-bottom: 0.5em; }}
                h2 {{ color: #45649b; margin-top: 2em; }}
                h3 {{ color: #20507c; margin-top: 1.5em; }}
                .subheader {{ color: #4a7eb5; margin-bottom: 1.2em; font-size: 1.15em; }}
                .section {{ margin-bottom: 2.5em; }}
                table {{ width: 100%; border-collapse: collapse; margin: 1em 0; }}
                th, td {{ border: 1px solid #e1e1e1; padding: 10px 8px; }}
                th {{ background: #e3eaf4; text-align: left; }}
                .tag {{ display: inline-block; padding: 2px 10px; border-radius: 7px; font-size: 0.92em; margin-right: 6px;}}
                .tag-init {{ background: #d9e7fd; color: #374b68; }}
                .tag-severity {{ background: #f8e3a3; color: #b37b00; }}
                .tag-business {{ background: #e7f7ea; color: #246442; }}
                .tag-medium {{ background: #ffe5b7; color: #a8740a; }}
                .tag-priority {{ background: #e1eafd; color: #224c82; }}
                .tag-email {{ background: #f4e7f7; color: #8653a3; }}
                .highlight {{ background: #fff8d4; }}
                .severity-high {{ color: #d2173f; }}
                .severity-medium {{ color: #b37b00; }}
                .severity-low {{ color: #246442; }}
                code {{ background: #f0f2f6; padding: 1px 6px; border-radius: 3px; }}
            </style>
        </head>
        <body>
        <div class="container">
            <h1>AI Agent Performance Summary</h1>
            <div class="subheader">
                <strong>Session Scope:</strong> Automated cybersecurity intelligence gathering, incident categorization, severity assessment, and prioritization for the healthcare sector.<br>
                <strong>Date:</strong> <!-- Insert report date here -->
            </div>
        
            <div class="section">
                <h2>Session Initialization</h2>
                <table>
                    <tr>
                        <th width="128">Decision Type</th>
                        <th>AI Reasoning</th>
                    </tr>
                    <!-- Insert session initialization rows here -->
                </table>
            </div>
        
            <div class="section">
                <h2>Incident Analysis & Reasoning Details</h2>
                <!-- For each incident, repeat this block -->
                <h3><!-- Insert Incident Headline Here --></h3>
                <table>
                    <tr>
                        <th width="128">Decision Type</th>
                        <th>AI Reasoning</th>
                    </tr>
                    <!-- Insert analysis/categorization and severity assessment rows here -->
                    <!-- For the severity assessment rows, summarize them by each of these categories: 
                        - Regulatory
                        - Operational
                        - Attack sophistication
                        - Scale
                        - Healthcare factors
                        - Compromised Data
                        ... and put each category in a separate bullet point. Boldface the name of the category.
                    -->
                    <-- Under the list of bullet points, state the severity category (HIGH/MEDIUM/LOW), and sum up the reasons for that in a single sentence. -->
                    
                    
                </table>
            </div>
        
            <div class="section">
                <h2>Incident Prioritization</h2>
                <table>
                    <tr>
                        <th width="128">Order</th>
                        <th>Incident</th> 
                        <th>AI Reasoning for Priority</th>
                    </tr>
                    <!-- Insert prioritization rows here -->
                </table>
            </div>
        
            <div class="section">
                <h2>Email Format Generation</h2>
                <table>
                    <tr>
                        <th width="128">Decision Type</th>
                        <th>AI Reasoning</th>
                    </tr>
                    <!-- Insert email format generation row(s) here -->
                </table>
            </div>
        </div>
        </body>
        </html>

        Here is the data to be summarized: {json.dumps(self.decision_log, indent=2)}
        
        Provide the results in html format. Return only the html.
        """

        # chatGPT works better than Perplexity for this
        # Perplexity often leaves out articles
        ai_response_object = call_chatGPT_api(summary_prompt)
        ai_response_message = get_text_message_from_llm_response(CHAT_GPT_OPEN_AI, ai_response_object)

        ai_response_message.replace("```html", "").replace("```", "")
        self.log_ai_decision("Final AI Summary", 'Wrap-Up', ai_response_message, "COMPLETED")

        return {
            "summary_of_ai_decisions": ai_response_message,
            "incidents_found": len(articles),
            "incidents_processed": prioritized_incidents,
            "email_html": email_html,
            "decision_log": self.decision_log,
            "ai_summary": '',
            "total_ai_decisions": len(self.decision_log)
        }

def startAI_Agent(gather_articles_only=False):
    global total_cost

    # Initialize LLM client (replace with real API integration)
    llm_client = LLMClient(api_key="your-api-key-here", model="gpt-4")

    # Initialize the TRUE AI agent
    ai_agent = TrueAIBreachAgent(llm_client, healthcare_focus=True)

    if gather_articles_only:
        print("Gathering articles only. Final report will use all articles.")
    else:
        print("🤖 Starting AI Cybersecurity Breach Agent...")
        print("🧠 All decisions will be made by AI, not hardcoded rules")
        print("=" * 70)

    results = ai_agent.run_ai_agent(gather_articles_only)

    if gather_articles_only:
        print("News articles have been gathered and saved to DB")
        return

    # Display results
    print(f"\n📊 AI AGENT RESULTS:")
    print(f"Incidents found: {results['incidents_found']}")
    print(f"AI decisions made: {results['total_ai_decisions']}")
    print(f"AI summary: {results['ai_summary']}")

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