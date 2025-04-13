import boto3
import streamlit as st
import datetime
import json
import math
from utils.bedrock_agent import Task

def make_full_prompt(tasks, additional_instructions, processing_type="allow_parallel"):
    """Build a full prompt from tasks and instructions."""
    prompt = ''
    if processing_type == 'sequential':
        prompt += """
다음 작업을 순차적으로 수행하세요. 다음 사항을 주의하세요. 
어떤 작업도 병렬로 수행하지 마세요. 작업에 이전 작업에서 생성된 정보가 필요한 경우, 
작업에 대한 포괄적인 입력으로 전체 텍스트 세부 정보를 포함해야 합니다.\n\n"""
    elif processing_type == "allow_parallel":
        prompt += """
다음 작업을 가능한 한 많이 병렬로 수행하세요.
작업 간의 종속성이 분명한 경우 해당 작업을 순차적으로 실행하세요. 
작업에 이전 작업에서 생성된 정보가 필요한 경우,
작업에 대한 입력으로 포괄적인 텍스트 세부 정보를 반드시 포함하세요.\n\n"""

    for task_num, task in enumerate(tasks, 1):
        prompt += f"Task {task_num}. {task}\n"

    prompt += "\n최종 답안을 제출하기 전에 각 작업에 대해 예상한 결과를 달성했는지 검토합니다."

    if additional_instructions:
        prompt += f"\n{additional_instructions}"

    return prompt

def process_routing_trace(event, step, _sub_agent_name, _time_before_routing=None):
    """Process routing classifier trace events."""
   
    _route = event['trace']['trace']['routingClassifierTrace']
    
    if 'modelInvocationInput' in _route:
        container = st.container(border=True)                            
        container.markdown(f"""🔍 요청에 맞는 collaborator를 선택 중입니다...""")
        return datetime.datetime.now(), step, _sub_agent_name, None, None
        
    if 'modelInvocationOutput' in _route and _time_before_routing:
        _llm_usage = _route['modelInvocationOutput']['metadata']['usage']
        inputTokens = _llm_usage.get('inputTokens', 0)
        outputTokens = _llm_usage['outputTokens']
        
        _route_duration = datetime.datetime.now() - _time_before_routing

        _raw_resp_str = _route['modelInvocationOutput']['rawResponse']['content']
        _raw_resp = json.loads(_raw_resp_str)
        _classification = _raw_resp['content'][0]['text'].replace('<a>', '').replace('</a>', '')

        if _classification == "undecidable":
            text = f"❌ 일치하는 collaborator가 없습니다. `SUPERVISOR` 모드로 전환합니다."
        elif _classification in (_sub_agent_name, 'keep_previous_agent'):
            step = math.floor(step + 1)
            text = f"➡️ 이전 collaborator와 대화를 이어가세요."
        else:
            _sub_agent_name = _classification
            step = math.floor(step + 1)
            text = f"✅ **Collaborator**: `{_sub_agent_name}`"

        time_text = f"- **Intent classifier** took {_route_duration.total_seconds():,.1f}s"
        container = st.container(border=True)                            
        container.write(text)
        container.write(time_text)
        
        return step, _sub_agent_name, inputTokens, outputTokens

