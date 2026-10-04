# HW5 Reflection

For this reflection I picked run 20289ffb from agent_runs.jsonl. The question was "List 50 fixtures played at Gilroy Field."

First the harness logged a start event with the model (qwen2.5:3b), the question and max_steps, which was 5. Then it sent my system prompt, the question and the descriptions of my three tools to Ollama. That counted as step 1.

The model took about 56 seconds to reply. It didn't write any text. It just asked for search_fixtures with the query "Gilroy Field" and a limit of 50. Honestly that was a sensible choice, because the user did ask for 50 fixtures. The harness logged the step and passed the call to execute_tool.

execute_tool checked the arguments first. The names and types were fine, so it moved on to my safety rule, which says the assistant can't pull more than 20 fixtures in one search. 50 is over that, so it returned ok false with a SAFETY_BLOCKED error. It didn't raise an exception, and the database was never queried. The harness logged the tool call with its input and this result.

Then the loop stopped. I made it end the run on a safety block instead of sending the error back to the model, because I didn't want the model to keep trying different ways around the rule. The stop event shows stop_reason safety_block, 1 step and 1 tool call, and the user got a message saying the request wasn't allowed.

So this run ended because of the safety rule, not because it finished or hit max_steps. What I liked about it is that the rule is enforced by my code, so it doesn't depend on the model behaving.
