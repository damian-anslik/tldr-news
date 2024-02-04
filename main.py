import streamlit as st
import validators
import newspaper
import supabase
import logging
import openai

logger = logging.getLogger(__name__)
strings = {
    "APP_NAME": "🤖 TLDR.ai",
    "APP_DESCRIPTION": "Welcome to TLDR.ai! Simply enter a URL to start chatting with any news article, blog post, or documentation.",
    "RECENT_CHATS_HEADER": "Recent Chats",
    "CHAT_INPUT_PLACEHOLDER": "Enter a question or message...",
    "NEW_CHAT_BUTTON_LABEL": "New Chat",
    "NEW_CHAT_INPUT_PLACEHOLDER": "Enter a URL to start a new chat...",
    "NEW_CHAT_TITLE": "Create a new chat",
    "INVALID_URL_MESSAGE": "Please enter a valid URL.",
}
app_config = {
    "OPENAI_API_KEY": st.secrets["OPENAI_API_KEY"],
    "OPENAI_COMPLETIONS_MODEL": st.secrets["OPENAI_COMPLETIONS_MODEL"],
    "SUPABASE_PROJECT_URL": st.secrets["SUPABASE_PROJECT_URL"],
    "SUPABASE_API_KEY": st.secrets["SUPABASE_API_KEY"],
}
db_client = supabase.Client(
    supabase_url=st.secrets["SUPABASE_PROJECT_URL"],
    supabase_key=st.secrets["SUPABASE_API_KEY"],
)


def download_article(url: str) -> dict:
    article = newspaper.Article(url)
    article.download()
    article.parse()
    filtered_keywords = [
        "The Explainer",
    ]
    for keyword in filtered_keywords:
        if keyword in article.text:
            raise Exception(
                f"Article is not supported - contains filtered keyword: {keyword}."
            )
    return {
        "url": article.url,
        "title": article.title,
        "text": article.text,
    }


def generate_chat_completion(
    context: str,
    question: str,
    api_key: str,
    completion_model: str,
    previous_messages: list[dict] = [],
) -> dict:
    openai_client = openai.OpenAI(api_key=api_key)
    completion_response = openai_client.chat.completions.create(
        model=completion_model,
        messages=[
            {
                "role": "system",
                "content": f"""
                    Instructions:

                    - You are a helpful assistant whose goal is to answer user questions based on the provided context.
                    - You can answer questions, provide explanations, and offer help, as long as the questions are relevant to the context.
                    - If you are unable to answer the user's question, return the message: "I'm sorry, I don't know the answer to that question."
                    - If the users question is not relevant to the context, return the message: "I'm sorry, I can't help with that question given the context provided." 
                    
                    Context: 
                    
                    {context}
                """,
            },
            *previous_messages,
            {"role": "user", "content": question},
        ],
    )
    question_answer = {
        "role": "assistant",
        "content": completion_response.choices[0].message.content,
    }
    return question_answer


def get_user_chats() -> dict:
    user_chats_response = db_client.table("chats").select("*").execute()
    user_chats_response_data = user_chats_response.data
    user_chats = {chat["id"]: chat for chat in user_chats_response_data}
    return user_chats


def insert_new_chat(chat_data: dict) -> tuple[int, dict]:
    insert_response = db_client.table("chats").insert([chat_data]).execute()
    insert_response_data = insert_response.data[0]
    chat_id = insert_response_data["id"]
    return chat_id, chat_data


def update_user_chat(chat_id: str, update_data: dict):
    db_client.table("chats").update(update_data).eq("id", chat_id).execute()


def create_new_chat(url: str) -> str:
    article_details = download_article(url)
    new_chat_data = {
        "title": article_details["title"],
        "url": article_details["url"],
        "text": article_details["text"],
        "messages": [
            {
                "role": "assistant",
                "content": f"Hey! What would you like to know about: **{article_details['title']}** ({url})?",
            }
        ],
    }
    chat_id, chat_data = insert_new_chat(new_chat_data)
    st.session_state["chats"][chat_id] = chat_data
    return chat_id


def render_chat_message(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def render_new_chat_view():
    st.title(strings["NEW_CHAT_TITLE"])
    if url := st.chat_input(strings["NEW_CHAT_INPUT_PLACEHOLDER"]):
        if not validators.url(url):
            st.error(strings["INVALID_URL_MESSAGE"])
        else:
            try:
                new_chat_id = create_new_chat(url)
            except Exception as e:
                st.error(str(e))
                return
            set_active_chat(new_chat_id)
            st.rerun()


def render_existing_chat_view(chat_id: str):
    chat = st.session_state["chats"][chat_id]
    st.title(chat["title"])
    for message in chat["messages"]:
        render_chat_message(message["role"], message["content"])
    if question := st.chat_input(strings["CHAT_INPUT_PLACEHOLDER"]):
        user_question = {
            "role": "user",
            "content": question,
        }
        render_chat_message(user_question["role"], user_question["content"])
        response = generate_chat_completion(
            context=chat["text"],
            question=question,
            api_key=app_config["OPENAI_API_KEY"],
            completion_model=app_config["OPENAI_COMPLETIONS_MODEL"],
            previous_messages=st.session_state["chats"][chat_id]["messages"],
        )
        render_chat_message(response["role"], response["content"])
        st.session_state["chats"][chat_id]["messages"].extend([user_question, response])
        update_user_chat(chat_id=chat_id, update_data={"messages": [*chat["messages"]]})


def render_chat():
    active_chat_id = st.session_state.get("active_chat_id")
    if not active_chat_id:
        render_new_chat_view()
    else:
        render_existing_chat_view(active_chat_id)


def render_sidebar():
    with st.sidebar:
        st.title(strings["APP_NAME"])
        st.write(strings["APP_DESCRIPTION"])
        new_chat_button = st.button(
            strings["NEW_CHAT_BUTTON_LABEL"],
            use_container_width=True,
        )
        if new_chat_button:
            st.session_state["active_chat_id"] = None
        if len(st.session_state.get("chats", {})) > 0:
            st.header(strings["RECENT_CHATS_HEADER"])
            chat_history = st.session_state.get("chats", {})
            for chat_id, chat in chat_history.items():
                load_chat_button = st.button(
                    chat["title"],
                    use_container_width=True,
                    key=chat_id,
                )
                if load_chat_button:
                    set_active_chat(chat_id)


def set_active_chat(chat_id: str):
    st.session_state["active_chat_id"] = chat_id


def get_session_state():
    if "chats" not in st.session_state:
        st.session_state["chats"] = get_user_chats()
    if "active_chat_id" not in st.session_state:
        st.session_state["active_chat_id"] = None


def main():
    get_session_state()
    render_sidebar()
    render_chat()


if __name__ == "__main__":
    main()
