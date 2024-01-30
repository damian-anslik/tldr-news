import streamlit as st
import newspaper
import supabase
import openai


openai_client = openai.OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"],
)
completions_model = st.secrets["OPENAI_COMPLETIONS_MODEL"]
db_client = supabase.Client(
    supabase_url=st.secrets["SUPABASE_PROJECT_URL"],
    supabase_key=st.secrets["SUPABASE_API_KEY"],
)
articles = db_client.table("articles")


def get_article(url: str) -> dict:
    article = newspaper.Article(url)
    article.download()
    article.parse()
    return {
        "title": article.title,
        "text": article.text,
        "url": url,
    }


def generate_summary(article_text: str) -> str:
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
        model=completions_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": article_text},
        ],
    )
    return completion_response.choices[0].message.content


if "messages" not in st.session_state:
    st.session_state.messages = []
if "articles" not in st.session_state:
    st.session_state.articles = []
st.title("TLDR News")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
if url := st.chat_input("Enter a URL to summarise..."):
    st.session_state.messages.append({"role": "user", "content": url})
    is_valid_url = url.startswith("http")
    if not is_valid_url:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Please enter a valid URL.",
            }
        )
        st.rerun()
    try:
        article = articles.select("*").eq("url", url).single().execute().data
    except:
        with st.spinner(f"Downloading article from '{url}'..."):
            article = get_article(url)
        with st.spinner(f"Summarising article '{article['title']}'..."):
            article_summary = generate_summary(article["text"])
        article.update({"summary": article_summary})
        articles.insert([article]).execute()
    article_summary = article["summary"]
    article_title = article["title"]
    st.session_state.articles.append(article)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": article_title + "\n" + article_summary,
        }
    )
    st.rerun()
