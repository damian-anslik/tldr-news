import streamlit as st
import validators
import newspaper
import supabase
import openai


def generate_summary(article_text: str, model_config: dict) -> str:
    openai_client = openai.OpenAI(api_key=model_config["OPENAI_API_KEY"])
    system_prompt = """
    Create a concise TLDR summary of a news article provided by the user. 
    The user will paste the contents of the article, and you return a summary. 
    The summary should be limited to 250 words. 
    Remove any bias that may be present in the article, and only present the facts. 
    Only include information pertaining to the topic at hand - information not relevant to the topic of the article should be omitted. 
    The response should be formatted as a list of bullet points. 
    Use proper English grammar and punctuation rules with sentences ending in a period.
    """
    completion_response = openai_client.chat.completions.create(
        model=model_config["OPENAI_COMPLETIONS_MODEL"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": article_text},
        ],
    )
    return completion_response.choices[0].message.content


def get_article(url: str, app_config: dict) -> dict:
    db_client = supabase.Client(
        supabase_url=app_config["SUPABASE_PROJECT_URL"],
        supabase_key=app_config["SUPABASE_API_KEY"],
    )
    articles = db_client.table("articles")
    try:
        article_data = articles.select("*").eq("url", url).single().execute().data
    except:
        model_config = {
            "OPENAI_API_KEY": app_config["OPENAI_API_KEY"],
            "OPENAI_COMPLETIONS_MODEL": app_config["OPENAI_COMPLETIONS_MODEL"],
        }
        article = newspaper.Article(url)
        article.download()
        article.parse()
        article_summary = generate_summary(article.text, model_config)
        article_data = {
            "title": article.title,
            "text": article.text,
            "url": url,
            "summary": article_summary,
        }
        articles.insert(article_data).execute()
    return article_data


def add_chat_message(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def add_article(article_data: dict):
    st.session_state.articles.append(article_data)


app_config = {
    "APP_NAME": "TLDR News",
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
        article_data = get_article(url, app_config)
    article_summary = article_data["summary"]
    article_title = article_data["title"]
    add_article(article_data)
    add_chat_message("assistant", article_title + "\n" + article_summary)
    st.rerun()
