import streamlit as st
import validators
import newspaper
import datetime
import supabase
import requests
import logging
import openai
import json

logger = logging.getLogger(__name__)


def parse_generated_summary(raw_response: str) -> dict:
    response = raw_response.strip("`").replace("json", "").strip()
    try:
        return json.loads(response)
    except:
        return {}


def generate_summary(article_text: str, article_title: str, model_config: dict) -> dict:
    openai_client = openai.OpenAI(api_key=model_config["OPENAI_API_KEY"])
    with open("system_prompt.txt", "r") as f:
        system_prompt = f.read()
    completion_response = openai_client.chat.completions.create(
        model=model_config["OPENAI_COMPLETIONS_MODEL"],
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps({"title": article_title, "text": article_text}),
            },
        ],
    )
    formatted_completion_content = parse_generated_summary(
        completion_response.choices[0].message.content
    )
    if not formatted_completion_content:
        raise Exception(
            f"Failed to generate summary: {completion_response.choices[0].message.content}"
        )
    return formatted_completion_content


def download_article(url: str) -> dict:
    article = newspaper.Article(url)
    article.download()
    article.parse()
    filtered_keywords = [
        "The Explainer",
    ]
    if any(keyword in article.text for keyword in filtered_keywords):
        raise Exception("Article is not supported - contains filtered keywords.")
    return {
        "url": article.url,
        "title": article.title,
        "text": article.text,
    }


def get_article(url: str, app_config: dict) -> dict:
    db_client = supabase.Client(
        supabase_url=app_config["SUPABASE_PROJECT_URL"],
        supabase_key=app_config["SUPABASE_API_KEY"],
    )
    articles = db_client.table("articles")
    existing_articles = articles.select("*").eq("url", url).execute()
    if len(existing_articles.data) > 0:
        return existing_articles.data[0]
    model_config = {
        "OPENAI_API_KEY": app_config["OPENAI_API_KEY"],
        "OPENAI_COMPLETIONS_MODEL": app_config["OPENAI_COMPLETIONS_MODEL"],
    }
    try:
        article = download_article(url)
    except Exception as e:
        db_client.table("failing-articles").insert({"url": url}).execute()
        logger.error(f"Failed to download article - {str(e)}")
        raise
    try:
        generated_summary = generate_summary(
            article_text=article["text"],
            article_title=article["title"],
            model_config=model_config,
        )
    except Exception as e:
        logger.error(f"Failed to generate article summary - {str(e)}")
        raise
    inserted_article_data = {
        **article,
        "summary": generated_summary["summary"],
    }
    related_articles = get_related_articles(
        article_keywords=generated_summary["keywords"],
        from_date=datetime.datetime.now() - datetime.timedelta(hours=72),
        api_key=app_config["NEWSAPI_API_KEY"],
    )
    inserted_article_data["related_articles"] = related_articles
    articles.insert(inserted_article_data).execute()
    return inserted_article_data


def get_related_articles(
    article_keywords: list[str],
    from_date: datetime.datetime,
    api_key: str,
    limit: int = 5,
) -> list[dict]:
    query_string = " ".join(article_keywords)
    from_date_string = from_date.date().strftime("%Y-%m-%d")
    response = requests.get(
        url="https://newsapi.org/v2/everything",
        params={
            "q": query_string,
            "from": from_date_string,
            "pageSize": limit,
            "page": 1,
        },
        headers={"X-Api-Key": api_key},
    )
    if not response.ok:
        logger.error(f"Failed to get related articles: {response.text}")
        return []
    response_data = response.json()
    return response_data["articles"]


def add_chat_message(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def add_article(article_data: dict):
    st.session_state.articles.append(article_data)


app_config = {
    "APP_NAME": "TLDR News",
    "NEWSAPI_API_KEY": st.secrets["NEWSAPI_API_KEY"],
    "CHAT_INPUT_PLACEHOLDER": "Enter a URL to summarise...",
    "OPENAI_API_KEY": st.secrets["OPENAI_API_KEY"],
    "OPENAI_COMPLETIONS_MODEL": st.secrets["OPENAI_COMPLETIONS_MODEL"],
    "SUPABASE_PROJECT_URL": st.secrets["SUPABASE_PROJECT_URL"],
    "SUPABASE_API_KEY": st.secrets["SUPABASE_API_KEY"],
}
st.title(app_config["APP_NAME"])
if "messages" not in st.session_state:
    st.session_state.messages = []
if "articles" not in st.session_state:
    st.session_state.articles = []
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
if url := st.chat_input(app_config["CHAT_INPUT_PLACEHOLDER"]):
    add_chat_message("user", url)
    if not validators.url(url):
        add_chat_message("assistant", "Please enter a valid URL.")
        st.rerun()
    with st.spinner(f"Getting article summary for '{url}'..."):
        try:
            article_data = get_article(url, app_config)
        except:
            add_chat_message(
                "assistant",
                "An error occurred while trying to get the article summary. Please try again later.",
            )
            st.rerun()
    article_summary = article_data["summary"]
    article_title = article_data["title"]
    add_article(article_data)
    add_chat_message("assistant", article_title + "\n" + article_summary)
    st.rerun()
