import streamlit as st
import os
import uuid
import yaml
import sys
import json
import boto3
from pathlib import Path
from config import bot_configs
from ui_utils import invoke_agent
from utils.bedrock_agent import agents_helper


boto3.setup_default_session()

os.environ['AWS_DEFAULT_REGION'] = "us-west-2"
os.environ['AWS_ACCESS_KEY_ID'] = ""
os.environ['AWS_SECRET_ACCESS_KEY'] = ""
os.environ['AWS_SESSION_TOKEN']=""

def initialize_session():
    """Initialize session state and bot configuration."""
    if 'count' not in st.session_state:
        st.session_state['count'] = 1
        st.session_state['conversations'] = []  # List of conversation groups
        st.session_state['current_conversation'] = None

        # Refresh agent IDs and aliases
        for idx, config in enumerate(bot_configs):
            try:
                agent_id = agents_helper.get_agent_id_by_name(config['agent_name'])
                agent_alias_id = agents_helper.get_agent_latest_alias_id(agent_id)
                bot_configs[idx]['agent_id'] = agent_id
                bot_configs[idx]['agent_alias_id'] = agent_alias_id
            except Exception as e:
                print(f"Could not find agent named:{config['agent_name']}, skipping...")
                continue

        # Get bot configuration
        # bot_name = os.environ.get('BOT_NAME', 'Energy Agent')
        bot_name = os.environ.get('BOT_NAME', 'Energy Agent')
        bot_config = next((config for config in bot_configs if config['bot_name'] == bot_name), None)
        
        if bot_config:
            st.session_state['bot_config'] = bot_config
            
            # Load tasks if any
            task_yaml_content = {}
            if 'tasks' in bot_config:
                with open(bot_config['tasks'], 'r') as file:
                    task_yaml_content = yaml.safe_load(file)
            st.session_state['task_yaml_content'] = task_yaml_content

            # Initialize session ID if not exists
            if 'session_id' not in st.session_state:
                st.session_state['session_id'] = str(uuid.uuid4())
            
            # Initialize messages if not exists
            if 'messages' not in st.session_state:
                st.session_state.messages = []


def main():
    """Main application flow."""
    initialize_session()

    # Display chat interface in main area
    st.title(f"🚀 {st.session_state['bot_config']['bot_name']}")
    # st.title(f"⚡️ 에너지 효율 관리 에이전트 🤖")
    
    # Display status panel in sidebar
    with st.sidebar:
        st.title("Status & Results")
        for conv_idx, conv in enumerate(reversed(st.session_state.get('conversations', [])), 1):
            with st.expander(f"{conv['question']}", expanded=True):
                for agent in conv['agents']:
                    container1 = st.container(border=True)
                    container1.write(f"**{agent['name']}** ({agent['time'].strftime('%H:%M:%S')})")
                    if 'tools_used' in agent:
                        # Convert set to list if it's still a set
                        tools = list(agent['tools_used']) if isinstance(agent['tools_used'], set) else agent['tools_used']
                        for tool in tools:
                            container1.markdown(f"- {tool}")
                if 'tokens' in conv:
                    # st.write("---")
                    container = st.container(border=True)
                    container.write(f"Input Tokens: **{conv['tokens']['input']}**")
                    container.write(f"Output Tokens: **{conv['tokens']['output']}**")
                    container.write(f"LLM Calls: **{conv['tokens']['llm_calls']}**")
        
    # Display existing messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle user input
    if 'user_input' not in st.session_state:
        next_prompt = st.session_state['bot_config']['start_prompt']
        user_query = st.chat_input(placeholder=next_prompt, key="user_input")
        st.session_state['bot_config']['start_prompt'] = " "
    elif st.session_state.count > 1:
        user_query = st.session_state['user_input']
        
        if user_query:
            # Display user message
            st.session_state.messages.append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.markdown(user_query)

            # Create new conversation group for this question
            current_conv = {
                'question': user_query,
                'agents': [],
                'tokens': {'input': 0, 'output': 0, 'llm_calls': 0}
            }
            st.session_state['current_conversation'] = current_conv
            st.session_state['conversations'].append(current_conv)

            # Get and display assistant response
            response = ""
            with st.chat_message("assistant"):
                try:
                    session_id = st.session_state['session_id']
                    # Handle streaming response from invoke_agent
                    table_name = st.session_state.get('current_table_name')
                    
                    response_chunks = []
                    for chunk_text, chunk_table_name, token_info in invoke_agent(
                        user_query, 
                        session_id, 
                        st.session_state['task_yaml_content']
                    ):
                        st.write(chunk_text)
                        response_chunks.append(chunk_text)
                        if chunk_table_name:
                            table_name = chunk_table_name
                    
                    response = "".join(response_chunks)
                    
                    # Store table name in session state for persistence
                    if table_name:
                        st.session_state['current_table_name'] = table_name
                                    
                except Exception as e:
                    print(f"Error: {e}")  # Keep logging for debugging
                    st.error(f"An error occurred: {str(e)}")  # Show error in UI
                    response = "I encountered an error processing your request. Please try again."

            # Update chat history
            st.session_state.messages.append({"role": "assistant", "content": response})

        # Reset input
        user_query = st.chat_input(placeholder=" ", key="user_input")

    # Update session count
    st.session_state['count'] = st.session_state.get('count', 1) + 1

if __name__ == "__main__":
    main()
