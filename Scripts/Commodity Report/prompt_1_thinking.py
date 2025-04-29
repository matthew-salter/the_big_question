import openai
import time
import os

def run_prompt(data):
    # Extract the incoming variables
    assistant_id = data.get('assistant_id')
    thread_id = data.get('thread_id')

    client = data.get('client')
    client_context = data.get('client_context')
    main_question = data.get('main_question')
    question_context = data.get('question_context')
    number_sections = data.get('number_sections')
    number_sub_sections = data.get('number_sub_sections')
    target_variable = data.get('target_variable')
    commodity = data.get('commodity')
    region = data.get('region')
    time_range = data.get('time_range')

    # Load the correct prompt template
    prompt_path = 'Prompts/Commodity Report/prompt_1_thinking.txt'
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()

    # Fill in the prompt
    prompt = prompt_template.format(
        client=client,
        client_context=client_context,
        main_question=main_question,
        question_context=question_context,
        number_sections=number_sections,
        number_sub_sections=number_sub_sections,
        target_variable=target_variable,
        commodity=commodity,
        region=region,
        time_range=time_range
    )

    # Step 1: Add message to existing Thread
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )

    # Step 1.5: Wait to allow backend to register the message
    time.sleep(1)

    # Step 2: Run the Assistant on that Thread
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        temperature=0.2,
        response_format="json_object"
    )

    # Step 3: Poll until Run is complete
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        time.sleep(1)  # wait 1 second between checks

    # Step 4: Retrieve the final message from the Thread
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    for msg in messages.data:
        if msg.role == "assistant":
            for content in msg.content:
                if content.type == "json_object":
                    return {"output": content.json}

    # If nothing found
    return {"error": "No valid JSON object returned from Assistant."}
