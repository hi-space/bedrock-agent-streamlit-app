import datetime

# Bot configurations
bot_configs = [
    {
        "bot_name": "Energy Agent",
        "agent_name": "agent-quick-start-2025",
        "agent_id": "ADSSKE7HGL",
        "agent_alias_id": "CUTZ6N2T2A",
        "start_prompt": "에너지 소비, 예측, 피크 사용량, 운영에 대해 문의하세요"
    },
    {
        "bot_name": "Marketing Advisor",
        "agent_name": "startup_advisor",
        "agent_id": "QJMXEANC52",
        "agent_alias_id": "NNBOKSII5Q",
        "start_prompt": "마케팅을 수행할 스타트업의 프로젝트를 서술하세요.",
        "tasks": "tasks.yaml",
        "inputs": {
            "web_domain": "flyingCars.com",
            "project_description": "FlyingCars wants to be the leading supplier of flying cars. The project is to build an innovative marketing strategy to showcase FlyingCars' advanced offerings, emphasizing ease of use, cost effectiveness, productivity, and safety. Target high net worth individuals, highlighting success stories and transformative potential. Be sure to include a draft for a video ad.",
            "feedback_iteration_count": "1"
        },
        "additional_instructions": """Use a single Working Memory table for this entire set of tasks, with 
            table name: startup-advisor. Tell your collaborators this table name as part of 
            every request, so that they are not confused and they share state effectively.
            The keys they use in that table will allow them to keep track of any number 
            of state items they require."""
    },
    {
        "bot_name": "Mortgages Assistant",
        "agent_name": "mortgages_assistant",
        "start_prompt": "I'm your mortgages assistant. How can I help today?",
        "session_attributes": {
            "sessionAttributes": {
                "customer_id": "123456",
                "todays_date": datetime.datetime.now().strftime("%Y-%m-%d")
            },
            "promptSessionAttributes": {
                "customer_id": "123456",
                "customer_preferred_name": "Mark",
                "todays_date": datetime.datetime.now().strftime("%Y-%m-%d")
            }
        }
    }
]
