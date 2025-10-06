from cybersecurity.analysis_settings import CHAT_GPT_OPEN_AI, GEMINI_GOOGLE
from django.conf import settings
from cybersecurity.report_latest_cybersecurity_news import call_google_gemini_api, call_chatGPT_api, \
    get_text_message_from_llm_response

from cybersecurity.seek_trends_past_4_weeks import do_analysis_of_past_4_weeks_get_json, \
    do_analysis_of_past_4_weeks_get_html
from cybersecurity.seek_trends_past_7_days import do_analysis_of_how_the_past_7_days_fits_into_the_trends


def seek_trends(llm_to_use=CHAT_GPT_OPEN_AI, days=30, category= ''):
    LLM_TO_USE_WITH_THIS_FUNCTION = llm_to_use #Can be CHAT_GPT_OPEN_AI or GEMINI_GOOGLE
    PERFORM_NEW_ANALYSIS_OF_PAST_30_DAYS = False
    OUTPUT_NEW_HTML_REPORT_FOR_PAST_30_DAYS = True
    PERFORM_NEW_ANALYSIS_OF_PAST_7_DAYS = True

    if PERFORM_NEW_ANALYSIS_OF_PAST_30_DAYS:
        html_report_json_cleaned = do_analysis_of_past_4_weeks_get_json(LLM_TO_USE_WITH_THIS_FUNCTION)
    else:
        filename = f"seek_trends_raw_json-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.json"
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, 'r', encoding='utf-8') as file:
            html_report_json_cleaned = file.read()

    if OUTPUT_NEW_HTML_REPORT_FOR_PAST_30_DAYS:
        past_30_days_report_html = do_analysis_of_past_4_weeks_get_html(html_report_json_cleaned)
        filename = f"seek_trends_html_report-{'chatGPT' if LLM_TO_USE_WITH_THIS_FUNCTION == CHAT_GPT_OPEN_AI else 'gemini'}.html"
        file_path = settings.BASE_DIR / 'output' / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(past_30_days_report_html)



    if PERFORM_NEW_ANALYSIS_OF_PAST_7_DAYS:
        past_7_days_trends_html = do_analysis_of_how_the_past_7_days_fits_into_the_trends(LLM_TO_USE_WITH_THIS_FUNCTION, html_report_json_cleaned)

    pass