def process_orchestration_trace(event, agentClient, step):
    """Process orchestration trace events."""
    _orch = event['trace']['trace']['orchestrationTrace']
    inputTokens = 0
    outputTokens = 0
    
    if "invocationInput" in _orch:
        _input = _orch['invocationInput']

        print(_input)
        
        if 'knowledgeBaseLookupInput' in _input:
            with st.expander("Using knowledge base", True, icon=":material/plumbing:"):
                st.write("**knowledge base id**: " + _input["knowledgeBaseLookupInput"]["knowledgeBaseId"])
                st.write("**query**: " + _input["knowledgeBaseLookupInput"]["text"].replace('$', '\\$'))
                
        if "actionGroupInvocationInput" in _input:
            function = _input["actionGroupInvocationInput"]["function"]
            with st.expander(f"Invoking Tool - `{function}`", True, icon=":material/plumbing:"):
                st.write(f"- **Function:** `{function}`")
                st.write(f"- **Type:** `{_input.get('actionGroupInvocationInput', {}).get('executionType', '')}`")
                if 'parameters' in _input["actionGroupInvocationInput"]:
                    st.write("- **Parameters**")
                    params = _input["actionGroupInvocationInput"]["parameters"]
                    st.table({
                        'Parameter Name': [p["name"] for p in params],
                        'Parameter Value': [p["value"] for p in params]
                    })
                    
                    # Monitor DynamoDB operations
                    if function in ['set_value_for_key', 'get_key_value']:
                        table_param = next((p for p in params if p["name"] == "table_name"), None)
                        if table_param:
                            table_name = table_param["value"]
                            print(f"DynamoDB operation: {function} on table: {table_name}")  # Debug log
                            # Store table name in session state
                            st.session_state['current_table_name'] = table_name

        if 'codeInterpreterInvocationInput' in _input:
            with st.expander("Code interpreter tool usage", True, icon=":material/psychology:"):
                gen_code = _input['codeInterpreterInvocationInput']['code']
                st.code(gen_code, language="python")
                    
    if "modelInvocationOutput" in _orch:
        if "usage" in _orch["modelInvocationOutput"]["metadata"]:
            inputTokens = _orch["modelInvocationOutput"]["metadata"]["usage"].get("inputTokens", 0)
            outputTokens = _orch["modelInvocationOutput"]["metadata"]["usage"]["outputTokens"]
                    
    # Initialize agent data when we first see the agent
    if "agentId" in event["trace"] and 'current_conversation' in st.session_state:
        current_conv = st.session_state['current_conversation']
        agentData = agentClient.get_agent(agentId=event["trace"]["agentId"])
        agentName = agentData["agent"]["agentName"]
        
        # Find or create agent data in current conversation
        agent_data = next(
            (agent for agent in current_conv['agents'] if agent['name'] == agentName),
            None
        )
        
        if not agent_data:
            agent_data = {
                'name': agentName,
                'time': datetime.datetime.now(),
                'step': step,
                'tools_used': set()  # Use set to avoid duplicates
            }
            current_conv['agents'].append(agent_data)
        
        # Track tool usage throughout the trace
        if "invocationInput" in _orch:
            _input = _orch['invocationInput']
            
            if 'knowledgeBaseLookupInput' in _input:
                print(f"Agent {agentName} using Knowledge Base")
                agent_data['tools_used'].add('Knowledge Base')
            
            if 'actionGroupInvocationInput' in _input:
                function = _input['actionGroupInvocationInput']['function']
                print(f"Agent {agentName} using Tool: {function}")
                agent_data['tools_used'].add(f'{function}')
            
            if 'codeInterpreterInvocationInput' in _input:
                print(f"Agent {agentName} using Code Interpreter")
                agent_data['tools_used'].add('Code Interpreter')

        # Also track tools from observations
        if "observation" in _orch:
            _obs = _orch['observation']
            
            if 'knowledgeBaseLookupOutput' in _obs:
                print(f"Agent {agentName} completed Knowledge Base lookup")
                agent_data['tools_used'].add('Knowledge Base')
                
            if 'actionGroupInvocationOutput' in _obs:
                print(f"Agent {agentName} completed Tool invocation")
                
            if 'codeInterpreterInvocationOutput' in _obs:
                print(f"Agent {agentName} completed Code Interpreter execution")
                agent_data['tools_used'].add('Code Interpreter')
        
        # Display step information
        if "rationale" in _orch:
            chain = event["trace"]["callerChain"]
            container = st.container(border=True)
            
            if len(chain) <= 1:
                step = math.floor(step + 1)
                container.markdown(f"""#### Step  :blue[{round(step,2)}]""")
            else:
                step = step + 0.1
                container.markdown(f"""###### Step {round(step,2)} Sub-Agent  :red[{agentName}]""")
            
            # Update step in agent data
            agent_data['step'] = step
            
            # Add matching indentation for the content
            if len(chain) <= 1:
                container.write(_orch["rationale"]["text"].replace('$', '\\$'))
            else:
                container.markdown(_orch["rationale"]["text"].replace('$', '\\$'))

    if "observation" in _orch:
        _obs = _orch['observation']
        
        if 'knowledgeBaseLookupOutput' in _obs:
            with st.expander(":green[Knowledge Base Results]", True, icon=":material/psychology:"):
                _refs = _obs['knowledgeBaseLookupOutput']['retrievedReferences']
                _ref_count = len(_refs)
                st.write(f"{_ref_count} references")
                for i, _ref in enumerate(_refs, 1):
                    st.write(f"  ({i}) {_ref['content']['text'][0:200]}...")

        if 'actionGroupInvocationOutput' in _obs:
            with st.expander(":green[Tool Response]", False, icon=":material/psychology:"):
                st.write(_obs['actionGroupInvocationOutput']['text'].replace('$', '\\$'))

        if 'codeInterpreterInvocationOutput' in _obs:
            with st.expander(":green[Code interpreter]", True, icon=":material/psychology:"):
                if 'executionOutput' in _obs['codeInterpreterInvocationOutput']:
                    raw_output = _obs['codeInterpreterInvocationOutput']['executionOutput']
                    st.code(raw_output)

                if 'executionError' in _obs['codeInterpreterInvocationOutput']:
                    error_text = _obs['codeInterpreterInvocationOutput']['executionError']
                    st.write(f"Code interpretation error: {error_text}")

                if 'files' in _obs['codeInterpreterInvocationOutput']:
                    files_generated = _obs['codeInterpreterInvocationOutput']['files']
                    st.write(f"Code interpretation files generated:\n{files_generated}")

        if 'finalResponse' in _obs:
            with st.expander(":blue[Agent Response]", True, icon=":material/psychology:"):
                st.write(_obs['finalResponse']['text'].replace('$', '\\$'))
            
    return step, inputTokens, outputTokens


def invoke_agent(input_text, session_id, task_yaml_content):
    """Main agent invocation and response processing."""
    client = boto3.client('bedrock-agent-runtime')
    agentClient = boto3.client('bedrock-agent')
    region = boto3.session.Session().region_name
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    # Configure tools
    web_search_tool = {
        "code":f"arn:aws:lambda:{region}:{account_id}:function:web_search",
        "definition":{
            "name": "web_search",
            "description": "Searches the web for information",
            "parameters": {
                "search_query": {
                    "description": "The query to search the web with",
                    "type": "string",
                    "required": True,
                },
                "target_website": {
                    "description": "The specific website to search including its domain name. If not provided, the most relevant website will be used",
                    "type": "string",
                    "required": False,
                },
                "topic": {
                    "description": "The topic being searched. 'news' or 'general'. Helps narrow the search when news is the focus.",
                    "type": "string",
                    "required": False,
                },
                "days": {
                    "description": "The number of days of history to search. Helps when looking for recent events or news.",
                    "type": "string",
                    "required": False,
                },
            },
        },
    }

    set_value_for_key = {
        "code":f"arn:aws:lambda:{region}:{account_id}:function:working_memory",
        "definition":{
            "name": "set_value_for_key",
            "description": " Stores a key-value pair in a DynamoDB table. Creates the table if it doesn't exist.",
            "parameters": {
                "key": {
                    "description": "The name of the key to store the value under.",
                    "type": "string",
                    "required": True,
                },
                "value": {
                    "description": "The value to store for that key name.",
                    "type": "string",
                    "required": True,
                },
                "table_name": {
                    "description": "The name of the DynamoDB table to use for storage.",
                    "type": "string",
                    "required": True,
                }
            },
        },
    }

    get_key_value = {
        "code":f"arn:aws:lambda:{region}:{account_id}:function:working_memory",
        "definition":{
            "name": "get_key_value",
            "description": "Retrieves a value for a given key name from a DynamoDB table.",
            "parameters": {
                "key": {
                    "description": "The name of the key to store the value under.",
                    "type": "string",
                    "required": True,
                },
                "table_name": {
                    "description": "The name of the DynamoDB table to use for storage.",
                    "type": "string",
                    "required": True,
                }
            },
        },
    }
    
    # Process tasks if any
    _tasks = []
    _bot_config = st.session_state['bot_config']
    for _task_name in task_yaml_content.keys():
        _curr_task = Task(_task_name, task_yaml_content, _bot_config['inputs'])
        _tasks.append(_curr_task)
        
    if len(_tasks) > 0:
        additional_instructions = _bot_config.get('additional_instructions')
        messagesStr = make_full_prompt(_tasks, additional_instructions, processing_type="allow_parallel")
    else:
        messagesStr = input_text

    # Invoke agent
    try:
        if 'session_attributes' in _bot_config:
            session_state = {
                "sessionAttributes": _bot_config['session_attributes']['sessionAttributes']
            }
            if 'promptSessionAttributes' in _bot_config['session_attributes']:
                session_state['promptSessionAttributes'] = _bot_config['session_attributes']['promptSessionAttributes']

            response = client.invoke_agent(
                agentId=_bot_config['agent_id'],
                agentAliasId=_bot_config['agent_alias_id'],
                sessionId=session_id,
                sessionState=session_state,
                inputText=messagesStr,
                enableTrace=True
            )
        else:
            response = client.invoke_agent(
                agentId=_bot_config['agent_id'],
                agentAliasId=_bot_config['agent_alias_id'],
                sessionId=session_id,
                inputText=messagesStr,
                enableTrace=True
            )
    except Exception as e:
        print(f"Error invoking agent: {e}")
        raise e

    # Process response
    step = 0.0
    _sub_agent_name = " "
    _time_before_routing = None
    inputTokens = 0
    outputTokens = 0
    _total_llm_calls = 0
    
    with st.spinner("Processing ....."):
        for event in response.get("completion"):
            if "chunk" in event:
                chunk_text = event["chunk"]["bytes"].decode("utf-8").replace('$', '\\$')
                # Try to extract table name if it's in the response
                table_name = None
                try:
                    # Look for table name in various formats
                    lower_text = chunk_text.lower()
                    if "table name:" in lower_text:
                        table_name = lower_text.split("table name:")[1].split()[0].strip()
                    elif "table:" in lower_text:
                        table_name = lower_text.split("table:")[1].split()[0].strip()
                    elif "dynamodb table:" in lower_text:
                        table_name = lower_text.split("dynamodb table:")[1].split()[0].strip()
                    elif "using table" in lower_text:
                        table_name = lower_text.split("using table")[1].split()[0].strip()
                        
                    # Clean up any punctuation
                    if table_name:
                        table_name = table_name.strip(".,!?()[]{}'\"`")
                        print(f"Found table name: {table_name}")  # Debug log
                except Exception as e:
                    print(f"Error extracting table name: {e}")  # Debug log
                    pass
                # Include current token counts with each chunk
                token_info = {
                    'input': inputTokens,
                    'output': outputTokens,
                    'llm_calls': _total_llm_calls
                }
                yield chunk_text, table_name, token_info
                
            if "trace" in event:
                if 'routingClassifierTrace' in event['trace']['trace']:
                    #print("Processing routing trace...")
                    result = process_routing_trace(event, step, _sub_agent_name, _time_before_routing)
                    if result:
                        if len(result) == 5:  # Initial invocation
                            #print("Initial routing invocation")
                            _time_before_routing, step, _sub_agent_name, in_tokens, out_tokens = result
                            if in_tokens and out_tokens:
                                inputTokens += in_tokens
                                outputTokens += out_tokens
                                _total_llm_calls += 1
                        else:  # Subsequent invocation
                            #print("Subsequent routing invocation")
                            step, _sub_agent_name, in_tokens, out_tokens = result
                            if in_tokens and out_tokens:
                                inputTokens += in_tokens
                                outputTokens += out_tokens
                                _total_llm_calls += 1

                        
                if "orchestrationTrace" in event["trace"]["trace"]:
                    result = process_orchestration_trace(event, agentClient, step)
                    if result:
                        step, in_tokens, out_tokens = result
                        if in_tokens and out_tokens:
                            inputTokens += in_tokens
                            outputTokens += out_tokens
                            _total_llm_calls += 1

        # Update token information in current conversation
        if 'current_conversation' in st.session_state and st.session_state['current_conversation']:
            current_conv = st.session_state['current_conversation']
            current_conv['tokens'] = {
                'input': inputTokens,
                'output': outputTokens,
                'llm_calls': _total_llm_calls
            }
